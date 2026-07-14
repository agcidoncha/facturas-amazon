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
        "descripcion": "Sube, revisa y exporta las facturas que Amazon te cobra por logística, comisiones y publicidad.",
        "url": "/facturas",
        "icono": iconos.documento(28),
    },
]


@router.get("/", response_class=HTMLResponse)
def inicio(_: None = Depends(verificar_credenciales), db: Session = Depends(get_db)):
    necesitan_revision = (
        db.query(func.count(models.Documento.id))
        .filter(models.Documento.estado == "necesita revisión")
        .scalar()
        or 0
    )

    tarjetas = "".join(
        f"""
        <a class="card elev-sm tarjeta-modulo" href="{m['url']}">
          <div style="color:var(--color-accent)">{m['icono']}</div>
          <div class="card-title">{m['titulo']}</div>
          <p class="card-body">{m['descripcion']}</p>
          <div class="card-meta">{iconos.alerta_triangulo(13)} {necesitan_revision} necesitan revisión</div>
        </a>
        """
        for m in MODULOS
    )

    contenido = f"""
    <h1>Módulos</h1>
    <p class="subtitulo">Elige el área de negocio que quieres gestionar.</p>
    <div class="rejilla-modulos">
      {tarjetas}
    </div>
    """
    return pagina("Inicio", contenido, activo="inicio")
