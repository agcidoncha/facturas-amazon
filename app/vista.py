import html
import io
import os
import re
import secrets
from collections import defaultdict

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse, StreamingResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from openpyxl import Workbook
from sqlalchemy.orm import Session

from app import models
from app.db import get_db
from app.extraccion import reprocesar_documento
from app.plantillas import pagina

router = APIRouter()
security = HTTPBasic()

APP_TOKEN = os.environ.get("APP_TOKEN")

CAMPOS_VISTA = ["fecha_documento", "numero_documento", "base_imponible", "iva", "importe_total"]

COLUMNAS = [
    "Fecha de factura", "Emisor", "Tipo de gasto", "Número de factura",
    "Importe base", "IVA", "Importe total", "Estado",
]

ETIQUETAS_COLUMNAS = [
    "Fecha", "Emisor", "Tipo de gasto", "Nº factura", "Base", "IVA", "Total", "Estado", "",
]


def _verificar_credenciales(credentials: HTTPBasicCredentials = Depends(security)):
    if not APP_TOKEN or not secrets.compare_digest(credentials.password, APP_TOKEN):
        raise HTTPException(
            status_code=401,
            detail="No autorizado",
            headers={"WWW-Authenticate": "Basic"},
        )


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
            "fecha_documento": v.get("fecha_documento"),
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
def vista_facturas(_: None = Depends(_verificar_credenciales), db: Session = Depends(get_db)):
    filas = _obtener_filas(db)

    def celda(etiqueta, valor):
        texto = html.escape(str(valor)) if valor not in (None, "") else ""
        return f'<td data-label="{etiqueta}">{texto}</td>'

    filas_html = []
    for f in filas:
        acciones = [f'<a class="enlace-secundario" href="/facturas/{f["documento_id"]}">Ver</a>']
        if not f["tiene_datos"]:
            acciones.append(
                f'<a class="enlace-secundario" href="/facturas/{f["documento_id"]}/reprocesar">Reprocesar</a>'
            )
        filas_html.append(
            "<tr>"
            + celda("Fecha", f["fecha_documento"])
            + celda("Emisor", f["emisor"])
            + celda("Tipo de gasto", f["tipo_gasto"])
            + celda("Nº factura", f["numero_documento"])
            + celda("Base", f["base_imponible"])
            + celda("IVA", f["iva"])
            + celda("Total", f["importe_total"])
            + celda("Estado", f["estado"])
            + f'<td data-label="">{" · ".join(acciones)}</td>'
            + "</tr>"
        )

    filas_render = "".join(filas_html) or '<tr><td colspan="9">No hay facturas todavía</td></tr>'
    cabecera_html = "".join(f"<th>{etq}</th>" for etq in ETIQUETAS_COLUMNAS)

    contenido = f"""
    <h1>Facturas</h1>
    <div class="acciones">
      <a class="boton" href="/subir">Subir facturas</a>
      <a class="enlace-secundario" href="/facturas/exportar.xlsx">Exportar a Excel</a>
    </div>
    <div class="tabla-envoltura">
    <table>
      <thead><tr>{cabecera_html}</tr></thead>
      <tbody>
      {filas_render}
      </tbody>
    </table>
    </div>
    """
    return pagina("Facturas", contenido, activo="facturas")


@router.get("/facturas/exportar.xlsx")
def exportar_excel(_: None = Depends(_verificar_credenciales), db: Session = Depends(get_db)):
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


@router.get("/facturas/{documento_id}", response_class=HTMLResponse)
def detalle_factura(
    documento_id: int,
    _: None = Depends(_verificar_credenciales),
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

    filas_campos = "".join(
        f'<tr><td data-label="Campo">{html.escape(c.campo)}</td>'
        f'<td data-label="Valor">{html.escape(_formatear_valor(c.valor))}</td></tr>'
        for c in campos
    ) or '<tr><td colspan="2">Sin datos extraídos todavía</td></tr>'

    pendientes = [c for c in campos if c.necesita_revision]
    aviso = ""
    if pendientes:
        lista = "".join(f"<li>{html.escape(c.campo)}</li>" for c in pendientes)
        aviso = f'<div class="aviso">⚠ Necesita revisión:<ul>{lista}</ul></div>'

    contenido = f"""
    <p><a class="enlace-secundario" href="/facturas">← Volver a la lista</a></p>
    <h1>{html.escape(documento.archivo_origen)}</h1>
    <div class="tarjeta">
      <dl class="ficha">
        <dt>Emisor</dt><dd>{html.escape(documento.emisor)}</dd>
        <dt>Tipo de documento</dt><dd>{html.escape(documento.tipo_documento)}</dd>
        <dt>Tipo de gasto</dt><dd>{html.escape(documento.tipo_gasto or "(no encontrado)")}</dd>
        <dt>Estado</dt><dd>{html.escape(documento.estado)}</dd>
        <dt>Subido</dt><dd>{documento.fecha_carga.strftime("%Y-%m-%d %H:%M")}</dd>
      </dl>
    </div>
    {aviso}
    <div class="tabla-envoltura">
    <table>
      <thead><tr><th>Campo</th><th>Valor</th></tr></thead>
      <tbody>
      {filas_campos}
      </tbody>
    </table>
    </div>
    """
    return pagina(f"Factura {documento.archivo_origen}", contenido, activo="facturas")


@router.get("/facturas/{documento_id}/reprocesar")
def reprocesar(
    documento_id: int,
    _: None = Depends(_verificar_credenciales),
    db: Session = Depends(get_db),
):
    documento = db.query(models.Documento).get(documento_id)
    if not documento:
        raise HTTPException(status_code=404, detail="Documento no encontrado")
    reprocesar_documento(db, documento)
    return RedirectResponse(url="/facturas", status_code=303)
