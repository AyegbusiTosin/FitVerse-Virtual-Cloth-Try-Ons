"""
FitVerse — Relational Database Models

Defines the PostgreSQL schema for merchants, products, and size variants.
Database-level CHECK constraints mirror the garment validation bounds
enforced in recommendation.py.
"""

from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from database import Base


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class Merchant(Base):
    __tablename__ = "merchants"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(150), nullable=False)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    storefront_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )

    products: Mapped[list["Product"]] = relationship(
        back_populates="merchant",
        cascade="all, delete-orphan",
    )


class Product(Base):
    __tablename__ = "products"
    __table_args__ = (
        UniqueConstraint("merchant_id", "external_sku", name="uq_merchant_product_sku"),
        CheckConstraint(
            "data_status IN ('VERIFIED', 'SAMPLE_NOT_VERIFIED', 'PENDING_REVIEW')",
            name="ck_product_data_status",
        ),
        CheckConstraint(
            "unit IN ('inches', 'cm')",
            name="ck_product_unit",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    merchant_id: Mapped[int] = mapped_column(
        ForeignKey("merchants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    external_sku: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    category: Mapped[str] = mapped_column(String(50), nullable=False, default="hoodie")
    data_status: Mapped[str] = mapped_column(
        String(30), nullable=False, default="PENDING_REVIEW"
    )
    unit: Mapped[str] = mapped_column(String(10), nullable=False, default="inches")

    # Visual assets for the React mannequin/avatar try-on UI
    thumbnail_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    model_asset_url: Mapped[str | None] = mapped_column(String(500), nullable=True)

    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False
    )

    merchant: Mapped["Merchant"] = relationship(back_populates="products")
    sizes: Mapped[list["ProductSize"]] = relationship(
        back_populates="product",
        cascade="all, delete-orphan",
    )


class ProductSize(Base):
    __tablename__ = "product_sizes"
    __table_args__ = (
        UniqueConstraint("product_id", "size_label", name="uq_product_size_label"),
        # Mirror validate_garment_data() bounds from recommendation.py
        CheckConstraint(
            "chest_circumference >= 20 AND chest_circumference <= 100",
            name="ck_size_chest_range",
        ),
        CheckConstraint(
            "shoulder_width >= 5 AND shoulder_width <= 40",
            name="ck_size_shoulder_range",
        ),
        CheckConstraint(
            "body_length >= 10 AND body_length <= 50",
            name="ck_size_body_length_range",
        ),
        CheckConstraint(
            "sleeve_length >= 5 AND sleeve_length <= 50",
            name="ck_size_sleeve_length_range",
        ),
        CheckConstraint(
            "stock_quantity >= 0",
            name="ck_size_stock_non_negative",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    product_id: Mapped[int] = mapped_column(
        ForeignKey("products.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    size_label: Mapped[str] = mapped_column(String(20), nullable=False)

    # Garment measurements in product.unit (default: inches)
    chest_circumference: Mapped[float] = mapped_column(Float, nullable=False)
    shoulder_width: Mapped[float] = mapped_column(Float, nullable=False)
    body_length: Mapped[float] = mapped_column(Float, nullable=False)
    sleeve_length: Mapped[float] = mapped_column(Float, nullable=False)

    stock_quantity: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    is_available: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    product: Mapped["Product"] = relationship(back_populates="sizes")