from fastapi import APIRouter, Depends
from fastapi.responses import HTMLResponse
from sqlalchemy import func
from sqlalchemy.orm import Session

from app import iconos, models
from app.auth import verificar_credenciales
from app.db import get_db
from app.plantillas import pagina

router = APIRouter()

# Un módulo por tarjeta. Añadir aquí los siguientes módulos según se vayan
# construyendo, sin tocar el resto de la aplicación.
MODULOS = [
    {
        "titulo": "Gestión de Facturas",
        "descripcion": "Sube, consulta y exporta las facturas que Amazon emite al vendedor.",
        "url": "/facturas",
        "icono": iconos.documento(18),
    },
]


@router.get("/", response_class=HTMLResponse)
def inicio(_: None = Depends(verificar_credenciales), db: Session = Depends(get_db)):
    total_facturas = db.query(func.count(models.Documento.id)).scalar() or 0
    necesitan_revision = (
        db.query(func.count(models.Documento.id))
        .filter(models.Documento.estado == "necesita revisión")
        .scalar()
        or 0
    )

    tarjetas = "".join(
        f"""
        <a class="tarjeta-modulo" href="{m['url']}">
          <div class="icono-modulo">{m['icono']}</div>
          <div class="etiqueta-modulo">Módulo</div>
          <h2>{m['titulo']}</h2>
          <p>{m['descripcion']}</p>
          <div class="estadisticas-modulo">{total_facturas} facturas registradas · {necesitan_revision} por revisar</div>
        </a>
        """
        for m in MODULOS
    )

    tarjeta_proxima = f"""
    <div class="tarjeta-modulo tarjeta-modulo-proxima">
      <div class="icono-modulo">{iconos.mas_circulo(18)}</div>
      <div class="etiqueta-modulo" style="color:var(--gris-600)">Próximamente</div>
      <h2>Más módulos</h2>
      <p>Este espacio crecerá con futuras herramientas de gestión de la empresa.</p>
    </div>
    """

    contenido = f"""
    <h1>Melopido</h1>
    <p class="subtitulo">Selecciona un módulo.</p>
    <div class="rejilla-modulos">
      {tarjetas}
      {tarjeta_proxima}
    </div>
    """
    return pagina("Inicio", contenido, activo="inicio")
