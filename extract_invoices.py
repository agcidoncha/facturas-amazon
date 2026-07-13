"""
Módulo de Extracción de Facturas de Amazon (prototipo MVP)
============================================================

Implementa el diseño de la sección 3.3 de la arquitectura:
- No asume estructura fija: cada factura puede aportar campos distintos.
- Cada dato extraído guarda: campo, valor, origen, confianza, si necesita revisión.
- El PDF original nunca se modifica (fuente de verdad, sección 3.2).
- Detecta duplicados por huella (hash) del PDF.
- Distingue emisor (Amazon EU SARL / Amazon Online Spain) y tipo de documento
  (factura / nota de crédito), sin depender de un único idioma de etiquetas.

Este script NO se conecta a Amazon (eso es el módulo de Conexión, sección 3.1,
que se integrará más adelante). Trabaja sobre PDFs ya descargados en disco.
"""

import hashlib
import json
import re
import sys
from pathlib import Path

import pdfplumber

# ---------------------------------------------------------------------------
# Utilidades básicas
# ---------------------------------------------------------------------------

def compute_hash(path: Path) -> str:
    """Huella única del PDF, para detección de duplicados (sección 3.2 / 7.11)."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        h.update(f.read())
    return h.hexdigest()


def extract_text(path: Path) -> str:
    """Extrae todo el texto del PDF, página a página."""
    text_parts = []
    with pdfplumber.open(path) as pdf:
        for page in pdf.pages:
            t = page.extract_text() or ""
            text_parts.append(t)
    return "\n".join(text_parts)


def make_field(field, value, origin, confidence=1.0, needs_review=False):
    """Estructura estándar de cada dato extraído (condición 3, sección 2)."""
    return {
        "campo": field,
        "valor": value,
        "origen": origin,
        "confianza": round(confidence, 2),
        "necesita_revision": needs_review,
    }


# ---------------------------------------------------------------------------
# Detección de emisor y tipo de documento (multi-idioma)
# ---------------------------------------------------------------------------

def detect_issuer(text: str) -> str:
    if re.search(r"Amazon Online Spain", text, re.IGNORECASE):
        return "Amazon Online Spain, S.L.U. (Ads)"
    if re.search(r"Amazon EU", text, re.IGNORECASE):
        return "Amazon EU S.à r.l., Sucursal en España"
    return "Desconocido"


def detect_document_type(text: str) -> str:
    credit_note_markers = [
        "NOTA DE CR\u00c9DITO", "TAX CREDIT NOTE", "GUTSCHRIFT", "NOTE DE CR\u00c9DIT",
    ]
    for marker in credit_note_markers:
        if marker.upper() in text.upper():
            return "nota_de_credito"
    return "factura"


# ---------------------------------------------------------------------------
# Extracción de campos comunes (multi-idioma: ES / EN / DE / FR)
# ---------------------------------------------------------------------------

# Cada entrada: (nombre_campo, [ (idioma, patron_regex) ... ])
COMMON_FIELD_PATTERNS = {
    "numero_documento": [
        ("es", r"N[u\u00fa]mero de nota de cr[e\u00e9]dito[:\s]*([A-Z0-9\-]+)"),
        ("es", r"N[u\u00fa]mero de (?:la )?factura(?!\s+original)[:\s]*([A-Z0-9\-]+)"),
        ("en", r"Invoice Number[:\s]*([A-Z0-9\-]+)"),
        ("de", r"Rechnungsnummer[:\s]*([A-Z0-9\-]+)"),
        ("fr", r"Facture n[\u00b0o][:\s]*([A-Z0-9\-]+)"),
    ],
    "fecha_documento": [
        ("es", r"Fecha de (?:la )?factura[:\s]*(\d{2}[/\-]\d{2}[/\-]\d{4})"),
        ("es", r"Fecha de emisi[o\u00f3]n de la nota de cr[e\u00e9]dito[:\s]*(\d{2}[/\-]\d{2}[/\-]\d{4})"),
        ("en", r"Invoice Date[:\s]*(\d{2}[/\-]\d{2}[/\-]\d{4})"),
        ("de", r"Rechnungsdatum[:\s]*(\d{2}[/\-]\d{2}[/\-]\d{4})"),
        ("fr", r"Date de la facture[:\s]*(\d{2}[/\-]\d{2}[/\-]\d{4})"),
    ],
    "periodo": [
        ("es", r"Periodo de facturaci[o\u00f3]n[:\s]*([\d/\-]+\s*(?:to|a)\s*[\d/\-]+)"),
        ("es", r"Per[i\u00ed]odo de nota de cr[e\u00e9]dito[:\s]*([\d/\-]+\s*to\s*[\d/\-]+)"),
        ("en", r"Invoice Period[:\s]*([\d/\-]+\s*to\s*[\d/\-]+)"),
        ("de", r"Rechnungszeitraum[:\s]*([\d/\-]+\s*to\s*[\d/\-]+)"),
        ("fr", r"P[e\u00e9]riode de facturation[:\s]*([\d/\-]+\s*to\s*[\d/\-]+)"),
    ],
    "moneda": [
        ("es", r"Moneda de la factura[:\s]*([A-Z]{3})"),
        ("en", r"Invoice Currency[:\s]*([A-Z]{3})"),
    ],
    "nif_vendedor": [
        ("es", r"N[u\u00fa]mero de IVA del vendedor:?\s*\n?\s*(ES[A-Z0-9]+)"),
        ("es", r"N[u\u00fa]mero de impuesto\s*\n?\s*(ES[A-Z0-9]+)"),
        ("de", r"UStID des Leistungsempf[a\u00e4]ngers:?\s*\n?\s*(ES[A-Z0-9]+)"),
        ("fr", r"Num[e\u00e9]ro de TVA intracommunautaire:?\s*\n?\s*(ES[A-Z0-9]+)"),
    ],
}

TOTAL_PATTERNS = {
    "importe_total": [
        ("es", r"Importe Total a Pagar\s*([\-\d.,]+)\s*EUR"),
        ("es", r"Importe de factura adeudado\s*([\-\d.,]+)\s*EUR"),
        ("en", r"Invoice Amount Due\s*([\-\d.,]+)\s*EUR"),
        ("de", r"Gesamtsumme\s*EUR\s*([\-\d.,]+)\s*EUR\s*([\-\d.,]+)\s*EUR\s*([\-\d.,]+)"),
        ("es_simple", r"^Total\s+EUR\s*([\-\d.,]+)\s+EUR\s*[\-\d.,]+\s+EUR\s*([\-\d.,]+)$"),
    ],
    "iva": [
        ("es", r"VAT\s*\(21%\)\s*-\s*SPAIN\s*([\-\d.,]+)\s*EUR"),
    ],
    "base_imponible": [
        ("es", r"Subtotal\s*([\-\d.,]+)\s*EUR"),
    ],
}


def try_patterns(text, patterns):
    """Devuelve (valor, idioma) del primer patrón que haga match, o (None, None)."""
    for lang, pattern in patterns:
        m = re.search(pattern, text, re.IGNORECASE | re.MULTILINE)
        if m:
            return m.group(1).strip(), lang
    return None, None


def normalizar_fecha(fecha_cruda):
    """Convierte una fecha con separador '/' o '-' (tal como la escriba
    Amazon según el idioma del documento) a un formato único AAAA-MM-DD,
    sin sustituir el valor crudo (sección 7.4: se guarda aparte)."""
    if not fecha_cruda:
        return None
    partes = re.split(r"[/\-]", fecha_cruda.strip())
    if len(partes) != 3:
        return None
    dia, mes, anio = partes
    if not (dia.isdigit() and mes.isdigit() and anio.isdigit() and len(anio) == 4):
        return None
    return f"{anio}-{mes.zfill(2)}-{dia.zfill(2)}"


def extract_common_fields(text):
    fields = []
    for field_name, patterns in COMMON_FIELD_PATTERNS.items():
        value, lang = try_patterns(text, patterns)
        if value:
            fields.append(make_field(
                field_name, value,
                origin=f"etiqueta detectada ({lang})",
                confidence=0.95,
            ))
            if field_name == "fecha_documento":
                normalizada = normalizar_fecha(value)
                if normalizada:
                    fields.append(make_field(
                        "fecha_documento_normalizada", normalizada,
                        origin="normalizado desde fecha_documento",
                        confidence=0.95,
                    ))
        else:
            fields.append(make_field(
                field_name, None, origin="no encontrado",
                confidence=0.0, needs_review=True,
            ))
    return fields


def extract_totals(text):
    fields = []
    for field_name, patterns in TOTAL_PATTERNS.items():
        value = None
        lang = None
        for l, pattern in patterns:
            m = re.search(pattern, text, re.IGNORECASE | re.MULTILINE)
            if m:
                # algunos patrones tienen varios grupos; nos quedamos con el último
                value = m.groups()[-1]
                lang = l
                break
        if value:
            fields.append(make_field(field_name, value, origin=f"tabla resumen ({lang})", confidence=0.9))
    return fields


# ---------------------------------------------------------------------------
# Extracción específica: facturas simples de Amazon EU SARL (una sola línea)
# ---------------------------------------------------------------------------

# Mapeo de códigos internos de Amazon a texto legible (no sustituye al dato
# crudo, se añade como campo adicional "concepto_normalizado" — sección 7.8:
# el concepto original siempre se conserva tal cual).
MAPEO_CONCEPTOS = {
    "ais_selling_on_amazon_fees_text": "Tarifas de vender en Amazon",
    "ais_fulfillment_by_amazon_fees_text": "Tarifas de logística de Amazon (FBA)",
    "ais_refunded_fees_text": "Tarifas reembolsadas",
}


def normalizar_concepto(concepto_crudo):
    if not concepto_crudo:
        return None
    clave = concepto_crudo.strip().lower()
    return MAPEO_CONCEPTOS.get(clave)

def extract_eu_sarl_line_item(text):
    """
    Las facturas de Amazon EU SARL traen una única línea de concepto:
    Descripción | Precio (sin IVA) | % IVA | IVA | Total

    Algunos PDFs parten el texto del concepto en dos líneas, con la fila de
    importes insertada en medio (quirk de extracción por columnas). Si la
    línea siguiente a los importes no parece ser un total, se añade como
    continuación del concepto.
    """
    fields = []
    # Concepto: puede ser código interno (ais_xxx_text) o texto legible
    m = re.search(r"\n([A-Za-z_][\w \"'/áéíóúñÁÉÍÓÚÑ]+)\s+(-?)EUR\s*([\d.,]+)\s*(\d+\.\d+)%\s*(-?)EUR\s*([\d.,]+)\s*(-?)EUR\s*([\d.,]+)", text)
    if m:
        concepto, sign_base, base, iva_pct, sign_iva, iva, sign_total, total = m.groups()
        concepto = concepto.strip()

        # ¿Continúa el concepto en la línea siguiente? (quirk de columnas)
        resto_texto = text[m.end():]
        siguiente_linea = resto_texto.split("\n", 2)[1] if resto_texto.count("\n") >= 1 else ""
        siguiente_linea = siguiente_linea.strip()
        if siguiente_linea and not re.match(r"^(Gesamtsumme|Total|Subtotal)", siguiente_linea, re.IGNORECASE) \
                and "EUR" not in siguiente_linea:
            concepto = f"{concepto} {siguiente_linea}"

        base_val = f"-{base}" if sign_base else base
        iva_val = f"-{iva}" if sign_iva else iva
        total_val = f"-{total}" if sign_total else total
        fields.append(make_field("concepto", concepto, origin="línea de detalle", confidence=0.9))
        concepto_norm = normalizar_concepto(concepto)
        if concepto_norm:
            fields.append(make_field("concepto_normalizado", concepto_norm, origin="mapeo interno de códigos Amazon", confidence=0.85))
        fields.append(make_field("base_imponible", base_val, origin="línea de detalle", confidence=0.95))
        fields.append(make_field("porcentaje_iva", iva_pct, origin="línea de detalle", confidence=0.95))
        fields.append(make_field("iva", iva_val, origin="línea de detalle", confidence=0.95))
        fields.append(make_field("importe_total", total_val, origin="línea de detalle", confidence=0.95))
    else:
        fields.append(make_field("concepto", None, origin="no encontrado", confidence=0.0, needs_review=True))
    return fields


# ---------------------------------------------------------------------------
# Extracción específica: facturas de Amazon Ads (desglose por portfolio)
# ---------------------------------------------------------------------------

def extract_ads_portfolio_breakdown(text):
    """
    Extrae la tabla 'Resumen de cargos del portafolio' / 'Summary of Portfolio Charges'.
    Devuelve una lista de {nombre_portfolio, importe}, marcada como dato anidado
    (no encaja en la vista por defecto, pero queda disponible para consultas).
    """
    portfolios = []
    lines = text.splitlines()
    capture = False
    for line in lines:
        if re.search(r"(Nombre del portafolio|Portfolio name)\s+(Importe|Amount)", line, re.IGNORECASE):
            capture = True
            continue
        if capture:
            m = re.match(r"^(.*?)\s+([\-\d.,]+)\s*EUR$", line.strip())
            if m and "Total" not in m.group(1):
                portfolios.append({"nombre_portfolio": m.group(1).strip(), "importe_eur": m.group(2)})
            elif "Total" in line or line.strip() == "":
                capture = False
    return portfolios


def extract_ads_summary(text):
    """Campos de resumen específicos de las facturas de publicidad (Ads)."""
    fields = []
    patterns = {
        "total_cargos_campana": [
            (r"Cargos Totales De La Campa[n\u00f1]a\s*([\-\d.,]+)\s*EUR"),
            (r"Total Campaign charges\s*([\-\d.,]+)\s*EUR"),
        ],
        "total_ajustes": [
            (r"Ajustes Totales\s*([\-\d.,]+)\s*EUR"),
            (r"Total Adjustments\s*([\-\d.,]+)\s*EUR"),
        ],
        "total_tarifas_regulatorias": [
            (r"Total de tarifas publicitarias regulatorias\s*([\-\d.,]+)\s*EUR"),
            (r"Total Regulatory Advertising Fees\s*([\-\d.,]+)\s*EUR"),
        ],
    }
    for field_name, pats in patterns.items():
        for pat in pats:
            m = re.search(pat, text, re.IGNORECASE)
            if m:
                fields.append(make_field(field_name, m.group(1), origin="tabla resumen Ads", confidence=0.9))
                break
    return fields


# ---------------------------------------------------------------------------
# Extracción específica: notas de crédito (referencias a facturas originales)
# ---------------------------------------------------------------------------

def extract_credit_note_references(text):
    fields = []
    m = re.search(r"N[u\u00fa]mero de factura original\s*\n((?:[A-Z0-9\-]+\s*\n?)+)", text)
    if m:
        block = m.group(1)
        # Solo líneas que parecen números de factura reales (con dígitos y longitud mínima)
        refs = [
            r.strip() for r in block.splitlines()
            if r.strip() and len(r.strip()) >= 5 and any(ch.isdigit() for ch in r)
        ]
        fields.append(make_field(
            "facturas_originales_referenciadas", refs,
            origin="sección 'Número de factura original'", confidence=0.95,
        ))
    return fields


# ---------------------------------------------------------------------------
# Determinación del "tipo de gasto" para la vista por defecto (sección 7.7/7.8)
# ---------------------------------------------------------------------------

def determine_tipo_gasto(issuer, doc_type, eu_sarl_concepto):
    if doc_type == "nota_de_credito":
        return "Nota de crédito"
    if issuer.startswith("Amazon Online Spain"):
        return "Publicidad (Amazon Ads)"
    if eu_sarl_concepto:
        return eu_sarl_concepto  # se guarda tal cual, sin categorizar (decisión 7.8)
    return "Sin determinar"


# ---------------------------------------------------------------------------
# Proceso principal por factura
# ---------------------------------------------------------------------------

def process_invoice(path: Path) -> dict:
    file_hash = compute_hash(path)
    text = extract_text(path)

    issuer = detect_issuer(text)
    doc_type = detect_document_type(text)

    fields = []
    fields += extract_common_fields(text)

    eu_sarl_concepto = None
    eu_sarl_concepto_norm = None
    if issuer.startswith("Amazon EU"):
        line_item_fields = extract_eu_sarl_line_item(text)
        fields += line_item_fields
        for f in line_item_fields:
            if f["campo"] == "concepto":
                eu_sarl_concepto = f["valor"]
            if f["campo"] == "concepto_normalizado":
                eu_sarl_concepto_norm = f["valor"]
    else:
        fields += extract_totals(text)
        fields += extract_ads_summary(text)

    extra_data = {}
    if issuer.startswith("Amazon Online Spain"):
        portfolios = extract_ads_portfolio_breakdown(text)
        if portfolios:
            extra_data["desglose_por_portfolio"] = portfolios

    if doc_type == "nota_de_credito":
        fields += extract_credit_note_references(text)

    # Para el tipo de gasto mostrado se prefiere el concepto normalizado
    # (más legible), pero el dato crudo siempre queda disponible en "campos".
    tipo_gasto = determine_tipo_gasto(issuer, doc_type, eu_sarl_concepto_norm or eu_sarl_concepto)

    # Nivel de confianza global: si algún campo clave falta, marcar revisión.
    # No se comprueban TODOS los campos (ej. "moneda" o "periodo" no aparecen
    # nunca en las facturas simples de Amazon EU SARL, y contarlos dejaría
    # esas facturas marcadas como "necesita revisión" permanentemente, sin
    # aportar ninguna señal útil). Solo los campos realmente imprescindibles
    # para la contabilidad: número, fecha e importe total. Si alguno de ellos
    # ni siquiera aparece en "campos" (algunos extractores solo añaden el
    # campo cuando lo encuentran), también cuenta como pendiente de revisión.
    campos_criticos = ["numero_documento", "fecha_documento", "importe_total"]
    campos_por_nombre = {f["campo"]: f for f in fields}
    necesita_revision_global = any(
        campos_por_nombre[c]["necesita_revision"] if c in campos_por_nombre else True
        for c in campos_criticos
    )

    return {
        "archivo_origen": path.name,
        "huella_sha256": file_hash,
        "emisor": issuer,
        "tipo_documento": doc_type,
        "tipo_gasto": tipo_gasto,
        "estado": "necesita revisión" if necesita_revision_global else "revisado",
        "campos": fields,
        "datos_adicionales": extra_data,
    }


def main(input_dir: str, output_json: str):
    input_path = Path(input_dir)
    results = []
    seen_hashes = {}

    for pdf_file in sorted(input_path.glob("*.pdf")):
        result = process_invoice(pdf_file)
        h = result["huella_sha256"]
        if h in seen_hashes:
            print(f"[duplicado detectado, se omite] {pdf_file.name} == {seen_hashes[h]}")
            continue
        seen_hashes[h] = pdf_file.name
        results.append(result)
        print(f"[procesado] {pdf_file.name} -> {result['emisor']} / {result['tipo_documento']} / {result['estado']}")

    with open(output_json, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    print(f"\nTotal procesadas: {len(results)}. Guardado en {output_json}")
    return results


if __name__ == "__main__":
    input_dir = sys.argv[1] if len(sys.argv) > 1 else "/mnt/user-data/uploads"
    output_json = sys.argv[2] if len(sys.argv) > 2 else "/home/claude/extraction/facturas_extraidas.json"
    main(input_dir, output_json)
