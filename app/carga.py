import hashlib
import os
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from app import models
from app.db import get_db
from app.extraccion import procesar_y_guardar

router = APIRouter()

APP_TOKEN = os.environ.get("APP_TOKEN")
PDF_STORAGE_PATH = Path(os.environ.get("PDF_STORAGE_PATH", "/var/data/facturas"))

FORMULARIO_HTML = """
<!doctype html>
<html lang="es">
<head><meta charset="utf-8"><title>Subir facturas</title></head>
<body>
<h1>Subir facturas de Amazon</h1>
<p>Selecciona los PDF descargados de la Biblioteca de Documentos Fiscales de Amazon.</p>
<form method="post" enctype="multipart/form-data">
  <p><label>Contraseña: <input type="password" name="token" required></label></p>
  <p><input type="file" name="archivos" accept="application/pdf" multiple required></p>
  <p><button type="submit">Subir</button></p>
</form>
</body>
</html>
"""


@router.get("/subir", response_class=HTMLResponse)
def formulario_subida():
    return FORMULARIO_HTML


@router.post("/subir", response_class=HTMLResponse)
def subir_documentos(
    token: str = Form(...),
    archivos: list[UploadFile] = File(...),
    db: Session = Depends(get_db),
):
    if not APP_TOKEN or token != APP_TOKEN:
        raise HTTPException(status_code=401, detail="Contraseña incorrecta")

    PDF_STORAGE_PATH.mkdir(parents=True, exist_ok=True)

    guardados = []
    duplicados = []
    errores = []

    for archivo in archivos:
        if not archivo.filename.lower().endswith(".pdf"):
            errores.append(f"{archivo.filename}: no es un PDF")
            continue

        contenido = archivo.file.read()
        huella = hashlib.sha256(contenido).hexdigest()

        ya_existe = db.query(models.Documento).filter_by(huella_sha256=huella).first()
        if ya_existe:
            duplicados.append(archivo.filename)
            continue

        destino = PDF_STORAGE_PATH / f"{huella}.pdf"
        destino.write_bytes(contenido)

        documento = procesar_y_guardar(db, destino, archivo.filename)
        guardados.append(
            f"{archivo.filename} ({documento.emisor} / {documento.tipo_documento} / {documento.estado})"
        )

    filas = "".join(f"<li>{g}</li>" for g in guardados) or "<li>ninguno</li>"
    filas_dup = "".join(f"<li>{d}</li>" for d in duplicados) or "<li>ninguno</li>"
    filas_err = "".join(f"<li>{e}</li>" for e in errores) or "<li>ninguno</li>"

    return f"""
    <!doctype html>
    <html lang="es">
    <head><meta charset="utf-8"><title>Resultado de la subida</title></head>
    <body>
    <h1>Resultado</h1>
    <h2>Guardados ({len(guardados)})</h2><ul>{filas}</ul>
    <h2>Duplicados, ya existían ({len(duplicados)})</h2><ul>{filas_dup}</ul>
    <h2>Errores ({len(errores)})</h2><ul>{filas_err}</ul>
    <p><a href="/subir">Subir más</a></p>
    </body>
    </html>
    """
