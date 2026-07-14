import hashlib
import html
import os
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from app import iconos, models
from app.db import get_db
from app.extraccion import procesar_y_guardar
from app.plantillas import pagina

router = APIRouter()

APP_TOKEN = os.environ.get("APP_TOKEN")
PDF_STORAGE_PATH = Path(os.environ.get("PDF_STORAGE_PATH", "/var/data/facturas"))

SCRIPT_ZONA_SUBIDA = """
<script>
(function () {
  var zona = document.getElementById('zona-subida');
  var entrada = document.getElementById('campo-archivos');
  var lista = document.getElementById('lista-archivos');
  var formulario = document.getElementById('formulario-subida');
  var superposicion = document.getElementById('superposicion-carga');
  var archivos = [];

  function formatearTamano(bytes) {
    return bytes < 1024 * 1024
      ? Math.round(bytes / 1024) + ' KB'
      : (bytes / 1024 / 1024).toFixed(1) + ' MB';
  }

  function sincronizarEntrada() {
    var dt = new DataTransfer();
    archivos.forEach(function (f) { dt.items.add(f); });
    entrada.files = dt.files;
  }

  function renderizarLista() {
    lista.innerHTML = '';
    archivos.forEach(function (f, indice) {
      var li = document.createElement('li');
      var nombre = document.createElement('span');
      nombre.className = 'nombre-archivo';
      nombre.textContent = f.name;
      var tamano = document.createElement('span');
      tamano.className = 'tamano-archivo';
      tamano.textContent = formatearTamano(f.size);
      var boton = document.createElement('button');
      boton.type = 'button';
      boton.className = 'quitar-archivo';
      boton.setAttribute('aria-label', 'Quitar ' + f.name);
      boton.innerHTML = '&times;';
      boton.addEventListener('click', function () {
        archivos.splice(indice, 1);
        sincronizarEntrada();
        renderizarLista();
      });
      li.appendChild(nombre);
      li.appendChild(tamano);
      li.appendChild(boton);
      lista.appendChild(li);
    });
  }

  entrada.addEventListener('change', function () {
    Array.from(entrada.files).forEach(function (f) { archivos.push(f); });
    sincronizarEntrada();
    renderizarLista();
  });

  zona.addEventListener('dragenter', function () { zona.classList.add('arrastrando'); });
  zona.addEventListener('dragleave', function () { zona.classList.remove('arrastrando'); });
  zona.addEventListener('drop', function () { zona.classList.remove('arrastrando'); });

  formulario.addEventListener('submit', function () {
    superposicion.hidden = false;
  });
})();
</script>
"""


@router.get("/subir", response_class=HTMLResponse)
def formulario_subida():
    contenido = f"""
    <h1>Subir facturas</h1>
    <p class="subtitulo">Sube uno o varios PDF descargados de la Biblioteca de Documentos Fiscales de Amazon.</p>
    <div class="tarjeta" style="position:relative">
      <form method="post" enctype="multipart/form-data" id="formulario-subida">
        <div class="campo">
          <label for="token">{iconos.candado()} Contraseña compartida</label>
          <input type="password" id="token" name="token" required>
        </div>
        <div class="campo">
          <label>Archivos PDF</label>
          <label class="zona-subida" id="zona-subida">
            <div class="icono-subida">{iconos.subir(17)}</div>
            <div class="texto-principal">Arrastra tus PDF aquí o haz clic para seleccionar</div>
            <div class="texto-secundario">Puedes seleccionar varios archivos a la vez</div>
            <input type="file" id="campo-archivos" name="archivos" accept="application/pdf" multiple required>
          </label>
          <ul class="lista-archivos" id="lista-archivos"></ul>
        </div>
        <button type="submit" class="boton">{iconos.subir()} Subir facturas</button>
      </form>
      <div class="superposicion-carga" id="superposicion-carga" hidden>
        {iconos.refrescar(28)}
        <p>Leyendo y guardando las facturas…</p>
      </div>
    </div>
    {SCRIPT_ZONA_SUBIDA}
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
            errores.append({"nombre": archivo.filename, "motivo": "no es un PDF"})
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
        guardados.append({
            "nombre": archivo.filename,
            "emisor": documento.emisor,
            "tipo_gasto": documento.tipo_gasto or documento.tipo_documento,
        })

    def bloque_guardados():
        if not guardados:
            return '<p class="texto-vacio">Ninguno esta vez.</p>'
        filas = "".join(
            f'<li><span>{html.escape(g["nombre"])}</span>'
            f'<span class="detalle-item">{html.escape(g["emisor"])} · {html.escape(g["tipo_gasto"])}</span></li>'
            for g in guardados
        )
        return f'<ul class="lista-resultado">{filas}</ul>'

    def bloque_duplicados():
        if not duplicados:
            return '<p class="texto-vacio">Ninguno esta vez.</p>'
        filas = "".join(f'<li><span>{html.escape(d)}</span></li>' for d in duplicados)
        return f'<ul class="lista-resultado">{filas}</ul>'

    def bloque_errores():
        if not errores:
            return '<p class="texto-vacio">Ninguno esta vez.</p>'
        filas = "".join(
            f'<li><span>{html.escape(e["nombre"])}</span>'
            f'<span class="detalle-item">{html.escape(e["motivo"])}</span></li>'
            for e in errores
        )
        return f'<ul class="lista-resultado">{filas}</ul>'

    contenido_html = f"""
    <h1>Resultado de la subida</h1>
    <p class="subtitulo">Esto es lo que ha pasado con cada archivo enviado.</p>

    <div class="bloque-resultado">
      <div class="titulo-bloque">{iconos.check_circulo()} Guardados ({len(guardados)})</div>
      {bloque_guardados()}
    </div>

    <div class="bloque-resultado">
      <div class="titulo-bloque tenue">{iconos.duplicado()} Duplicados, ya existían ({len(duplicados)})</div>
      {bloque_duplicados()}
    </div>

    <div class="bloque-resultado">
      <div class="titulo-bloque acento">{iconos.alerta_triangulo()} Errores ({len(errores)})</div>
      {bloque_errores()}
    </div>

    <div class="acciones">
      <a class="boton" href="/subir">Subir más</a>
      <a class="boton-neutro" href="/facturas">Ver panel de facturas</a>
    </div>
    """
    return pagina("Resultado de la subida", contenido_html, activo="subir")
