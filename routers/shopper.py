"""
FitVerse — Shopper Catalog & Virtual Try-On Router

Responsibilities:
1. Serve the public storefront garment catalog (with 3D/2D asset URLs).
2. Recommend sizes and avatar drape zones for single garments (/api/recommend-size).
3. Evaluate multi-garment 'My Look' outfits (/api/try-on/look) against a
   shopper's body profile while strictly hiding internal merchant diagnostics.
"""

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from cloth_data import SAMPLE_HOODIE
from database import get_db
from models import Product
from recommendation import recommend_size
from repositories.product_repo import (
    get_product_by_id,
    list_active_catalog_products,
    to_recommendation_garment_dict,
)
from schemas import (
    CatalogProductRead,
    OutfitTryOnRequest,
    OutfitTryOnResponse,
    ShopperRecommendationResponse,
    SizeRecommendationRequest,
    build_shopper_response,
)

router = APIRouter(prefix="/api", tags=["Shopper Catalog & Virtual Try-On"])


def _evaluate_product_for_shopper(
    product: Product,
    body_dict: dict,
    fit_preference: str,
) -> ShopperRecommendationResponse:
    """
    Shared helper that adapts a PostgreSQL Product, checks stock availability,
    runs the deterministic engine, and maps the result to a shopper-safe response.
    """
    garment_dict = to_recommendation_garment_dict(product, only_available=True)

    if not garment_dict["sizes"]:
        return ShopperRecommendationResponse(
            status="out_of_stock",
            product_sku=garment_dict["product_id"],
            product_name=garment_dict["product_name"],
            data_status=garment_dict["data_status"],
            fit_preference=fit_preference,
            recommended_size=None,
            other_acceptable_sizes=[],
            avatar_fit_zones=None,
            shopper_message="All sizes for this garment are currently out of stock.",
        )

    try:
        raw_result = recommend_size(
            body=body_dict,
            garment_data=garment_dict,
            fit_preference=fit_preference,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc

    return build_shopper_response(raw_result)


@router.get(
    "/catalog/products",
    response_model=list[CatalogProductRead],
)
def get_storefront_catalog(
    category: str | None = Query(default=None, description="Filter by garment category (e.g., hoodie, shirt, blazer)"),
    merchant_id: int | None = Query(default=None, gt=0, description="Filter by merchant ID"),
    db: Session = Depends(get_db),
):
    """
    List active garments available for the React virtual try-on catalog.
    """
    products = list_active_catalog_products(db, category=category, merchant_id=merchant_id)

    catalog: list[CatalogProductRead] = []
    for prod in products:
        available_labels = [
            s.size_label
            for s in prod.sizes
            if s.is_available and s.stock_quantity > 0
        ]
        catalog.append(
            CatalogProductRead(
                id=prod.id,
                merchant_id=prod.merchant_id,
                external_sku=prod.external_sku,
                name=prod.name,
                category=prod.category,
                data_status=prod.data_status,
                thumbnail_url=prod.thumbnail_url,
                model_asset_url=prod.model_asset_url,
                available_sizes=available_labels,
            )
        )

    return catalog


@router.post(
    "/recommend-size",
    response_model=ShopperRecommendationResponse,
)
def get_size_recommendation(
    request: SizeRecommendationRequest,
    db: Session = Depends(get_db),
):
    """
    Recommend a garment size for a shopper (and return avatar fit zones)
    without exposing internal scoring or merchant diagnostics.
    """
    body_dict = request.body.model_dump()

    if request.product_id is not None:
        product = get_product_by_id(db, request.product_id)
        if not product:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Product with id {request.product_id} not found.",
            )
        return _evaluate_product_for_shopper(product, body_dict, request.fit_preference)

    try:
        raw_result = recommend_size(
            body=body_dict,
            garment_data=SAMPLE_HOODIE,
            fit_preference=request.fit_preference,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc

    return build_shopper_response(raw_result)


@router.post(
    "/try-on/look",
    response_model=OutfitTryOnResponse,
)
def evaluate_outfit_look(
    request: OutfitTryOnRequest,
    db: Session = Depends(get_db),
):
    """
    Evaluate a multi-garment 'My Look' combination against a shopper's body profile
    and return per-item size recommendations + avatar drape zones.
    """
    body_dict = request.body.model_dump()
    recommendations: list[ShopperRecommendationResponse] = []

    for item in request.items:
        product = get_product_by_id(db, item.product_id)
        if not product:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Product with id {item.product_id} not found.",
            )

        rec = _evaluate_product_for_shopper(product, body_dict, item.fit_preference)
        recommendations.append(rec)

    return OutfitTryOnResponse(
        total_items=len(recommendations),
        recommendations=recommendations,
    )