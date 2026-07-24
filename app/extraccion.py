from pathlib import Path

from sqlalchemy import cast
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Session

from app import models
from extract_invoices import process_invoice


def _volcar_extraccion(db: Session, documento: models.Documento, resultado: dict) -> None:
    """Actualiza los campos del documento y crea sus datos extraídos y
    relaciones a partir del resultado de process_invoice(). Asume que
    `documento` no tiene ya datos_extraidos/relaciones asociados.
    """
    documento.emisor = resultado["emisor"]
    documento.tipo_documento = resultado["tipo_documento"]
    documento.tipo_gasto = resultado["tipo_gasto"]
    documento.estado = resultado["estado"]

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


def procesar_y_guardar(db: Session, ruta_pdf: Path, archivo_origen: str) -> models.Documento:
    """Ejecuta el Módulo de Extracción (3.3) sobre un PDF recién subido y
    crea el documento junto con sus datos extraídos y relaciones (7.1, 7.10).
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

    _volcar_extraccion(db, documento, resultado)

    db.commit()
    db.refresh(documento)
    return documento


def reprocesar_documento(db: Session, documento: models.Documento) -> models.Documento:
    """Vuelve a ejecutar la extracción sobre un documento ya guardado (por
    ejemplo, uno subido antes de que existiera este módulo), sustituyendo
    sus datos extraídos y relaciones anteriores.

    Lanza FileNotFoundError si el PDF original ya no existe en el disco
    (por ejemplo, tras perderse el disco de Render en un incidente) — quien
    llama a esta función decide si eso debe detener un lote completo o solo
    saltarse ese documento.
    """
    ruta = Path(documento.ruta_almacenamiento)
    if not ruta.exists():
        raise FileNotFoundError(f"El PDF original ya no existe en el disco: {ruta}")

    resultado = process_invoice(ruta)

    db.query(models.RelacionDocumento).filter_by(documento_id=documento.id).delete()
    db.query(models.DatoExtraido).filter_by(documento_id=documento.id).delete()
    db.flush()

    _volcar_extraccion(db, documento, resultado)

    db.commit()
    db.refresh(documento)
    return documento
