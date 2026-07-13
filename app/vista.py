import html
import os
import secrets
from collections import defaultdict

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from sqlalchemy.orm import Session

from app import models
from app.db import get_db

router = APIRouter()
security = HTTPBasic()

APP_TOKEN = os.environ.get("APP_TOKEN")

CAMPOS_VISTA = ["fecha_documento", "numero_documento", "base_imponible", "iva", "importe_total"]


def _verificar_credenciales(credentials: HTTPBasicCredentials = Depends(security)):
    if not APP_TOKEN or not secrets.compare_digest(credentials.password, APP_TOKEN):
        raise HTTPException(
            status_code=401,
            detail="No autorizado",
            headers={"WWW-Authenticate": "Basic"},
        )


@router.get("/facturas", response_class=HTMLResponse)
def vista_facturas(_: None = Depends(_verificar_credenciales), db: Session = Depends(get_db)):
    documentos = db.query(models.Documento).order_by(models.Documento.fecha_carga.desc()).all()
    ids = [d.id for d in documentos]

    valores_por_doc = defaultdict(dict)
    if ids:
        datos = db.query(models.DatoExtraido).filter(
            models.DatoExtraido.documento_id.in_(ids),
            models.DatoExtraido.campo.in_(CAMPOS_VISTA),
        ).all()
        for d in datos:
            valores_por_doc[d.documento_id][d.campo] = d.valor

    def celda(valor):
        return html.escape(str(valor)) if valor not in (None, "") else ""

    filas_html = []
    for doc in documentos:
        v = valores_por_doc[doc.id]
        filas_html.append(
            "<tr>"
            f"<td>{celda(v.get('fecha_documento'))}</td>"
            f"<td>{celda(doc.emisor)}</td>"
            f"<td>{celda(doc.tipo_gasto)}</td>"
            f"<td>{celda(v.get('numero_documento'))}</td>"
            f"<td>{celda(v.get('base_imponible'))}</td>"
            f"<td>{celda(v.get('iva'))}</td>"
            f"<td>{celda(v.get('importe_total'))}</td>"
            f"<td>{celda(doc.estado)}</td>"
            "</tr>"
        )

    filas = "".join(filas_html) or "<tr><td colspan=\"8\">No hay facturas todavía</td></tr>"

    return f"""
    <!doctype html>
    <html lang="es">
    <head><meta charset="utf-8"><title>Facturas</title></head>
    <body>
    <h1>Facturas</h1>
    <p><a href="/subir">Subir facturas</a></p>
    <table border="1" cellpadding="4">
      <tr>
        <th>Fecha</th><th>Emisor</th><th>Tipo de gasto</th><th>Nº factura</th>
        <th>Base</th><th>IVA</th><th>Total</th><th>Estado</th>
      </tr>
      {filas}
    </table>
    </body>
    </html>
    """
