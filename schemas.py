"""
FitVerse — API Request & Response Schemas

Enforces strict boundaries between:
1. Public shopper-facing responses (including qualitative fit zones
   for the React 3D mannequin/avatar UI across upper & lower body).
2. Internal merchant-facing diagnostics and sizing analytics.
"""

from typing import Literal
from pydantic import BaseModel, Field, field_validator, model_validator


# ============================================================
# 1. SHOPPER INPUT SCHEMAS
# ============================================================

class BodyProfile(BaseModel):
    """
    Shopper body and garment-length preferences in inches.
    Upper-body measurements are required; lower-body measurements are
    optional unless trying on a lower-body garment (e.g., trousers).
    """

    chest_circumference: float = Field(ge=20.0, le=80.0)
    shoulder_width: float = Field(ge=10.0, le=30.0)
    preferred_body_length: float = Field(ge=15.0, le=40.0)
    preferred_sleeve_length: float = Field(ge=10.0, le=40.0)

    # Optional lower-body measurements for trousers/bottoms
    waist_circumference: float | None = Field(default=None, ge=20.0, le=70.0)
    hip_circumference: float | None = Field(default=None, ge=24.0, le=80.0)
    preferred_inseam_length: float | None = Field(default=None, ge=15.0, le=42.0)


class SizeRecommendationRequest(BaseModel):
    product_id: int | None = Field(default=None, gt=0)
    body: BodyProfile
    fit_preference: Literal["regular", "relaxed", "oversized"] = "relaxed"


# ============================================================
# 2. SHOPPER-FACING RESPONSE SCHEMAS (No Internal Diagnostics)
# ============================================================

class AvatarFitZones(BaseModel):
    """
    Qualitative drape/fit descriptors per body zone for the React 3D avatar.
    Populates upper-body zones for tops and lower-body zones for trousers.
    """

    # Upper-body zones
    chest: Literal["snug", "true_to_size", "relaxed", "oversized"] | None = None
    shoulders: Literal["snug", "true_to_size", "relaxed", "dropped"] | None = None
    body_length: Literal["cropped", "standard", "long"] | None = None
    sleeve_length: Literal["short", "standard", "long"] | None = None

    # Lower-body zones
    waist: Literal["snug", "true_to_size", "relaxed", "oversized"] | None = None
    hips: Literal["snug", "true_to_size", "relaxed", "oversized"] | None = None
    inseam: Literal["short", "standard", "long"] | None = None


class ShopperRecommendationResponse(BaseModel):
    status: Literal["success", "no_matching_size", "out_of_stock"]
    product_sku: str
    product_name: str
    garment_group: Literal["upper_body", "lower_body"] = "upper_body"
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
    # Upper-body metrics (present for upper_body garments)
    chest_ease: float | None = None
    shoulder_ease: float | None = None
    body_length_difference: float | None = None
    sleeve_length_difference: float | None = None
    chest_is_acceptable: bool | None = None
    shoulder_is_acceptable: bool | None = None
    body_length_is_acceptable: bool | None = None
    sleeve_length_is_acceptable: bool | None = None

    # Lower-body metrics (present for lower_body garments)
    waist_ease: float | None = None
    hip_ease: float | None = None
    inseam_difference: float | None = None
    waist_is_acceptable: bool | None = None
    hip_is_acceptable: bool | None = None
    inseam_is_acceptable: bool | None = None

    is_acceptable: bool
    score: float


class SizeCandidateDiagnostic(BaseModel):
    size: str
    fit: FitMetricsDiagnostic


class InvalidSizeDiagnostic(BaseModel):
    size: str
    reason: str


class MerchantDiagnosticResponse(BaseModel):
    status: Literal["success", "no_matching_size"]
    product_id: str
    product_name: str
    garment_group: Literal["upper_body", "lower_body"] = "upper_body"
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


def _classify_waist_ease(ease: float) -> Literal["snug", "true_to_size", "relaxed", "oversized"]:
    if ease < 0.5:
        return "snug"
    if ease <= 1.75:
        return "true_to_size"
    if ease <= 3.5:
        return "relaxed"
    return "oversized"


def _classify_hip_ease(ease: float) -> Literal["snug", "true_to_size", "relaxed", "oversized"]:
    if ease < 2.0:
        return "snug"
    if ease <= 3.75:
        return "true_to_size"
    if ease <= 6.5:
        return "relaxed"
    return "oversized"


def _classify_length_diff(diff: float, short_label: str) -> str:
    if diff < -0.75:
        return short_label
    if diff <= 0.75:
        return "standard"
    return "long"


def build_shopper_response(engine_result: dict) -> ShopperRecommendationResponse:
    status = engine_result["status"]
    garment_group = engine_result.get("garment_group", "upper_body")

    if status != "success":
        return ShopperRecommendationResponse(
            status="no_matching_size",
            product_sku=engine_result["product_id"],
            product_name=engine_result["product_name"],
            garment_group=garment_group,
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

    if garment_group == "lower_body":
        zones = AvatarFitZones(
            waist=_classify_waist_ease(fit["waist_ease"]),
            hips=_classify_hip_ease(fit["hip_ease"]),
            inseam=_classify_length_diff(fit["inseam_difference"], "short"),
        )
    else:
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
        garment_group=garment_group,
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
    size_label: str = Field(min_length=1, max_length=20)

    # Upper-body measurements
    chest_circumference: float | None = Field(default=None, ge=20.0, le=100.0)
    shoulder_width: float | None = Field(default=None, ge=5.0, le=40.0)
    body_length: float | None = Field(default=None, ge=10.0, le=50.0)
    sleeve_length: float | None = Field(default=None, ge=5.0, le=50.0)

    # Lower-body measurements
    waist_circumference: float | None = Field(default=None, ge=20.0, le=80.0)
    hip_circumference: float | None = Field(default=None, ge=24.0, le=90.0)
    inseam_length: float | None = Field(default=None, ge=10.0, le=45.0)

    stock_quantity: int = Field(default=10, ge=0)
    is_available: bool = True

    @field_validator("size_label")
    @classmethod
    def normalize_size_label(cls, value: str) -> str:
        cleaned = value.strip().upper()
        if not cleaned:
            raise ValueError("size_label cannot be blank.")
        return cleaned

    def has_complete_upper(self) -> bool:
        return all(
            v is not None
            for v in (
                self.chest_circumference,
                self.shoulder_width,
                self.body_length,
                self.sleeve_length,
            )
        )

    def has_any_upper(self) -> bool:
        return any(
            v is not None
            for v in (
                self.chest_circumference,
                self.shoulder_width,
                self.body_length,
                self.sleeve_length,
            )
        )

    def has_complete_lower(self) -> bool:
        return all(
            v is not None
            for v in (
                self.waist_circumference,
                self.hip_circumference,
                self.inseam_length,
            )
        )

    def has_any_lower(self) -> bool:
        return any(
            v is not None
            for v in (
                self.waist_circumference,
                self.hip_circumference,
                self.inseam_length,
            )
        )


class ProductSizeRead(BaseModel):
    id: int
    size_label: str
    chest_circumference: float | None
    shoulder_width: float | None
    body_length: float | None
    sleeve_length: float | None
    waist_circumference: float | None
    hip_circumference: float | None
    inseam_length: float | None
    stock_quantity: int
    is_available: bool

    model_config = {"from_attributes": True}


class ProductCreate(BaseModel):
    external_sku: str = Field(min_length=1, max_length=100)
    name: str = Field(min_length=2, max_length=200)
    category: str = Field(default="hoodie", min_length=2, max_length=50)
    garment_group: Literal["upper_body", "lower_body"] = "upper_body"
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

    @model_validator(mode="after")
    def validate_sizes_match_garment_group(self) -> "ProductCreate":
        for item in self.sizes:
            if self.garment_group == "upper_body":
                if not item.has_complete_upper() or item.has_any_lower():
                    raise ValueError(
                        f"Size '{item.size_label}' for an upper_body product must include all 4 upper measurements "
                        "(chest_circumference, shoulder_width, body_length, sleeve_length) and no lower measurements."
                    )
            elif self.garment_group == "lower_body":
                if not item.has_complete_lower() or item.has_any_upper():
                    raise ValueError(
                        f"Size '{item.size_label}' for a lower_body product must include all 3 lower measurements "
                        "(waist_circumference, hip_circumference, inseam_length) and no upper measurements."
                    )
        return self


class ProductRead(BaseModel):
    id: int
    merchant_id: int
    external_sku: str
    name: str
    category: str
    garment_group: str
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
    id: int
    merchant_id: int
    external_sku: str
    name: str
    category: str
    garment_group: str
    data_status: str
    thumbnail_url: str | None
    model_asset_url: str | None
    available_sizes: list[str]


class OutfitItemRequest(BaseModel):
    product_id: int = Field(gt=0)
    fit_preference: Literal["regular", "relaxed", "oversized"] = "relaxed"


class OutfitTryOnRequest(BaseModel):
    body: BodyProfile
    items: list[OutfitItemRequest] = Field(min_length=1, max_length=5)


class OutfitTryOnResponse(BaseModel):
    status: Literal["success"] = "success"
    total_items: int
    recommendations: list[ShopperRecommendationResponse]


# ============================================================
# 7. SHOPPER AVATAR PROFILES & SAVED LOOKS SCHEMAS
# ============================================================

AvatarPresetType = Literal["slim", "athletic", "average", "curvy", "broad"]


class ShopperProfileUpsert(BaseModel):
    display_name: str | None = Field(default=None, max_length=120)
    avatar_preset: AvatarPresetType = "average"
    height_inches: float | None = Field(default=None, ge=48.0, le=90.0)
    body: BodyProfile


class ShopperProfileRead(BaseModel):
    id: int
    external_shopper_id: str
    display_name: str | None
    avatar_preset: str
    height_inches: float | None
    chest_circumference: float
    shoulder_width: float
    preferred_body_length: float
    preferred_sleeve_length: float
    waist_circumference: float | None
    hip_circumference: float | None
    preferred_inseam_length: float | None

    model_config = {"from_attributes": True}


class SavedLookCreate(BaseModel):
    look_name: str = Field(min_length=1, max_length=150)
    notes: str | None = Field(default=None, max_length=500)
    items: list[OutfitItemRequest] = Field(min_length=1, max_length=5)

    @field_validator("items")
    @classmethod
    def ensure_unique_products(cls, items: list[OutfitItemRequest]) -> list[OutfitItemRequest]:
        seen: set[int] = set()
        for item in items:
            if item.product_id in seen:
                raise ValueError(f"Duplicate product_id {item.product_id} in saved look.")
            seen.add(item.product_id)
        return items


class SavedLookItemRead(BaseModel):
    id: int
    product_id: int
    product_sku: str
    product_name: str
    category: str
    garment_group: str
    thumbnail_url: str | None
    model_asset_url: str | None
    fit_preference: str
    recommended_size: str


class SavedLookRead(BaseModel):
    id: int
    shopper_id: int
    look_name: str
    notes: str | None
    items: list[SavedLookItemRead]