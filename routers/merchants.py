"""
FitVerse — Merchant Product & Diagnostics Router

Responsibilities:
1. Merchant account registration and catalog management (PostgreSQL-backed).
2. Size matrix creation and per-size measurement/stock updates without code changes.
3. Internal merchant-only fit diagnostics endpoint (exposing ease metrics,
   scores, rejected candidates, and data integrity warnings).
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from database import get_db
from recommendation import recommend_bottom_size, recommend_size
from repositories.product_repo import (
    ConflictError,
    create_merchant,
    create_product_with_sizes,
    get_merchant_by_id,
    get_product_by_id,
    list_products_by_merchant,
    to_recommendation_garment_dict,
    upsert_product_size,
)
from schemas import (
    BodyProfile,
    MerchantCreate,
    MerchantDiagnosticResponse,
    MerchantRead,
    ProductCreate,
    ProductRead,
    ProductSizeInput,
    ProductSizeRead,
)

router = APIRouter(prefix="/api", tags=["Merchant Management & Diagnostics"])


@router.post(
    "/merchants",
    response_model=MerchantRead,
    status_code=status.HTTP_201_CREATED,
)
def register_merchant(
    payload: MerchantCreate,
    db: Session = Depends(get_db),
):
    """Create a new merchant account."""
    try:
        return create_merchant(db, payload)
    except ConflictError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc


@router.post(
    "/merchants/{merchant_id}/products",
    response_model=ProductRead,
    status_code=status.HTTP_201_CREATED,
)
def create_merchant_product(
    merchant_id: int,
    payload: ProductCreate,
    db: Session = Depends(get_db),
):
    """Create a new product and its size chart for a merchant."""
    merchant = get_merchant_by_id(db, merchant_id)
    if not merchant:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Merchant with id {merchant_id} not found.",
        )

    try:
        return create_product_with_sizes(db, merchant_id, payload)
    except ConflictError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc


@router.get(
    "/merchants/{merchant_id}/products",
    response_model=list[ProductRead],
)
def get_merchant_catalog(
    merchant_id: int,
    db: Session = Depends(get_db),
):
    """List all active products and size charts for a merchant."""
    merchant = get_merchant_by_id(db, merchant_id)
    if not merchant:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Merchant with id {merchant_id} not found.",
        )

    return list_products_by_merchant(db, merchant_id)


@router.put(
    "/products/{product_id}/sizes/{size_label}",
    response_model=ProductSizeRead,
)
def update_or_add_product_size(
    product_id: int,
    size_label: str,
    payload: ProductSizeInput,
    db: Session = Depends(get_db),
):
    """
    Add or update a single size variant's measurements or stock on a product.
    """
    normalized_path_label = size_label.strip().upper()
    if normalized_path_label != payload.size_label:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                f"Path size_label '{normalized_path_label}' does not match "
                f"payload size_label '{payload.size_label}'."
            ),
        )

    product = get_product_by_id(db, product_id)
    if not product:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Product with id {product_id} not found.",
        )

    try:
        return upsert_product_size(db, product, payload)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc


@router.post(
    "/merchants/products/{product_id}/diagnose",
    response_model=MerchantDiagnosticResponse,
)
def diagnose_product_fit(
    product_id: int,
    body: BodyProfile,
    fit_preference: str = "relaxed",
    include_out_of_stock: bool = True,
    db: Session = Depends(get_db),
):
    """
    Merchant-only diagnostic endpoint.
    Exposes internal ease calculations, scores, rejected size candidates,
    and invalid size warnings that are strictly hidden from shoppers.
    """
    product = get_product_by_id(db, product_id)
    if not product:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Product with id {product_id} not found.",
        )

    garment_dict = to_recommendation_garment_dict(
        product,
        only_available=not include_out_of_stock,
    )

    engine_fn = (
        recommend_bottom_size
        if product.garment_group == "lower_body"
        else recommend_size
    )

    try:
        raw_result = engine_fn(
            body=body.model_dump(),
            garment_data=garment_dict,
            fit_preference=fit_preference,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc

    return MerchantDiagnosticResponse(**raw_result)