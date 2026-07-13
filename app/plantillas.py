def pagina(titulo: str, contenido: str, activo: str = "") -> str:
    """Envuelve el contenido de cada pantalla con la misma cabecera y
    navegación, para que todas las páginas se vean coherentes (desktop,
    tablet y móvil) y el estilo se pueda cambiar en un único sitio
    (app/static/estilo.css)."""

    def marca(nombre: str) -> str:
        return ' aria-current="page"' if nombre == activo else ""

    return f"""<!doctype html>
<html lang="es">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{titulo} · Facturas Amazon</title>
<link rel="stylesheet" href="/static/estilo.css">
</head>
<body>
<header class="cabecera">
  <div class="contenedor">
    <a class="titulo-app" href="/facturas">Facturas Amazon</a>
    <nav class="nav-principal">
      <a href="/facturas"{marca("facturas")}>Ver facturas</a>
      <a href="/subir"{marca("subir")}>Subir facturas</a>
    </nav>
  </div>
</header>
<main class="contenedor">
{contenido}
</main>
</body>
</html>"""
