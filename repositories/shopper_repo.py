"""
FitVerse — Shopper Profiles & Saved Looks Repository

Responsibilities:
1. Upsert and retrieve shopper avatar profiles + body measurements.
2. Persist and reload multi-garment 'Saved Looks' with eager-loaded
   product metadata and 3D model asset URLs.
"""

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from models import SavedLook, SavedLookItem, ShopperProfile
from schemas import ShopperProfileUpsert


def get_shopper_by_external_id(
    db: Session,
    external_shopper_id: str,
) -> ShopperProfile | None:
    cleaned_id = external_shopper_id.strip()
    stmt = select(ShopperProfile).where(
        ShopperProfile.external_shopper_id == cleaned_id
    )
    return db.scalars(stmt).first()


def upsert_shopper_profile(
    db: Session,
    external_shopper_id: str,
    payload: ShopperProfileUpsert,
) -> ShopperProfile:
    cleaned_id = external_shopper_id.strip()
    profile = get_shopper_by_external_id(db, cleaned_id)
    body = payload.body

    if profile:
        profile.display_name = payload.display_name
        profile.avatar_preset = payload.avatar_preset
        profile.height_inches = payload.height_inches
        profile.chest_circumference = body.chest_circumference
        profile.shoulder_width = body.shoulder_width
        profile.preferred_body_length = body.preferred_body_length
        profile.preferred_sleeve_length = body.preferred_sleeve_length
        profile.waist_circumference = body.waist_circumference
        profile.hip_circumference = body.hip_circumference
        profile.preferred_inseam_length = body.preferred_inseam_length
    else:
        profile = ShopperProfile(
            external_shopper_id=cleaned_id,
            display_name=payload.display_name,
            avatar_preset=payload.avatar_preset,
            height_inches=payload.height_inches,
            chest_circumference=body.chest_circumference,
            shoulder_width=body.shoulder_width,
            preferred_body_length=body.preferred_body_length,
            preferred_sleeve_length=body.preferred_sleeve_length,
            waist_circumference=body.waist_circumference,
            hip_circumference=body.hip_circumference,
            preferred_inseam_length=body.preferred_inseam_length,
        )
        db.add(profile)

    db.commit()
    db.refresh(profile)
    return profile


def create_saved_look(
    db: Session,
    shopper_id: int,
    look_name: str,
    notes: str | None,
    resolved_items: list[dict],
) -> SavedLook:
    """
    Persist a SavedLook along with its evaluated SavedLookItem rows.
    Each entry in resolved_items must include:
      product_id, fit_preference, recommended_size
    """
    look = SavedLook(
        shopper_id=shopper_id,
        look_name=look_name.strip(),
        notes=notes,
    )
    for item in resolved_items:
        look.items.append(
            SavedLookItem(
                product_id=item["product_id"],
                fit_preference=item["fit_preference"],
                recommended_size=item["recommended_size"],
            )
        )

    db.add(look)
    db.commit()
    return get_saved_look_by_id(db, look.id)  # type: ignore[return-value]


def get_saved_look_by_id(db: Session, look_id: int) -> SavedLook | None:
    stmt = (
        select(SavedLook)
        .options(selectinload(SavedLook.items).selectinload(SavedLookItem.product))
        .where(SavedLook.id == look_id)
    )
    return db.scalars(stmt).first()


def list_saved_looks_for_shopper(db: Session, shopper_id: int) -> list[SavedLook]:
    stmt = (
        select(SavedLook)
        .options(selectinload(SavedLook.items).selectinload(SavedLookItem.product))
        .where(SavedLook.shopper_id == shopper_id)
        .order_by(SavedLook.id.desc())
    )
    return list(db.scalars(stmt).all())


def delete_saved_look(db: Session, look: SavedLook) -> None:
    db.delete(look)
    db.commit()