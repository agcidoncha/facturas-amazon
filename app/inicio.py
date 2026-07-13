from fastapi import APIRouter, Depends
from fastapi.responses import HTMLResponse

from app.auth import verificar_credenciales
from app.plantillas import pagina

router = APIRouter()

# Un módulo por tarjeta. Añadir aquí los siguientes módulos según se vayan
# construyendo, sin tocar el resto de la aplicación.
MODULOS = [
    {
        "titulo": "Gestión de Facturas",
        "descripcion": "Sube, consulta y exporta las facturas que Amazon emite al vendedor.",
        "url": "/facturas",
    },
]


@router.get("/", response_class=HTMLResponse)
def inicio(_: None = Depends(verificar_credenciales)):
    tarjetas = "".join(
        f"""
        <a class="tarjeta-modulo" href="{m['url']}">
          <h2>{m['titulo']}</h2>
          <p>{m['descripcion']}</p>
        </a>
        """
        for m in MODULOS
    )
    contenido = f"""
    <h1>Melopido</h1>
    <p class="subtitulo">Selecciona un módulo.</p>
    <div class="rejilla-modulos">
      {tarjetas}
    </div>
    """
    return pagina("Inicio", contenido, activo="inicio")
