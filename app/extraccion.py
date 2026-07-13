from pathlib import Path

from sqlalchemy import cast
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Session

from app import models
from extract_invoices import process_invoice


def procesar_y_guardar(db: Session, ruta_pdf: Path, archivo_origen: str) -> models.Documento:
    """Ejecuta el Módulo de Extracción (3.3) sobre un PDF ya guardado en disco
    y persiste el resultado: el documento, sus campos extraídos, y las
    relaciones con facturas originales si es una nota de crédito (7.1, 7.10).
    """
    resultado = process_invoice(ruta_pdf)

    documento = models.Documento(
        huella_sha256=resultado["huella_sha256"],
        archivo_origen=archivo_origen,
        ruta_almacenamiento=str(ruta_pdf),
        emisor=resultado["emisor"],
        tipo_documento=resultado["tipo_documento"],
        tipo_gasto=resultado["tipo_gasto"],
        estado=resultado["estado"],
    )
    db.add(documento)
    db.flush()  # asigna documento.id sin cerrar la transacción todavía

    referencias_notas_credito = []
    for campo in resultado["campos"]:
        db.add(models.DatoExtraido(
            documento_id=documento.id,
            campo=campo["campo"],
            valor=campo["valor"],
            origen=campo["origen"],
            confianza=campo["confianza"],
            necesita_revision=campo["necesita_revision"],
        ))
        if campo["campo"] == "facturas_originales_referenciadas" and campo["valor"]:
            referencias_notas_credito = campo["valor"]

    for campo_extra, valor_extra in resultado.get("datos_adicionales", {}).items():
        db.add(models.DatoExtraido(
            documento_id=documento.id,
            campo=campo_extra,
            valor=valor_extra,
            origen="datos adicionales",
            confianza=0.85,
            necesita_revision=False,
        ))

    for numero_ref in referencias_notas_credito:
        referenciado = (
            db.query(models.DatoExtraido)
            .filter(
                models.DatoExtraido.campo == "numero_documento",
                models.DatoExtraido.valor == cast(numero_ref, JSONB),
            )
            .first()
        )
        db.add(models.RelacionDocumento(
            documento_id=documento.id,
            tipo_relacion="nota_de_credito_de",
            numero_factura_referenciada=numero_ref,
            documento_referenciado_id=referenciado.documento_id if referenciado else None,
        ))

    db.commit()
    db.refresh(documento)
    return documento
