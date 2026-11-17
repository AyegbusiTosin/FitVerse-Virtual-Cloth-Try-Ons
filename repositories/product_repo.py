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
    if the size_label does not exist yet.
    """
    target = next(
        (s for s in product.sizes if s.size_label == size_input.size_label),
        None,
    )

    if target:
        target.chest_circumference = size_input.chest_circumference
        target.shoulder_width = size_input.shoulder_width
        target.body_length = size_input.body_length
        target.sleeve_length = size_input.sleeve_length
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
            stock_quantity=size_input.stock_quantity,
            is_available=size_input.is_available,
        )
        db.add(target)

    db.commit()
    db.refresh(target)
    return target


# ============================================================
# 3. ENGINE ADAPTER (ORM -> recommendation.py Contract)
# ============================================================

def to_recommendation_garment_dict(
    product: Product,
    only_available: bool = True,
) -> dict:
    """
    Adapt a SQLAlchemy Product + ProductSize collection into the exact
    dictionary structure expected by recommendation.recommend_size().

    Why this adapter exists:
    - Keeps recommendation.py completely decoupled from SQLAlchemy models.
    - Allows filtering out-of-stock sizes before size evaluation.
    """
    sizes_map: dict[str, dict[str, float]] = {}

    for size in product.sizes:
        if only_available and (not size.is_available or size.stock_quantity <= 0):
            continue

        sizes_map[size.size_label] = {
            "chest_circumference": size.chest_circumference,
            "shoulder_width": size.shoulder_width,
            "body_length": size.body_length,
            "sleeve_length": size.sleeve_length,
        }

    return {
        "product_id": product.external_sku,
        "product_name": product.name,
        "category": product.category,
        "data_status": product.data_status,
        "unit": product.unit,
        "sizes": sizes_map,
    }