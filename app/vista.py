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

router = APIRouter()
security = HTTPBasic()

APP_TOKEN = os.environ.get("APP_TOKEN")

CAMPOS_VISTA = ["fecha_documento", "numero_documento", "base_imponible", "iva", "importe_total"]

COLUMNAS = [
    "Fecha de factura", "Emisor", "Tipo de gasto", "Número de factura",
    "Importe base", "IVA", "Importe total", "Estado",
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

    def celda(valor):
        return html.escape(str(valor)) if valor not in (None, "") else ""

    filas_html = []
    for f in filas:
        accion = "" if f["tiene_datos"] else f'<a href="/facturas/{f["documento_id"]}/reprocesar">Reprocesar</a>'
        filas_html.append(
            "<tr>"
            f"<td>{celda(f['fecha_documento'])}</td>"
            f"<td>{celda(f['emisor'])}</td>"
            f"<td>{celda(f['tipo_gasto'])}</td>"
            f"<td>{celda(f['numero_documento'])}</td>"
            f"<td>{celda(f['base_imponible'])}</td>"
            f"<td>{celda(f['iva'])}</td>"
            f"<td>{celda(f['importe_total'])}</td>"
            f"<td>{celda(f['estado'])}</td>"
            f"<td>{accion}</td>"
            "</tr>"
        )

    filas_render = "".join(filas_html) or "<tr><td colspan=\"9\">No hay facturas todavía</td></tr>"

    return f"""
    <!doctype html>
    <html lang="es">
    <head><meta charset="utf-8"><title>Facturas</title></head>
    <body>
    <h1>Facturas</h1>
    <p><a href="/subir">Subir facturas</a> · <a href="/facturas/exportar.xlsx">Exportar a Excel</a></p>
    <table border="1" cellpadding="4">
      <tr>
        <th>Fecha</th><th>Emisor</th><th>Tipo de gasto</th><th>Nº factura</th>
        <th>Base</th><th>IVA</th><th>Total</th><th>Estado</th><th></th>
      </tr>
      {filas_render}
    </table>
    </body>
    </html>
    """


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
