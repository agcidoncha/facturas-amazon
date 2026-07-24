import html
import io
import re
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse, StreamingResponse
from openpyxl import Workbook
from sqlalchemy import func
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
    clase = "tag-accent" if estado == "necesita revisión" else "tag-neutral"
    texto = "Revisión" if estado == "necesita revisión" else estado.capitalize()
    return f'<span class="tag {clase}">{html.escape(texto)}</span>'


def _hace_relativo(fecha) -> str:
    if fecha is None:
        return "sin subidas todavía"
    dias = (datetime.now(timezone.utc).date() - fecha.date()).days
    if dias <= 0:
        return "hoy"
    if dias == 1:
        return "ayer"
    return f"hace {dias} días"


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
    ultima_subida = db.query(func.max(models.Documento.fecha_carga)).scalar()

    def celda(etiqueta, valor, num=False):
        texto = html.escape(str(valor)) if valor not in (None, "") else ""
        clase = ' class="num"' if num else ""
        return f'<td data-label="{etiqueta}"{clase}>{texto}</td>'

    filas_tabla = []
    tarjetas_movil = []
    for f in filas:
        acciones = [f'<a class="btn btn-ghost btn-icon" href="/facturas/{f["documento_id"]}" title="Ver">{iconos.ojo()}</a>']
        if not f["tiene_datos"]:
            acciones.append(
                f'<a class="btn btn-ghost btn-icon" href="/facturas/{f["documento_id"]}/reprocesar" title="Reprocesar">{iconos.refrescar()}</a>'
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
            f'<a class="btn btn-ghost btn-icon" href="/facturas/{f["documento_id"]}/reprocesar" title="Reprocesar">{iconos.refrescar(14)}</a>'
            if not f["tiene_datos"] else ""
        )
        tarjetas_movil.append(f"""
        <div class="card elev-sm tarjeta-factura">
          <div class="cabecera-tarjeta">
            <span class="fecha">{html.escape(str(f["fecha_documento"] or ""))}</span>
            {_etiqueta_estado(f["estado"])}
          </div>
          <div class="info-secundaria">{html.escape(f["emisor"])} · {html.escape(f["tipo_gasto"] or "")}</div>
          <div class="info-secundaria">Nº {html.escape(str(f["numero_documento"] or ""))}</div>
          <div class="pie-tarjeta">
            <span class="total">Total {html.escape(str(f["importe_total"] or ""))}</span>
            <div style="display:flex;align-items:center;gap:4px">
              {boton_reprocesar_tarjeta}
              <a href="/facturas/{f["documento_id"]}">Ver →</a>
            </div>
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
          <table class="table">
            <thead><tr>{cabecera_html}</tr></thead>
            <tbody>{"".join(filas_tabla)}</tbody>
          </table>
        </div>
        """
    else:
        contenido_lista = f"""
        <div class="estado-vacio">
          <div style="color:var(--color-accent)">{iconos.caja_vacia(40)}</div>
          <h2>Todavía no hay facturas</h2>
          <p>Sube los PDF que descargaste de Amazon y la aplicación leerá los datos por ti.</p>
          <a class="btn btn-primary" href="/subir">{iconos.subir()} Subir tus primeras facturas</a>
        </div>
        """

    toast = f'<div class="toast">{html.escape(ok)}</div>' if ok else ""

    contenido = f"""
    <div class="acciones" style="justify-content:space-between;align-items:flex-end">
      <div>
        <h1 style="margin-bottom:4px">Facturas</h1>
        <p class="subtitulo" style="margin:0">{total} facturas · {necesitan_revision} necesitan revisión · última subida {_hace_relativo(ultima_subida)}</p>
      </div>
      <div class="acciones" style="margin-bottom:0">
        <a class="btn btn-primary" href="/subir">{iconos.subir()} Subir facturas</a>
        <a class="btn btn-secondary" href="/facturas/exportar.xlsx">{iconos.descargar()} Exportar a Excel</a>
        <button type="button" class="btn btn-secondary" onclick="document.getElementById('dialogo-reprocesar').showModal()">
          {iconos.refrescar()} Reprocesar todas
        </button>
      </div>
    </div>

    {contenido_lista}

    <dialog class="dialog" id="dialogo-reprocesar">
      <div class="dialog-title">{iconos.alerta_triangulo(18)} ¿Reprocesar todas las facturas?</div>
      <p class="dialog-body">Se volverá a ejecutar la lectura automática de datos sobre las {total} facturas ya guardadas. Puede tardar unos segundos y no modifica los PDF originales.</p>
      <div class="dialog-actions">
        <button type="button" class="btn btn-secondary" onclick="document.getElementById('dialogo-reprocesar').close()">Cancelar</button>
        <a class="btn btn-primary" href="/facturas/reprocesar-todas">Reprocesar todas</a>
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
    correctas = 0
    sin_pdf = 0
    for documento in documentos:
        try:
            reprocesar_documento(db, documento)
            correctas += 1
        except FileNotFoundError:
            db.rollback()
            sin_pdf += 1

    if sin_pdf:
        mensaje = quote(
            f"{correctas} facturas reprocesadas correctamente. "
            f"{sin_pdf} no se pudieron reprocesar porque su PDF original ya no existe: elimínalas y vuelve a subirlas."
        )
    else:
        mensaje = quote(f"{correctas} facturas reprocesadas correctamente")
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
            f"<tr><td>{html.escape(c.campo)}</td>"
            f'<td>{html.escape(_formatear_valor(c.valor))}'
            + (' <span class="tag tag-accent tag-inline">revisar</span>' if c.necesita_revision else "")
            + "</td></tr>"
            for c in filas_grupo
        )
        grupos_html += f"""
        <div class="grupo-campos">
          <h6>{titulo}</h6>
          <table class="table">
            <thead><tr><th style="width:38%">Campo</th><th>Valor</th></tr></thead>
            <tbody>{filas_html}</tbody>
          </table>
        </div>
        """

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
          {iconos.alerta_triangulo(18)}
          <div>
            <div class="titulo-aviso">{len(pendientes)} campo(s) necesitan revisión manual</div>
            {lineas}
          </div>
        </div>
        """

    relaciones_html = ""
    for r in relaciones:
        if r.documento_referenciado_id:
            enlace = f'<a href="/facturas/{r.documento_referenciado_id}">Ver factura original →</a>'
        else:
            enlace = '<span class="text-muted">no está en el sistema todavía.</span>'
        relaciones_html += (
            f'<div class="caja-relacion">Esta nota de crédito hace referencia a la factura '
            f'<strong>{html.escape(r.numero_factura_referenciada)}</strong> · {enlace}</div>'
        )

    contenido = f"""
    <a href="/facturas" style="display:inline-flex;align-items:center;gap:6px;font-size:13px;text-decoration:none;color:var(--color-text);opacity:.7;margin-bottom:20px">{iconos.flecha_izquierda()} Volver a facturas</a>
    <div class="acciones" style="justify-content:space-between;align-items:flex-start">
      <div style="display:flex;gap:12px;align-items:flex-start">
        <div style="color:var(--color-accent);margin-top:2px">{iconos.documento(26)}</div>
        <div>
          <h1 style="font-size:22px;margin-bottom:4px;word-break:break-all">{html.escape(documento.archivo_origen)}</h1>
          <p class="subtitulo" style="margin:0">Subido el {documento.fecha_carga.strftime("%d/%m/%Y, %H:%M")}</p>
        </div>
      </div>
      <div class="acciones" style="margin-bottom:0">
        <a class="btn btn-secondary" href="/facturas/{documento_id}/exportar.xlsx">{iconos.descargar()} Exportar esta factura</a>
        <button type="button" class="btn btn-secondary" onclick="document.getElementById('dialogo-eliminar').showModal()">
          {iconos.papelera()} Eliminar
        </button>
      </div>
    </div>

    <div class="rejilla-ficha">
      <div class="campo-ficha"><span class="etiqueta-ficha">Emisor</span><span class="valor-ficha">{html.escape(documento.emisor)}</span></div>
      <div class="campo-ficha"><span class="etiqueta-ficha">Tipo de documento</span><span class="valor-ficha">{html.escape(documento.tipo_documento)}</span></div>
      <div class="campo-ficha"><span class="etiqueta-ficha">Tipo de gasto</span><span class="valor-ficha">{html.escape(documento.tipo_gasto or "(no encontrado)")}</span></div>
      <div class="campo-ficha"><span class="etiqueta-ficha">Estado</span>{_etiqueta_estado(documento.estado)}</div>
    </div>

    {aviso}
    {grupos_html}
    {relaciones_html}

    <dialog class="dialog" id="dialogo-eliminar">
      <div class="dialog-title">{iconos.alerta_triangulo(18)} ¿Eliminar esta factura?</div>
      <p class="dialog-body">Se borrará el registro y el archivo PDF (si todavía existe en el servidor). Esta acción no se puede deshacer. Podrás volver a subir el mismo PDF después.</p>
      <div class="dialog-actions">
        <button type="button" class="btn btn-secondary" onclick="document.getElementById('dialogo-eliminar').close()">Cancelar</button>
        <a class="btn btn-primary" href="/facturas/{documento_id}/eliminar">Eliminar</a>
      </div>
    </dialog>
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
    try:
        reprocesar_documento(db, documento)
    except FileNotFoundError:
        db.rollback()
        mensaje = quote("El PDF original ya no existe: elimina esta factura y vuelve a subirla")
        return RedirectResponse(url=f"/facturas?ok={mensaje}", status_code=303)
    return RedirectResponse(url="/facturas?ok=Factura+reprocesada", status_code=303)


@router.get("/facturas/{documento_id}/eliminar")
def eliminar(
    documento_id: int,
    _: None = Depends(verificar_credenciales),
    db: Session = Depends(get_db),
):
    documento = db.query(models.Documento).get(documento_id)
    if not documento:
        raise HTTPException(status_code=404, detail="Documento no encontrado")

    ruta = Path(documento.ruta_almacenamiento)
    if ruta.exists():
        ruta.unlink()

    db.delete(documento)
    db.commit()

    mensaje = quote("Factura eliminada")
    return RedirectResponse(url=f"/facturas?ok={mensaje}", status_code=303)
