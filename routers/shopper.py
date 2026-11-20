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
from models import Product, SavedLook, ShopperProfile
from recommendation import recommend_bottom_size, recommend_size
from repositories.product_repo import (
    get_product_by_id,
    list_active_catalog_products,
    to_recommendation_garment_dict,
)
from repositories.shopper_repo import (
    create_saved_look,
    delete_saved_look,
    get_saved_look_by_id,
    get_shopper_by_external_id,
    list_saved_looks_for_shopper,
    upsert_shopper_profile,
)

from schemas import (
    CatalogProductRead,
    OutfitTryOnRequest,
    OutfitTryOnResponse,
    SavedLookCreate,
    SavedLookItemRead,
    SavedLookRead,
    ShopperProfileRead,
    ShopperProfileUpsert,
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
    dispatches to the upper- or lower-body deterministic engine, and maps the
    result to a shopper-safe response.
    """
    garment_dict = to_recommendation_garment_dict(product, only_available=True)

    if not garment_dict["sizes"]:
        return ShopperRecommendationResponse(
            status="out_of_stock",
            product_sku=garment_dict["product_id"],
            product_name=garment_dict["product_name"],
            garment_group=product.garment_group,  # type: ignore[arg-type]
            data_status=garment_dict["data_status"],
            fit_preference=fit_preference,
            recommended_size=None,
            other_acceptable_sizes=[],
            avatar_fit_zones=None,
            shopper_message="All sizes for this garment are currently out of stock.",
        )

    engine_fn = (
        recommend_bottom_size
        if product.garment_group == "lower_body"
        else recommend_size
    )

    try:
        raw_result = engine_fn(
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
    category: str | None = Query(default=None, description="Filter by garment category (e.g., hoodie, shirt, blazer, trousers)"),
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
                garment_group=prod.garment_group,
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
    response_model_exclude_none=True,
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
    response_model_exclude_none=True,
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

def _serialize_saved_look(look: SavedLook) -> SavedLookRead:
    return SavedLookRead(
        id=look.id,
        shopper_id=look.shopper_id,
        look_name=look.look_name,
        notes=look.notes,
        items=[
            SavedLookItemRead(
                id=item.id,
                product_id=item.product_id,
                product_sku=item.product.external_sku,
                product_name=item.product.name,
                category=item.product.category,
                garment_group=item.product.garment_group,
                thumbnail_url=item.product.thumbnail_url,
                model_asset_url=item.product.model_asset_url,
                fit_preference=item.fit_preference,
                recommended_size=item.recommended_size,
            )
            for item in look.items
        ],
    )


def _profile_to_body_dict(profile: ShopperProfile) -> dict:
    return {
        "chest_circumference": profile.chest_circumference,
        "shoulder_width": profile.shoulder_width,
        "preferred_body_length": profile.preferred_body_length,
        "preferred_sleeve_length": profile.preferred_sleeve_length,
        "waist_circumference": profile.waist_circumference,
        "hip_circumference": profile.hip_circumference,
        "preferred_inseam_length": profile.preferred_inseam_length,
    }


@router.put(
    "/shoppers/{external_shopper_id}/profile",
    response_model=ShopperProfileRead,
)
def save_shopper_avatar_profile(
    external_shopper_id: str,
    payload: ShopperProfileUpsert,
    db: Session = Depends(get_db),
):
    """Create or update a shopper's 3D avatar preset and body measurements."""
    if not external_shopper_id.strip():
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="external_shopper_id cannot be blank.",
        )
    return upsert_shopper_profile(db, external_shopper_id, payload)


@router.get(
    "/shoppers/{external_shopper_id}/profile",
    response_model=ShopperProfileRead,
)
def fetch_shopper_avatar_profile(
    external_shopper_id: str,
    db: Session = Depends(get_db),
):
    """Retrieve a shopper's saved 3D avatar preset and body measurements."""
    profile = get_shopper_by_external_id(db, external_shopper_id)
    if not profile:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Shopper profile '{external_shopper_id}' not found.",
        )
    return profile


@router.post(
    "/shoppers/{external_shopper_id}/looks",
    response_model=SavedLookRead,
    status_code=status.HTTP_201_CREATED,
)
def save_shopper_look(
    external_shopper_id: str,
    payload: SavedLookCreate,
    db: Session = Depends(get_db),
):
    """
    Evaluate each garment against the shopper's saved profile and persist
    the complete outfit ('Save Look') with recommended sizes.
    """
    profile = get_shopper_by_external_id(db, external_shopper_id)
    if not profile:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Shopper profile '{external_shopper_id}' not found. Save a profile first.",
        )

    body_dict = _profile_to_body_dict(profile)
    resolved_items: list[dict] = []

    for item in payload.items:
        product = get_product_by_id(db, item.product_id)
        if not product:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Product with id {item.product_id} not found.",
            )

        rec = _evaluate_product_for_shopper(product, body_dict, item.fit_preference)
        if rec.status != "success" or not rec.recommended_size:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail=(
                    f"Cannot save look: '{product.name}' has status '{rec.status}' "
                    "for your saved measurements."
                ),
            )

        resolved_items.append(
            {
                "product_id": product.id,
                "fit_preference": item.fit_preference,
                "recommended_size": rec.recommended_size,
            }
        )

    saved = create_saved_look(
        db=db,
        shopper_id=profile.id,
        look_name=payload.look_name,
        notes=payload.notes,
        resolved_items=resolved_items,
    )
    return _serialize_saved_look(saved)


@router.get(
    "/shoppers/{external_shopper_id}/looks",
    response_model=list[SavedLookRead],
)
def list_shopper_looks(
    external_shopper_id: str,
    db: Session = Depends(get_db),
):
    """Reload all saved outfits for a shopper with product asset URLs."""
    profile = get_shopper_by_external_id(db, external_shopper_id)
    if not profile:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Shopper profile '{external_shopper_id}' not found.",
        )
    looks = list_saved_looks_for_shopper(db, profile.id)
    return [_serialize_saved_look(look) for look in looks]


@router.delete(
    "/shoppers/{external_shopper_id}/looks/{look_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def remove_shopper_look(
    external_shopper_id: str,
    look_id: int,
    db: Session = Depends(get_db),
):
    """Delete one of the shopper's saved outfits."""
    profile = get_shopper_by_external_id(db, external_shopper_id)
    if not profile:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Shopper profile '{external_shopper_id}' not found.",
        )
    look = get_saved_look_by_id(db, look_id)
    if not look or look.shopper_id != profile.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Saved look {look_id} not found for this shopper.",
        )
    delete_saved_look(db, look)