"""
FitVerse — Product Data Access Layer (Repository)

Responsibilities:
1. Encapsulate all SQLAlchemy queries for merchants, products, and sizes.
2. Translate ORM entities into the pure Python dictionary contract
   expected by recommendation.py, keeping the engine 100% DB-agnostic.
"""

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from models import Merchant, Product, ProductSize
from schemas import MerchantCreate, ProductCreate, ProductSizeInput


class ConflictError(Exception):
    """Raised when a unique database constraint would be violated."""


# ============================================================
# 1. MERCHANT QUERIES
# ============================================================

def get_merchant_by_id(db: Session, merchant_id: int) -> Merchant | None:
    stmt = select(Merchant).where(Merchant.id == merchant_id, Merchant.is_active.is_(True))
    return db.scalars(stmt).first()


def get_merchant_by_email(db: Session, email: str) -> Merchant | None:
    stmt = select(Merchant).where(Merchant.email == email)
    return db.scalars(stmt).first()


def create_merchant(db: Session, payload: MerchantCreate) -> Merchant:
    existing = get_merchant_by_email(db, payload.email)
    if existing:
        raise ConflictError(f"A merchant with email '{payload.email}' already exists.")

    merchant = Merchant(
        name=payload.name.strip(),
        email=payload.email.strip().lower(),
        storefront_url=payload.storefront_url,
        is_active=True,
    )
    db.add(merchant)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise ConflictError("Merchant could not be created due to a uniqueness conflict.") from exc

    db.refresh(merchant)
    return merchant


# ============================================================
# 2. PRODUCT & SIZE QUERIES
# ============================================================

def get_product_by_id(db: Session, product_id: int) -> Product | None:
    """
    Fetch an active product along with all its size variants in one eager load.
    """
    stmt = (
        select(Product)
        .options(selectinload(Product.sizes))
        .where(Product.id == product_id, Product.is_active.is_(True))
    )
    return db.scalars(stmt).first()


def get_product_by_sku(
    db: Session,
    merchant_id: int,
    external_sku: str,
) -> Product | None:
    """
    Fetch a merchant's product by its external SKU (e.g., 'sample-hoodie-001').
    """
    stmt = (
        select(Product)
        .options(selectinload(Product.sizes))
        .where(
            Product.merchant_id == merchant_id,
            Product.external_sku == external_sku,
            Product.is_active.is_(True),
        )
    )
    return db.scalars(stmt).first()


def list_products_by_merchant(db: Session, merchant_id: int) -> list[Product]:
    stmt = (
        select(Product)
        .options(selectinload(Product.sizes))
        .where(Product.merchant_id == merchant_id, Product.is_active.is_(True))
        .order_by(Product.id.asc())
    )
    return list(db.scalars(stmt).all())

def create_product_with_sizes(
    db: Session,
    merchant_id: int,
    payload: ProductCreate,
) -> Product:
    existing = get_product_by_sku(db, merchant_id, payload.external_sku.strip())
    if existing:
        raise ConflictError(
            f"Product SKU '{payload.external_sku}' already exists for merchant {merchant_id}."
        )

    product = Product(
        merchant_id=merchant_id,
        external_sku=payload.external_sku.strip(),
        name=payload.name.strip(),
        category=payload.category.strip().lower(),
        garment_group=payload.garment_group,
        data_status=payload.data_status,
        unit=payload.unit,
        thumbnail_url=payload.thumbnail_url,
        model_asset_url=payload.model_asset_url,
        is_active=True,
    )

    for size_in in payload.sizes:
        product.sizes.append(
            ProductSize(
                size_label=size_in.size_label,
                chest_circumference=size_in.chest_circumference,
                shoulder_width=size_in.shoulder_width,
                body_length=size_in.body_length,
                sleeve_length=size_in.sleeve_length,
                waist_circumference=size_in.waist_circumference,
                hip_circumference=size_in.hip_circumference,
                inseam_length=size_in.inseam_length,
                stock_quantity=size_in.stock_quantity,
                is_available=size_in.is_available,
            )
        )

    db.add(product)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise ConflictError("Product could not be created due to a constraint conflict.") from exc

    return get_product_by_id(db, product.id)  # type: ignore[return-value]


def upsert_product_size(
    db: Session,
    product: Product,
    size_input: ProductSizeInput,
) -> ProductSize:
    """
    Update an existing size variant on a product, or insert a new one
    if the size_label does not exist yet. Validates measurement group match.
    """
    if product.garment_group == "upper_body" and (
        not size_input.has_complete_upper() or size_input.has_any_lower()
    ):
        raise ValueError(
            "Upper-body products require all 4 upper measurements and no lower measurements."
        )
    if product.garment_group == "lower_body" and (
        not size_input.has_complete_lower() or size_input.has_any_upper()
    ):
        raise ValueError(
            "Lower-body products require all 3 lower measurements and no upper measurements."
        )

    target = next(
        (s for s in product.sizes if s.size_label == size_input.size_label),
        None,
    )

    if target:
        target.chest_circumference = size_input.chest_circumference
        target.shoulder_width = size_input.shoulder_width
        target.body_length = size_input.body_length
        target.sleeve_length = size_input.sleeve_length
        target.waist_circumference = size_input.waist_circumference
        target.hip_circumference = size_input.hip_circumference
        target.inseam_length = size_input.inseam_length
        target.stock_quantity = size_input.stock_quantity
        target.is_available = size_input.is_available
    else:
        target = ProductSize(
            product_id=product.id,
            size_label=size_input.size_label,
            chest_circumference=size_input.chest_circumference,
            shoulder_width=size_input.shoulder_width,
            body_length=size_input.body_length,
            sleeve_length=size_input.sleeve_length,
            waist_circumference=size_input.waist_circumference,
            hip_circumference=size_input.hip_circumference,
            inseam_length=size_input.inseam_length,
            stock_quantity=size_input.stock_quantity,
            is_available=size_input.is_available,
        )
        db.add(target)

    db.commit()
    db.refresh(target)
    return target


def to_recommendation_garment_dict(
    product: Product,
    only_available: bool = True,
) -> dict:
    """
    Adapt a SQLAlchemy Product + ProductSize collection into the exact
    dictionary structure expected by recommendation.recommend_size() or
    recommendation.recommend_bottom_size().
    """
    sizes_map: dict[str, dict[str, float]] = {}

    for size in product.sizes:
        if only_available and (not size.is_available or size.stock_quantity <= 0):
            continue

        if product.garment_group == "lower_body":
            sizes_map[size.size_label] = {
                "waist_circumference": size.waist_circumference,  # type: ignore[dict-item]
                "hip_circumference": size.hip_circumference,      # type: ignore[dict-item]
                "inseam_length": size.inseam_length,              # type: ignore[dict-item]
            }
        else:
            sizes_map[size.size_label] = {
                "chest_circumference": size.chest_circumference,  # type: ignore[dict-item]
                "shoulder_width": size.shoulder_width,            # type: ignore[dict-item]
                "body_length": size.body_length,                  # type: ignore[dict-item]
                "sleeve_length": size.sleeve_length,              # type: ignore[dict-item]
            }

    return {
        "product_id": product.external_sku,
        "product_name": product.name,
        "category": product.category,
        "garment_group": product.garment_group,
        "data_status": product.data_status,
        "unit": product.unit,
        "sizes": sizes_map,
    }

def list_active_catalog_products(
    db: Session,
    category: str | None = None,
    merchant_id: int | None = None,
) -> list[Product]:
    """
    Fetch active products for the public storefront catalog, optionally
    filtered by garment category or merchant_id.
    """
    stmt = (
        select(Product)
        .options(selectinload(Product.sizes))
        .where(Product.is_active.is_(True))
        .order_by(Product.id.asc())
    )

    if merchant_id is not None:
        stmt = stmt.where(Product.merchant_id == merchant_id)

    if category is not None:
        stmt = stmt.where(Product.category == category.strip().lower())

    return list(db.scalars(stmt).all())

# ============================================================
# 3. ENGINE ADAPTER (ORM -> recommendation.py Contract)
# ============================================================

def to_recommendation_garment_dict(
    product: Product,
    only_available: bool = True,
) -> dict:
    """
    Adapt a SQLAlchemy Product + ProductSize collection into the exact
    dictionary structure expected by recommendation.recommend_size() or
    recommendation.recommend_bottom_size().
    """
    sizes_map: dict[str, dict[str, float]] = {}

    for size in product.sizes:
        if only_available and (not size.is_available or size.stock_quantity <= 0):
            continue

        if product.garment_group == "lower_body":
            sizes_map[size.size_label] = {
                "waist_circumference": size.waist_circumference,  # type: ignore[dict-item]
                "hip_circumference": size.hip_circumference,      # type: ignore[dict-item]
                "inseam_length": size.inseam_length,              # type: ignore[dict-item]
            }
        else:
            sizes_map[size.size_label] = {
                "chest_circumference": size.chest_circumference,  # type: ignore[dict-item]
                "shoulder_width": size.shoulder_width,            # type: ignore[dict-item]
                "body_length": size.body_length,                  # type: ignore[dict-item]
                "sleeve_length": size.sleeve_length,              # type: ignore[dict-item]
            }

    return {
        "product_id": product.external_sku,
        "product_name": product.name,
        "category": product.category,
        "garment_group": product.garment_group,
        "data_status": product.data_status,
        "unit": product.unit,
        "sizes": sizes_map,
    }