"""
FitVerse — Relational Database Models

Defines the PostgreSQL schema for merchants, products, and size variants.
Supports both upper-body garments (tops/hoodies/blazers) and lower-body
garments (trousers/shorts) with database-level CHECK constraints.
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
            "garment_group IN ('upper_body', 'lower_body')",
            name="ck_product_garment_group",
        ),
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
    garment_group: Mapped[str] = mapped_column(
        String(20), nullable=False, default="upper_body", server_default="upper_body"
    )
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
        # Upper-body range constraints (when present)
        CheckConstraint(
            "chest_circumference IS NULL OR (chest_circumference >= 20 AND chest_circumference <= 100)",
            name="ck_size_chest_range",
        ),
        CheckConstraint(
            "shoulder_width IS NULL OR (shoulder_width >= 5 AND shoulder_width <= 40)",
            name="ck_size_shoulder_range",
        ),
        CheckConstraint(
            "body_length IS NULL OR (body_length >= 10 AND body_length <= 50)",
            name="ck_size_body_length_range",
        ),
        CheckConstraint(
            "sleeve_length IS NULL OR (sleeve_length >= 5 AND sleeve_length <= 50)",
            name="ck_size_sleeve_length_range",
        ),
        # Lower-body range constraints (when present)
        CheckConstraint(
            "waist_circumference IS NULL OR (waist_circumference >= 20 AND waist_circumference <= 80)",
            name="ck_size_waist_range",
        ),
        CheckConstraint(
            "hip_circumference IS NULL OR (hip_circumference >= 24 AND hip_circumference <= 90)",
            name="ck_size_hip_range",
        ),
        CheckConstraint(
            "inseam_length IS NULL OR (inseam_length >= 10 AND inseam_length <= 45)",
            name="ck_size_inseam_range",
        ),
        # Ensure each row has either a complete upper-body set or a complete lower-body set
        CheckConstraint(
            "("
            "  (chest_circumference IS NOT NULL AND shoulder_width IS NOT NULL AND body_length IS NOT NULL AND sleeve_length IS NOT NULL)"
            "  OR "
            "  (waist_circumference IS NOT NULL AND hip_circumference IS NOT NULL AND inseam_length IS NOT NULL)"
            ")",
            name="ck_size_complete_measurement_set",
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

    # Upper-body garment measurements (inches)
    chest_circumference: Mapped[float | None] = mapped_column(Float, nullable=True)
    shoulder_width: Mapped[float | None] = mapped_column(Float, nullable=True)
    body_length: Mapped[float | None] = mapped_column(Float, nullable=True)
    sleeve_length: Mapped[float | None] = mapped_column(Float, nullable=True)

    # Lower-body garment measurements (inches)
    waist_circumference: Mapped[float | None] = mapped_column(Float, nullable=True)
    hip_circumference: Mapped[float | None] = mapped_column(Float, nullable=True)
    inseam_length: Mapped[float | None] = mapped_column(Float, nullable=True)

    stock_quantity: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    is_available: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    product: Mapped["Product"] = relationship(back_populates="sizes")


# ============================================================
# 4. SHOPPER AVATAR PROFILES & SAVED LOOKS
# ============================================================

class ShopperProfile(Base):
    __tablename__ = "shopper_profiles"
    __table_args__ = (
        CheckConstraint(
            "avatar_preset IN ('slim', 'athletic', 'average', 'curvy', 'broad')",
            name="ck_shopper_avatar_preset",
        ),
        CheckConstraint(
            "height_inches IS NULL OR (height_inches >= 48 AND height_inches <= 90)",
            name="ck_shopper_height_range",
        ),
        CheckConstraint(
            "chest_circumference >= 20 AND chest_circumference <= 80",
            name="ck_shopper_chest_range",
        ),
        CheckConstraint(
            "shoulder_width >= 10 AND shoulder_width <= 30",
            name="ck_shopper_shoulder_range",
        ),
        CheckConstraint(
            "preferred_body_length >= 15 AND preferred_body_length <= 40",
            name="ck_shopper_body_length_range",
        ),
        CheckConstraint(
            "preferred_sleeve_length >= 10 AND preferred_sleeve_length <= 40",
            name="ck_shopper_sleeve_length_range",
        ),
        CheckConstraint(
            "waist_circumference IS NULL OR (waist_circumference >= 20 AND waist_circumference <= 70)",
            name="ck_shopper_waist_range",
        ),
        CheckConstraint(
            "hip_circumference IS NULL OR (hip_circumference >= 24 AND hip_circumference <= 80)",
            name="ck_shopper_hip_range",
        ),
        CheckConstraint(
            "preferred_inseam_length IS NULL OR (preferred_inseam_length >= 15 AND preferred_inseam_length <= 42)",
            name="ck_shopper_inseam_range",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    external_shopper_id: Mapped[str] = mapped_column(
        String(150), unique=True, nullable=False, index=True
    )
    display_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    avatar_preset: Mapped[str] = mapped_column(
        String(30), nullable=False, default="average", server_default="average"
    )
    height_inches: Mapped[float | None] = mapped_column(Float, nullable=True)

    # Upper-body measurements (inches)
    chest_circumference: Mapped[float] = mapped_column(Float, nullable=False)
    shoulder_width: Mapped[float] = mapped_column(Float, nullable=False)
    preferred_body_length: Mapped[float] = mapped_column(Float, nullable=False)
    preferred_sleeve_length: Mapped[float] = mapped_column(Float, nullable=False)

    # Optional lower-body measurements (inches)
    waist_circumference: Mapped[float | None] = mapped_column(Float, nullable=True)
    hip_circumference: Mapped[float | None] = mapped_column(Float, nullable=True)
    preferred_inseam_length: Mapped[float | None] = mapped_column(Float, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False
    )

    saved_looks: Mapped[list["SavedLook"]] = relationship(
        back_populates="shopper",
        cascade="all, delete-orphan",
    )


class SavedLook(Base):
    __tablename__ = "saved_looks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    shopper_id: Mapped[int] = mapped_column(
        ForeignKey("shopper_profiles.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    look_name: Mapped[str] = mapped_column(String(150), nullable=False)
    notes: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )

    shopper: Mapped["ShopperProfile"] = relationship(back_populates="saved_looks")
    items: Mapped[list["SavedLookItem"]] = relationship(
        back_populates="saved_look",
        cascade="all, delete-orphan",
    )


class SavedLookItem(Base):
    __tablename__ = "saved_look_items"
    __table_args__ = (
        UniqueConstraint("saved_look_id", "product_id", name="uq_saved_look_product"),
        CheckConstraint(
            "fit_preference IN ('regular', 'relaxed', 'oversized')",
            name="ck_saved_look_item_fit_preference",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    saved_look_id: Mapped[int] = mapped_column(
        ForeignKey("saved_looks.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    product_id: Mapped[int] = mapped_column(
        ForeignKey("products.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    fit_preference: Mapped[str] = mapped_column(
        String(20), nullable=False, default="relaxed"
    )
    recommended_size: Mapped[str] = mapped_column(String(20), nullable=False)

    saved_look: Mapped["SavedLook"] = relationship(back_populates="items")
    product: Mapped["Product"] = relationship()