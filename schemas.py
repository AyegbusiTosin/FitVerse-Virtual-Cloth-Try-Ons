"""
FitVerse — API Request & Response Schemas

Enforces strict boundaries between:
1. Public shopper-facing responses (including qualitative fit zones
   for the React 3D mannequin/avatar UI).
2. Internal merchant-facing diagnostics and sizing analytics.
"""

from typing import Literal
from pydantic import BaseModel, Field, field_validator


# ============================================================
# 1. SHOPPER INPUT SCHEMAS (Aligned with recommendation.py bounds)
# ============================================================

class BodyProfile(BaseModel):
    """
    Shopper body and garment-length preferences in inches.
    Bounds match validate_body_profile() in recommendation.py so
    out-of-range values fail cleanly with HTTP 422 at the API boundary.
    """

    chest_circumference: float = Field(
        ge=20.0,
        le=80.0,
        description="Body chest circumference in inches (20–80).",
    )
    shoulder_width: float = Field(
        ge=10.0,
        le=30.0,
        description="Body shoulder width in inches (10–30).",
    )
    preferred_body_length: float = Field(
        ge=15.0,
        le=40.0,
        description="Desired garment body length in inches (15–40).",
    )
    preferred_sleeve_length: float = Field(
        ge=10.0,
        le=40.0,
        description="Desired garment sleeve length in inches (10–40).",
    )


class SizeRecommendationRequest(BaseModel):
    """
    Request payload for sizing recommendation.
    Accepts an optional product_id to evaluate a database-backed garment;
    falls back to the unverified sample garment if omitted during testing.
    """

    product_id: int | None = Field(
        default=None,
        gt=0,
        description="Database ID of the merchant product to evaluate.",
    )
    body: BodyProfile
    fit_preference: Literal["regular", "relaxed", "oversized"] = "relaxed"


# ============================================================
# 2. SHOPPER-FACING RESPONSE SCHEMAS (No Internal Diagnostics)
# ============================================================

class AvatarFitZones(BaseModel):
    """
    Qualitative drape/fit descriptors per body zone for the React 3D avatar.
    Translates raw ease metrics into visual cues without exposing internal
    scoring formulas or exact ease calculations.
    """

    chest: Literal["snug", "true_to_size", "relaxed", "oversized"]
    shoulders: Literal["snug", "true_to_size", "relaxed", "dropped"]
    body_length: Literal["cropped", "standard", "long"]
    sleeve_length: Literal["short", "standard", "long"]


class ShopperRecommendationResponse(BaseModel):
    """
    Public API response returned to storefronts and the React avatar UI.
    Strictly excludes internal scores, ease numbers, and merchant diagnostics.
    """

    status: Literal["success", "no_matching_size", "out_of_stock"]
    product_sku: str
    product_name: str
    data_status: str
    fit_preference: str
    recommended_size: str | None = None
    other_acceptable_sizes: list[str] = Field(default_factory=list)
    avatar_fit_zones: AvatarFitZones | None = None
    shopper_message: str


# ============================================================
# 3. MERCHANT-FACING DIAGNOSTIC SCHEMAS
# ============================================================

class FitMetricsDiagnostic(BaseModel):
    chest_ease: float
    shoulder_ease: float
    body_length_difference: float
    sleeve_length_difference: float
    chest_is_acceptable: bool
    shoulder_is_acceptable: bool
    body_length_is_acceptable: bool
    sleeve_length_is_acceptable: bool
    is_acceptable: bool
    score: float


class SizeCandidateDiagnostic(BaseModel):
    size: str
    fit: FitMetricsDiagnostic


class InvalidSizeDiagnostic(BaseModel):
    size: str
    reason: str


class MerchantDiagnosticResponse(BaseModel):
    """
    Internal merchant dashboard payload containing full ease calculations,
    normalized ranking scores, rejected candidates, and data integrity warnings.
    """

    status: Literal["success", "no_matching_size"]
    product_id: str
    product_name: str
    data_status: str
    fit_preference: str
    recommended_size: str | None = None
    fit_details: FitMetricsDiagnostic | None = None
    explanation: str | None = None
    message: str | None = None
    other_acceptable_sizes: list[str] = Field(default_factory=list)
    closest_candidates: list[SizeCandidateDiagnostic] = Field(default_factory=list)
    invalid_sizes: list[InvalidSizeDiagnostic] = Field(default_factory=list)


# ============================================================
# 4. SHOPPER RESPONSE MAPPER (Boundary Translator)
# ============================================================

def _classify_chest_ease(ease: float) -> Literal["snug", "true_to_size", "relaxed", "oversized"]:
    if ease < 2.5:
        return "snug"
    if ease <= 5.0:
        return "true_to_size"
    if ease <= 8.5:
        return "relaxed"
    return "oversized"


def _classify_shoulder_ease(ease: float) -> Literal["snug", "true_to_size", "relaxed", "dropped"]:
    if ease < 0.0:
        return "snug"
    if ease <= 1.5:
        return "true_to_size"
    if ease <= 3.5:
        return "relaxed"
    return "dropped"


def _classify_length_diff(diff: float, short_label: str) -> str:
    if diff < -0.75:
        return short_label
    if diff <= 0.75:
        return "standard"
    return "long"


def build_shopper_response(engine_result: dict) -> ShopperRecommendationResponse:
    """
    Convert the raw dictionary returned by recommendation.recommend_size()
    into a shopper-safe ShopperRecommendationResponse.
    """
    status = engine_result["status"]

    if status != "success":
        return ShopperRecommendationResponse(
            status="no_matching_size",
            product_sku=engine_result["product_id"],
            product_name=engine_result["product_name"],
            data_status=engine_result["data_status"],
            fit_preference=engine_result["fit_preference"],
            recommended_size=None,
            other_acceptable_sizes=[],
            avatar_fit_zones=None,
            shopper_message=(
                "None of the available sizes match your selected fit preference "
                "and measurements. Try switching your fit preference or reviewing "
                "another style."
            ),
        )

    fit = engine_result["fit_details"]
    rec_size = engine_result["recommended_size"]
    pref = engine_result["fit_preference"]

    zones = AvatarFitZones(
        chest=_classify_chest_ease(fit["chest_ease"]),
        shoulders=_classify_shoulder_ease(fit["shoulder_ease"]),
        body_length=_classify_length_diff(fit["body_length_difference"], "cropped"),
        sleeve_length=_classify_length_diff(fit["sleeve_length_difference"], "short"),
    )

    return ShopperRecommendationResponse(
        status="success",
        product_sku=engine_result["product_id"],
        product_name=engine_result["product_name"],
        data_status=engine_result["data_status"],
        fit_preference=pref,
        recommended_size=rec_size,
        other_acceptable_sizes=engine_result.get("other_acceptable_sizes", []),
        avatar_fit_zones=zones,
        shopper_message=(
            f"Size {rec_size} is our best match for your {pref} fit preference."
        ),
    )

# ============================================================
# 5. MERCHANT & PRODUCT MANAGEMENT SCHEMAS
# ============================================================

class MerchantCreate(BaseModel):
    name: str = Field(min_length=2, max_length=150)
    email: str = Field(min_length=5, max_length=255)
    storefront_url: str | None = Field(default=None, max_length=500)


class MerchantRead(BaseModel):
    id: int
    name: str
    email: str
    storefront_url: str | None
    is_active: bool

    model_config = {"from_attributes": True}


class ProductSizeInput(BaseModel):
    """
    Input schema for creating or updating a single garment size variant.
    Bounds mirror validate_garment_data() in recommendation.py and
    PostgreSQL CHECK constraints in models.py.
    """

    size_label: str = Field(min_length=1, max_length=20)
    chest_circumference: float = Field(ge=20.0, le=100.0)
    shoulder_width: float = Field(ge=5.0, le=40.0)
    body_length: float = Field(ge=10.0, le=50.0)
    sleeve_length: float = Field(ge=5.0, le=50.0)
    stock_quantity: int = Field(default=10, ge=0)
    is_available: bool = True

    @field_validator("size_label")
    @classmethod
    def normalize_size_label(cls, value: str) -> str:
        cleaned = value.strip().upper()
        if not cleaned:
            raise ValueError("size_label cannot be blank.")
        return cleaned


class ProductSizeRead(BaseModel):
    id: int
    size_label: str
    chest_circumference: float
    shoulder_width: float
    body_length: float
    sleeve_length: float
    stock_quantity: int
    is_available: bool

    model_config = {"from_attributes": True}


class ProductCreate(BaseModel):
    external_sku: str = Field(min_length=1, max_length=100)
    name: str = Field(min_length=2, max_length=200)
    category: str = Field(default="hoodie", min_length=2, max_length=50)
    data_status: Literal["VERIFIED", "SAMPLE_NOT_VERIFIED", "PENDING_REVIEW"] = "VERIFIED"
    unit: Literal["inches", "cm"] = "inches"
    thumbnail_url: str | None = Field(default=None, max_length=500)
    model_asset_url: str | None = Field(default=None, max_length=500)
    sizes: list[ProductSizeInput] = Field(min_length=1)

    @field_validator("sizes")
    @classmethod
    def ensure_unique_size_labels(cls, sizes: list[ProductSizeInput]) -> list[ProductSizeInput]:
        seen: set[str] = set()
        for item in sizes:
            if item.size_label in seen:
                raise ValueError(f"Duplicate size_label '{item.size_label}' in product sizes.")
            seen.add(item.size_label)
        return sizes


class ProductRead(BaseModel):
    id: int
    merchant_id: int
    external_sku: str
    name: str
    category: str
    data_status: str
    unit: str
    thumbnail_url: str | None
    model_asset_url: str | None
    is_active: bool
    sizes: list[ProductSizeRead]

    model_config = {"from_attributes": True}


# ============================================================
# 6. PUBLIC STOREFRONT CATALOG & MULTI-GARMENT TRY-ON SCHEMAS
# ============================================================

class CatalogProductRead(BaseModel):
    """
    Shopper-safe product representation for the React virtual try-on UI.
    Exposes visual assets and available size labels without leaking
    exact merchant inventory counts or raw garment size matrices.
    """

    id: int
    merchant_id: int
    external_sku: str
    name: str
    category: str
    data_status: str
    thumbnail_url: str | None
    model_asset_url: str | None
    available_sizes: list[str]


class OutfitItemRequest(BaseModel):
    product_id: int = Field(gt=0)
    fit_preference: Literal["regular", "relaxed", "oversized"] = "relaxed"


class OutfitTryOnRequest(BaseModel):
    """
    Evaluate multiple layered garments ('My Look') against a single
    shopper body profile for the 3D avatar try-on experience.
    """

    body: BodyProfile
    items: list[OutfitItemRequest] = Field(min_length=1, max_length=5)


class OutfitTryOnResponse(BaseModel):
    status: Literal["success"] = "success"
    total_items: int
    recommendations: list[ShopperRecommendationResponse]