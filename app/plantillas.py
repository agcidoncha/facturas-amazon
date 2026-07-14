# Páginas que pertenecen al módulo de Facturas. Solo dentro de estas se
# muestra la navegación propia del módulo ("Ver facturas" / "Subir
# facturas") — en la portada (o en un futuro módulo distinto) no tiene
# sentido ver los enlaces de un módulo que no es el que se está viendo.
PAGINAS_MODULO_FACTURAS = {"facturas", "subir"}


def pagina(titulo: str, contenido: str, activo: str = "") -> str:
    """Envuelve el contenido de cada pantalla con la misma cabecera y
    navegación, para que todas las páginas se vean coherentes (desktop,
    tablet y móvil) y el estilo se pueda cambiar en un único sitio
    (app/static/estilo.css)."""

    def marca(nombre: str) -> str:
        return ' aria-current="page"' if nombre == activo else ""

    nav = ""
    if activo in PAGINAS_MODULO_FACTURAS:
        nav = f"""
    <nav class="nav-principal">
      <a href="/facturas"{marca("facturas")}>Ver facturas</a>
      <a href="/subir"{marca("subir")}>Subir facturas</a>
    </nav>"""

    return f"""<!doctype html>
<html lang="es">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{titulo} · Melopido</title>
<link rel="stylesheet" href="/static/estilo.css">
</head>
<body>
<header class="cabecera">
  <div class="contenedor">
    <a class="titulo-app" href="/">Melopido</a>{nav}
  </div>
</header>
<main class="contenedor">
{contenido}
</main>
<script>
  document.querySelectorAll(".toast").forEach(function (el) {{
    setTimeout(function () {{ el.remove(); }}, 3200);
  }});
</script>
</body>
</html>"""
