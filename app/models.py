from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, ForeignKey, Numeric, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


class Documento(Base):
    """Un PDF descargado (sección 3.2). Es el ancla de todo lo demás."""

    __tablename__ = "documentos"

    id: Mapped[int] = mapped_column(primary_key=True)
    huella_sha256: Mapped[str] = mapped_column(Text, unique=True, index=True)
    archivo_origen: Mapped[str] = mapped_column(Text)
    ruta_almacenamiento: Mapped[str] = mapped_column(Text)
    emisor: Mapped[str] = mapped_column(Text)
    tipo_documento: Mapped[str] = mapped_column(Text)
    tipo_gasto: Mapped[str | None] = mapped_column(Text, nullable=True)
    estado: Mapped[str] = mapped_column(Text)
    fecha_carga: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    campos: Mapped[list["DatoExtraido"]] = relationship(
        back_populates="documento", cascade="all, delete-orphan"
    )
    relaciones: Mapped[list["RelacionDocumento"]] = relationship(
        foreign_keys="RelacionDocumento.documento_id",
        back_populates="documento",
        cascade="all, delete-orphan",
    )


class DatoExtraido(Base):
    """Tabla flexible campo-valor (sección 3.3). Un campo nuevo no exige migrar nada."""

    __tablename__ = "datos_extraidos"

    id: Mapped[int] = mapped_column(primary_key=True)
    documento_id: Mapped[int] = mapped_column(ForeignKey("documentos.id", ondelete="CASCADE"))
    campo: Mapped[str] = mapped_column(Text)
    valor: Mapped[dict | list | str | float | None] = mapped_column(JSONB, nullable=True)
    origen: Mapped[str | None] = mapped_column(Text, nullable=True)
    confianza: Mapped[float | None] = mapped_column(Numeric(3, 2), nullable=True)
    necesita_revision: Mapped[bool] = mapped_column(Boolean, default=False)

    documento: Mapped["Documento"] = relationship(back_populates="campos")


class RelacionDocumento(Base):
    """Enlaza una nota de crédito con su(s) factura(s) original(es) (secciones 7.1, 7.10).

    documento_referenciado_id queda en NULL si la factura original todavía
    no se ha subido al sistema (puede ser de un periodo anterior).
    """

    __tablename__ = "relaciones_documentos"

    id: Mapped[int] = mapped_column(primary_key=True)
    documento_id: Mapped[int] = mapped_column(ForeignKey("documentos.id", ondelete="CASCADE"))
    tipo_relacion: Mapped[str] = mapped_column(Text)
    numero_factura_referenciada: Mapped[str] = mapped_column(Text)
    documento_referenciado_id: Mapped[int | None] = mapped_column(
        ForeignKey("documentos.id"), nullable=True
    )

    documento: Mapped["Documento"] = relationship(
        foreign_keys=[documento_id], back_populates="relaciones"
    )
