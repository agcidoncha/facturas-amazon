import html
import io
import re
from collections import defaultdict
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse, StreamingResponse
from openpyxl import Workbook
from sqlalchemy.orm import Session

from app import iconos, models
from app.auth import verificar_credenciales
from app.db import get_db
from app.extraccion import reprocesar_documento
from app.plantillas import pagina

router = APIRouter()

CAMPOS_VISTA = [
    "fecha_documento", "fecha_documento_normalizada", "numero_documento",
    "base_imponible", "iva", "importe_total",
]

COLUMNAS = [
    "Fecha de factura", "Emisor", "Tipo de gasto", "Número de factura",
    "Importe base", "IVA", "Importe total", "Estado",
]

# Agrupación puramente de presentación para la pantalla de detalle: no
# cambia cómo se guardan los datos (siguen siendo una lista plana en
# datos_extraidos), solo cómo se organizan visualmente. Cualquier campo
# que no encaje en estos grupos aparece igualmente, en "Desglose y otros
# datos" — nunca se oculta nada.
GRUPOS_CAMPOS = [
    ("Datos generales", {
        "numero_documento", "fecha_documento", "fecha_documento_normalizada",
        "periodo", "moneda", "nif_vendedor", "concepto", "concepto_normalizado",
    }),
    ("Importes", {"base_imponible", "porcentaje_iva", "iva", "importe_total"}),
]


def _a_numero(valor):
    """Convierte un importe con formato español ('1.234,56' o '-121,00') a
    float. Devuelve None si no hay valor o no se puede interpretar, para no
    inventar datos que la extracción no proporcionó."""
    if not valor:
        return None
    texto = str(valor).strip()
    if not re.fullmatch(r"-?[\d.,]+", texto):
        return None
    texto = texto.replace(".", "").replace(",", ".")
    try:
        return float(texto)
    except ValueError:
        return None


def _formatear_valor(valor):
    if valor is None:
        return "(no encontrado)"
    if isinstance(valor, list):
        partes = []
        for item in valor:
            if isinstance(item, dict):
                partes.append(", ".join(f"{k}: {v}" for k, v in item.items()))
            else:
                partes.append(str(item))
        return " | ".join(partes) if partes else "(vacío)"
    if isinstance(valor, dict):
        return ", ".join(f"{k}: {v}" for k, v in valor.items())
    return str(valor)


def _etiqueta_estado(estado: str) -> str:
    clase = "etiqueta-aviso" if estado == "necesita revisión" else "etiqueta-ok"
    return f'<span class="etiqueta {clase}">{html.escape(estado)}</span>'


def _obtener_filas(db: Session) -> list[dict]:
    documentos = db.query(models.Documento).order_by(models.Documento.fecha_carga.desc()).all()
    ids = [d.id for d in documentos]

    valores_por_doc = defaultdict(dict)
    ids_con_datos = set()
    if ids:
        datos = db.query(models.DatoExtraido).filter(
            models.DatoExtraido.documento_id.in_(ids),
        ).all()
        for d in datos:
            ids_con_datos.add(d.documento_id)
            if d.campo in CAMPOS_VISTA:
                valores_por_doc[d.documento_id][d.campo] = d.valor

    filas = []
    for doc in documentos:
        v = valores_por_doc[doc.id]
        filas.append({
            "documento_id": doc.id,
            "tiene_datos": doc.id in ids_con_datos,
            "fecha_documento": v.get("fecha_documento_normalizada") or v.get("fecha_documento"),
            "emisor": doc.emisor,
            "tipo_gasto": doc.tipo_gasto,
            "numero_documento": v.get("numero_documento"),
            "base_imponible": v.get("base_imponible"),
            "iva": v.get("iva"),
            "importe_total": v.get("importe_total"),
            "estado": doc.estado,
        })
    return filas


@router.get("/facturas", response_class=HTMLResponse)
def vista_facturas(
    ok: str | None = None,
    _: None = Depends(verificar_credenciales),
    db: Session = Depends(get_db),
):
    filas = _obtener_filas(db)
    total = len(filas)
    necesitan_revision = sum(1 for f in filas if f["estado"] == "necesita revisión")

    def celda(etiqueta, valor, num=False):
        texto = html.escape(str(valor)) if valor not in (None, "") else ""
        clase = ' class="num"' if num else ""
        return f'<td data-label="{etiqueta}"{clase}>{texto}</td>'

    filas_tabla = []
    tarjetas_movil = []
    for f in filas:
        acciones = [f'<a href="/facturas/{f["documento_id"]}" title="Ver">{iconos.ojo()}</a>']
        if not f["tiene_datos"]:
            acciones.append(
                f'<a class="reprocesar" href="/facturas/{f["documento_id"]}/reprocesar" title="Reprocesar">{iconos.refrescar()}</a>'
            )
        filas_tabla.append(
            "<tr>"
            + celda("Fecha", f["fecha_documento"])
            + celda("Emisor", f["emisor"])
            + celda("Tipo de gasto", f["tipo_gasto"])
            + celda("Nº factura", f["numero_documento"])
            + celda("Base", f["base_imponible"], num=True)
            + celda("IVA", f["iva"], num=True)
            + celda("Total", f["importe_total"], num=True)
            + f'<td data-label="Estado">{_etiqueta_estado(f["estado"])}</td>'
            + f'<td data-label="" class="acciones-fila">{"".join(acciones)}</td>'
            + "</tr>"
        )

        boton_reprocesar_tarjeta = (
            f'<a class="reprocesar" href="/facturas/{f["documento_id"]}/reprocesar">{iconos.refrescar(13)} Reprocesar</a>'
            if not f["tiene_datos"] else ""
        )
        tarjetas_movil.append(f"""
        <div class="tarjeta-factura">
          <div class="cabecera-tarjeta">
            <span class="fecha">{html.escape(str(f["fecha_documento"] or ""))}</span>
            {_etiqueta_estado(f["estado"])}
          </div>
          <div class="numero">{html.escape(str(f["numero_documento"] or ""))}</div>
          <div class="info-secundaria">{html.escape(f["emisor"])} · {html.escape(f["tipo_gasto"] or "")}</div>
          <div class="importes">
            <span>Base {html.escape(str(f["base_imponible"] or ""))}</span>
            <span>IVA {html.escape(str(f["iva"] or ""))}</span>
            <span><strong>Total {html.escape(str(f["importe_total"] or ""))}</strong></span>
          </div>
          <div class="acciones-tarjeta">
            <a class="ver" href="/facturas/{f["documento_id"]}">{iconos.ojo(13)} Ver</a>
            {boton_reprocesar_tarjeta}
          </div>
        </div>
        """)

    cabecera_html = "".join(f"<th>{etq}</th>" for etq in ["Fecha", "Emisor", "Tipo de gasto", "Nº factura", "Base", "IVA", "Total", "Estado", ""])

    if filas:
        contenido_lista = f"""
        <div class="mlp-cards">
          <div class="tarjetas-facturas">{"".join(tarjetas_movil)}</div>
        </div>
        <div class="mlp-table tabla-envoltura">
          <table>
            <thead><tr>{cabecera_html}</tr></thead>
            <tbody>{"".join(filas_tabla)}</tbody>
          </table>
        </div>
        """
    else:
        contenido_lista = f"""
        <div class="estado-vacio">
          <div class="icono-vacio">{iconos.caja_vacia()}</div>
          <h2>Aún no hay facturas</h2>
          <p>Cuando subas tus primeros PDF de Amazon, aparecerán aquí con todos sus datos ya extraídos.</p>
          <a class="boton" href="/subir">Subir tus primeras facturas</a>
        </div>
        """

    toast = f'<div class="toast">{html.escape(ok)}</div>' if ok else ""

    contenido = f"""
    <h1>Facturas</h1>
    <p class="subtitulo">{total} documentos · {necesitan_revision} necesitan revisión</p>
    <div class="acciones">
      <a class="boton" href="/subir">{iconos.subir()} Subir facturas</a>
      <a class="boton-neutro" href="/facturas/exportar.xlsx">{iconos.descargar()} Exportar a Excel</a>
      <button type="button" class="boton-neutro" onclick="document.getElementById('dialogo-reprocesar').showModal()">
        {iconos.refrescar()} Reprocesar todas
      </button>
    </div>

    {contenido_lista}

    <dialog class="dialogo" id="dialogo-reprocesar">
      <div class="titulo-dialogo">{iconos.alerta_triangulo(18)} ¿Reprocesar todas las facturas?</div>
      <p>Se volverá a ejecutar la lectura automática de datos sobre las {total} facturas ya guardadas. Puede tardar unos segundos y no modifica los PDF originales.</p>
      <div class="acciones-dialogo">
        <button type="button" class="boton-neutro" onclick="document.getElementById('dialogo-reprocesar').close()">Cancelar</button>
        <a class="boton" href="/facturas/reprocesar-todas">Reprocesar todas</a>
      </div>
    </dialog>

    {toast}
    """
    return pagina("Facturas", contenido, activo="facturas")


@router.get("/facturas/exportar.xlsx")
def exportar_excel(_: None = Depends(verificar_credenciales), db: Session = Depends(get_db)):
    filas = _obtener_filas(db)

    libro = Workbook()
    hoja = libro.active
    hoja.title = "Facturas"
    hoja.append(COLUMNAS)

    for f in filas:
        hoja.append([
            f["fecha_documento"],
            f["emisor"],
            f["tipo_gasto"],
            f["numero_documento"],
            _a_numero(f["base_imponible"]),
            _a_numero(f["iva"]),
            _a_numero(f["importe_total"]),
            f["estado"],
        ])

    buffer = io.BytesIO()
    libro.save(buffer)
    buffer.seek(0)

    return StreamingResponse(
        buffer,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=facturas_amazon.xlsx"},
    )


@router.get("/facturas/reprocesar-todas")
def reprocesar_todas(_: None = Depends(verificar_credenciales), db: Session = Depends(get_db)):
    documentos = db.query(models.Documento).all()
    for documento in documentos:
        reprocesar_documento(db, documento)
    mensaje = quote(f"{len(documentos)} facturas reprocesadas correctamente")
    return RedirectResponse(url=f"/facturas?ok={mensaje}", status_code=303)


def _agrupar_campos(campos):
    grupos = {titulo: [] for titulo, _ in GRUPOS_CAMPOS}
    grupos["Desglose y otros datos"] = []
    for c in campos:
        if c.campo == "facturas_originales_referenciadas":
            continue  # se muestra en la caja de relación, no aquí
        for titulo, nombres in GRUPOS_CAMPOS:
            if c.campo in nombres:
                grupos[titulo].append(c)
                break
        else:
            grupos["Desglose y otros datos"].append(c)
    return [(titulo, filas) for titulo, filas in grupos.items() if filas]


@router.get("/facturas/{documento_id}", response_class=HTMLResponse)
def detalle_factura(
    documento_id: int,
    _: None = Depends(verificar_credenciales),
    db: Session = Depends(get_db),
):
    documento = db.query(models.Documento).get(documento_id)
    if not documento:
        raise HTTPException(status_code=404, detail="Documento no encontrado")

    campos = (
        db.query(models.DatoExtraido)
        .filter_by(documento_id=documento_id)
        .order_by(models.DatoExtraido.id)
        .all()
    )
    relaciones = db.query(models.RelacionDocumento).filter_by(documento_id=documento_id).all()

    grupos_html = ""
    for titulo, filas_grupo in _agrupar_campos(campos):
        filas_html = "".join(
            f'<div class="fila-campo"><span class="nombre-campo">{html.escape(c.campo)}</span>'
            f'<span class="valor-campo">{html.escape(_formatear_valor(c.valor))}</span></div>'
            for c in filas_grupo
        )
        grupos_html += f'<div class="grupo-campos"><div class="titulo-grupo">{titulo}</div>{filas_html}</div>'

    if not campos:
        grupos_html = '<p class="texto-vacio">Sin datos extraídos todavía.</p>'

    pendientes = [c for c in campos if c.necesita_revision]
    aviso = ""
    if pendientes:
        lineas = "".join(
            f'<div class="linea-aviso"><strong>{html.escape(c.campo)}</strong> — {html.escape(c.origen or "")}</div>'
            for c in pendientes
        )
        aviso = f"""
        <div class="aviso">
          {iconos.alerta_triangulo(17)}
          <div>
            <div class="titulo-aviso">Necesita revisión manual</div>
            {lineas}
          </div>
        </div>
        """

    relaciones_html = ""
    for r in relaciones:
        if r.documento_referenciado_id:
            enlace = f'<a class="enlace-secundario" href="/facturas/{r.documento_referenciado_id}">Ver factura original →</a>'
        else:
            enlace = '<span style="color:var(--color-texto-suave)">no está en el sistema todavía.</span>'
        relaciones_html += (
            f'<div class="caja-relacion">Esta nota de crédito hace referencia a la factura '
            f'<strong>{html.escape(r.numero_factura_referenciada)}</strong> · {enlace}</div>'
        )

    contenido = f"""
    <p><a class="enlace-secundario" href="/facturas">{iconos.flecha_izquierda()} Volver a facturas</a></p>
    <div class="acciones" style="justify-content:space-between;align-items:flex-start">
      <h1 style="margin-bottom:0">{html.escape(documento.archivo_origen)}</h1>
      <a class="boton" href="/facturas/{documento_id}/exportar.xlsx">{iconos.descargar()} Exportar esta factura</a>
    </div>
    <div class="tarjeta">
      <dl class="ficha">
        <div><dt>Emisor</dt><dd>{html.escape(documento.emisor)}</dd></div>
        <div><dt>Tipo de documento</dt><dd>{html.escape(documento.tipo_documento)}</dd></div>
        <div><dt>Tipo de gasto</dt><dd>{html.escape(documento.tipo_gasto or "(no encontrado)")}</dd></div>
        <div><dt>Estado</dt><dd>{_etiqueta_estado(documento.estado)}</dd></div>
        <div><dt>Subido</dt><dd>{documento.fecha_carga.strftime("%Y-%m-%d %H:%M")}</dd></div>
      </dl>
    </div>
    {aviso}
    {grupos_html}
    {relaciones_html}
    """
    return pagina(f"Factura {documento.archivo_origen}", contenido, activo="facturas")


@router.get("/facturas/{documento_id}/exportar.xlsx")
def exportar_una_factura(
    documento_id: int,
    _: None = Depends(verificar_credenciales),
    db: Session = Depends(get_db),
):
    documento = db.query(models.Documento).get(documento_id)
    if not documento:
        raise HTTPException(status_code=404, detail="Documento no encontrado")

    campos = (
        db.query(models.DatoExtraido)
        .filter_by(documento_id=documento_id)
        .order_by(models.DatoExtraido.id)
        .all()
    )

    libro = Workbook()
    hoja = libro.active
    hoja.title = "Factura"
    hoja.append(["Campo", "Valor"])
    hoja.append(["archivo_origen", documento.archivo_origen])
    hoja.append(["emisor", documento.emisor])
    hoja.append(["tipo_documento", documento.tipo_documento])
    hoja.append(["tipo_gasto", documento.tipo_gasto])
    hoja.append(["estado", documento.estado])
    hoja.append(["subido", documento.fecha_carga.strftime("%Y-%m-%d %H:%M")])
    for c in campos:
        hoja.append([c.campo, _formatear_valor(c.valor)])

    buffer = io.BytesIO()
    libro.save(buffer)
    buffer.seek(0)

    nombre_archivo = f"factura_{documento_id}_{documento.archivo_origen.rsplit('.', 1)[0]}.xlsx"
    return StreamingResponse(
        buffer,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename={nombre_archivo}"},
    )


@router.get("/facturas/{documento_id}/reprocesar")
def reprocesar(
    documento_id: int,
    _: None = Depends(verificar_credenciales),
    db: Session = Depends(get_db),
):
    documento = db.query(models.Documento).get(documento_id)
    if not documento:
        raise HTTPException(status_code=404, detail="Documento no encontrado")
    reprocesar_documento(db, documento)
    return RedirectResponse(url="/facturas?ok=Factura+reprocesada", status_code=303)
