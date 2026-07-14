"""Iconos SVG en línea (estilo trazo, heredan el color del texto vía
currentColor), reutilizados en varias pantallas. Basados en el mockup
generado con Claude Design a partir de PROJECT_FOR_DESIGN.md."""


def _svg(paths: str, size: int = 16) -> str:
    return (
        f'<svg class="icono" width="{size}" height="{size}" viewBox="0 0 24 24" '
        f'fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" '
        f'stroke-linejoin="round">{paths}</svg>'
    )


def documento(size=18):
    return _svg(
        '<path d="M14.5 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7.5L14.5 2z"></path>'
        '<polyline points="14 2 14 8 20 8"></polyline>'
        '<line x1="16" y1="13" x2="8" y2="13"></line>'
        '<line x1="16" y1="17" x2="8" y2="17"></line>',
        size,
    )


def mas_circulo(size=18):
    return _svg(
        '<circle cx="12" cy="12" r="10"></circle>'
        '<line x1="12" y1="8" x2="12" y2="16"></line>'
        '<line x1="8" y1="12" x2="16" y2="12"></line>',
        size,
    )


def candado(size=13):
    return _svg(
        '<rect x="3" y="11" width="18" height="11" rx="2" ry="2"></rect>'
        '<path d="M7 11V7a5 5 0 0 1 10 0v4"></path>',
        size,
    )


def subir(size=15):
    return _svg(
        '<path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"></path>'
        '<polyline points="17 8 12 3 7 8"></polyline>'
        '<line x1="12" y1="3" x2="12" y2="15"></line>',
        size,
    )


def descargar(size=14):
    return _svg(
        '<path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"></path>'
        '<polyline points="7 10 12 15 17 10"></polyline>'
        '<line x1="12" y1="15" x2="12" y2="3"></line>',
        size,
    )


def refrescar(size=14):
    return _svg(
        '<path d="M21 12a9 9 0 0 1-9 9 9.75 9.75 0 0 1-6.74-2.74L3 16"></path>'
        '<path d="M3 12a9 9 0 0 1 9-9 9.75 9.75 0 0 1 6.74 2.74L21 8"></path>'
        '<path d="M21 3v5h-5"></path><path d="M3 21v-5h5"></path>',
        size,
    )


def check_circulo(size=16):
    return _svg(
        '<path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"></path>'
        '<polyline points="22 4 12 14.01 9 11.01"></polyline>',
        size,
    )


def duplicado(size=16):
    return _svg(
        '<path d="M21.44 11.05 12.25 20.24a5 5 0 0 1-7.07-7.07l8.49-8.48a3.5 3.5 0 0 1 4.95 4.95'
        'L10.13 18.5a2 2 0 0 1-2.83-2.83l7.78-7.78"></path>',
        size,
    )


def alerta_triangulo(size=16):
    return _svg(
        '<path d="M10.29 3.86 1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0Z"></path>'
        '<line x1="12" y1="9" x2="12" y2="13"></line>'
        '<line x1="12" y1="17" x2="12.01" y2="17"></line>',
        size,
    )


def ojo(size=15):
    return _svg(
        '<path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8Z"></path>'
        '<circle cx="12" cy="12" r="3"></circle>',
        size,
    )


def flecha_izquierda(size=14):
    return _svg(
        '<line x1="19" y1="12" x2="5" y2="12"></line>'
        '<polyline points="12 19 5 12 12 5"></polyline>',
        size,
    )


def caja_vacia(size=24):
    return _svg(
        '<polyline points="22 12 16 12 14 15 10 15 8 12 2 12"></polyline>'
        '<path d="M5.45 5.11 2 12v6a2 2 0 0 0 2 2h16a2 2 0 0 0 2-2v-6l-3.45-6.89A2 2 0 0 0 16.76 4H7.24a2 2 0 0 0-1.79 1.11Z"></path>',
        size,
    )


def equis(size=14):
    return _svg(
        '<line x1="18" y1="6" x2="6" y2="18"></line>'
        '<line x1="6" y1="6" x2="18" y2="18"></line>',
        size,
    )
