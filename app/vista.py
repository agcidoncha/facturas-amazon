import html
import os
import secrets
from collections import defaultdict

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from sqlalchemy.orm import Session

from app import models
from app.db import get_db
from app.extraccion import reprocesar_documento

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
    ids_con_datos = set()
    if ids:
        datos = db.query(models.DatoExtraido).filter(
            models.DatoExtraido.documento_id.in_(ids),
        ).all()
        for d in datos:
            ids_con_datos.add(d.documento_id)
            if d.campo in CAMPOS_VISTA:
                valores_por_doc[d.documento_id][d.campo] = d.valor

    def celda(valor):
        return html.escape(str(valor)) if valor not in (None, "") else ""

    filas_html = []
    for doc in documentos:
        v = valores_por_doc[doc.id]
        accion = (
            ""
            if doc.id in ids_con_datos
            else f'<a href="/facturas/{doc.id}/reprocesar">Reprocesar</a>'
        )
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
            f"<td>{accion}</td>"
            "</tr>"
        )

    filas = "".join(filas_html) or "<tr><td colspan=\"9\">No hay facturas todavía</td></tr>"

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
        <th>Base</th><th>IVA</th><th>Total</th><th>Estado</th><th></th>
      </tr>
      {filas}
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
