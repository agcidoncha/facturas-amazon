import hashlib
import html
import os
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from app import models
from app.db import get_db
from app.extraccion import procesar_y_guardar
from app.plantillas import pagina

router = APIRouter()

APP_TOKEN = os.environ.get("APP_TOKEN")
PDF_STORAGE_PATH = Path(os.environ.get("PDF_STORAGE_PATH", "/var/data/facturas"))


@router.get("/subir", response_class=HTMLResponse)
def formulario_subida():
    contenido = """
    <h1>Subir facturas de Amazon</h1>
    <p class="subtitulo">Selecciona los PDF descargados de la Biblioteca de Documentos Fiscales de Amazon.</p>
    <div class="tarjeta">
      <form method="post" enctype="multipart/form-data">
        <div class="campo">
          <label for="token">Contraseña</label>
          <input type="password" id="token" name="token" required>
        </div>
        <div class="campo">
          <label for="archivos">Archivos PDF</label>
          <input type="file" id="archivos" name="archivos" accept="application/pdf" multiple required>
        </div>
        <button type="submit" class="boton">Subir</button>
      </form>
    </div>
    """
    return pagina("Subir facturas", contenido, activo="subir")


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

    def lista(items):
        if not items:
            return '<ul class="lista-resultado"><li>ninguno</li></ul>'
        filas = "".join(f"<li>{html.escape(item)}</li>" for item in items)
        return f'<ul class="lista-resultado">{filas}</ul>'

    contenido_html = f"""
    <h1>Resultado de la subida</h1>
    <div class="tarjeta">
      <h2>Guardados ({len(guardados)})</h2>
      {lista(guardados)}
      <h2>Duplicados, ya existían ({len(duplicados)})</h2>
      {lista(duplicados)}
      <h2>Errores ({len(errores)})</h2>
      {lista(errores)}
      <p><a class="enlace-secundario" href="/subir">Subir más</a></p>
    </div>
    """
    return pagina("Resultado de la subida", contenido_html, activo="subir")
