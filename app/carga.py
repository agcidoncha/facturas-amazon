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

MAX_ITEMS_VISIBLES = 5

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
    <p class="subtitulo">Descarga primero los PDF desde la Biblioteca de Documentos Fiscales de Amazon y súbelos aquí. La lectura de los datos es automática.</p>
    <div style="position:relative;max-width:520px">
      <form method="post" enctype="multipart/form-data" id="formulario-subida">
        <div class="field campo-con-icono">
          <label for="token">Contraseña</label>
          {iconos.candado()}
          <input class="input" type="password" id="token" name="token" placeholder="Contraseña compartida" required>
        </div>
        <div class="field">
          <label>Archivos PDF</label>
          <label class="zona-subida" id="zona-subida">
            <div style="color:var(--color-accent)">{iconos.subir(28)}</div>
            <div class="texto-principal">Arrastra tus PDF aquí</div>
            <div class="texto-secundario">o haz clic para seleccionar — puedes elegir varios a la vez</div>
            <input type="file" id="campo-archivos" name="archivos" accept="application/pdf" multiple required>
          </label>
          <ul class="lista-archivos" id="lista-archivos"></ul>
        </div>
        <button type="submit" class="btn btn-primary btn-block">{iconos.subir()} Subir facturas</button>
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
            errores.append({"nombre": archivo.filename, "motivo": "No es un archivo PDF válido"})
            continue

        contenido = archivo.file.read()
        huella = hashlib.sha256(contenido).hexdigest()

        ya_existe = db.query(models.Documento).filter_by(huella_sha256=huella).first()
        if ya_existe:
            duplicados.append({
                "nombre": archivo.filename,
                "subido": ya_existe.fecha_carga.strftime("%d/%m/%Y"),
            })
            continue

        destino = PDF_STORAGE_PATH / f"{huella}.pdf"
        destino.write_bytes(contenido)

        documento = procesar_y_guardar(db, destino, archivo.filename)
        guardados.append({
            "nombre": archivo.filename,
            "emisor": documento.emisor,
            "estado": documento.estado,
        })

    def etiqueta_estado(estado):
        clase = "tag-accent" if estado == "necesita revisión" else "tag-neutral"
        texto = "Revisión" if estado == "necesita revisión" else estado.capitalize()
        return f'<span class="tag {clase}">{html.escape(texto)}</span>'

    def bloque_guardados():
        if not guardados:
            return '<p class="texto-vacio">Ninguno esta vez.</p>'
        visibles = guardados[:MAX_ITEMS_VISIBLES]
        resto = len(guardados) - len(visibles)
        filas = "".join(
            f'<li><div class="nombre-item">{html.escape(g["nombre"])}</div>'
            f'<div class="etiquetas-item">'
            f'<span class="tag tag-neutral">{html.escape(g["emisor"])}</span>'
            f'{etiqueta_estado(g["estado"])}'
            f'</div></li>'
            for g in visibles
        )
        extra = f'<li class="text-muted" style="font-size:12px">+ {resto} más</li>' if resto > 0 else ""
        return f'<ul class="lista-resultado">{filas}{extra}</ul>'

    def bloque_duplicados():
        if not duplicados:
            return '<p class="texto-vacio">Ninguno esta vez.</p>'
        visibles = duplicados[:MAX_ITEMS_VISIBLES]
        resto = len(duplicados) - len(visibles)
        filas = "".join(
            f'<li><div class="nombre-item">{html.escape(d["nombre"])}</div>'
            f'<div class="detalle-item">Ya existía — subido el {d["subido"]}</div></li>'
            for d in visibles
        )
        extra = f'<li class="text-muted" style="font-size:12px">+ {resto} más</li>' if resto > 0 else ""
        return f'<ul class="lista-resultado">{filas}{extra}</ul>'

    def bloque_errores():
        if not errores:
            return '<p class="texto-vacio">Ninguno esta vez.</p>'
        filas = "".join(
            f'<li><div class="nombre-item">{html.escape(e["nombre"])}</div>'
            f'<div class="detalle-item" style="color:var(--color-accent-700)">{html.escape(e["motivo"])}</div></li>'
            for e in errores
        )
        return f'<ul class="lista-resultado">{filas}</ul>'

    contenido_html = f"""
    <h1>Resultado de la subida</h1>
    <div class="rejilla-resultado">
      <div class="card">
        <div class="titulo-bloque">{iconos.check_circulo()} <div class="card-title" style="font-size:15px">Guardados ({len(guardados)})</div></div>
        {bloque_guardados()}
      </div>
      <div class="card">
        <div class="titulo-bloque tenue">{iconos.duplicado()} <div class="card-title" style="font-size:15px">Duplicados ({len(duplicados)})</div></div>
        {bloque_duplicados()}
      </div>
      <div class="card">
        <div class="titulo-bloque acento">{iconos.alerta_triangulo()} <div class="card-title" style="font-size:15px;color:var(--color-accent-700)">Errores ({len(errores)})</div></div>
        {bloque_errores()}
      </div>
    </div>
    <div class="acciones" style="margin-top:var(--space-6)">
      <a class="btn btn-secondary" href="/subir">{iconos.subir()} Subir más</a>
      <a class="btn btn-secondary" href="/facturas">Ver panel de facturas</a>
    </div>
    """
    return pagina("Resultado de la subida", contenido_html, activo="subir")
