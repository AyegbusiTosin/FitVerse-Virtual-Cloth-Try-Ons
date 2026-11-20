"""
FitVerse — Database Seed Script

Idempotently seeds:
1. FitVerse Demo Store Lagos (merchant_id=1)
2. Full head-to-toe demo catalog (Polo + Blazer + Trousers) so the
   React 3D mannequin UI has upper-body and lower-body garments ready
   for demos out of the box.

Run with:
    python seed.py
"""

from database import SessionLocal
from models import Merchant, Product, ProductSize
from repositories.product_repo import get_merchant_by_email, get_product_by_sku


DEMO_CATALOG = [
    {
        "external_sku": "fv-polo-emerald-01",
        "name": "Emerald Knit Polo",
        "category": "polo",
        "garment_group": "upper_body",
        "data_status": "VERIFIED",
        "thumbnail_url": "/assets/thumbnails/emerald-polo.png",
        "model_asset_url": "/assets/models/emerald-polo.glb",
        "sizes": [
            {"size_label": "S", "chest_circumference": 39.0, "shoulder_width": 17.5, "body_length": 26.5, "sleeve_length": 24.0, "stock_quantity": 12},
            {"size_label": "M", "chest_circumference": 41.0, "shoulder_width": 18.5, "body_length": 27.5, "sleeve_length": 24.5, "stock_quantity": 15},
            {"size_label": "L", "chest_circumference": 43.0, "shoulder_width": 19.5, "body_length": 28.5, "sleeve_length": 25.0, "stock_quantity": 10},
            {"size_label": "XL", "chest_circumference": 45.0, "shoulder_width": 20.5, "body_length": 29.5, "sleeve_length": 25.5, "stock_quantity": 8},
        ],
    },
    {
        "external_sku": "fv-blazer-camel-01",
        "name": "Camel Linen Blazer",
        "category": "blazer",
        "garment_group": "upper_body",
        "data_status": "VERIFIED",
        "thumbnail_url": "/assets/thumbnails/camel-blazer.png",
        "model_asset_url": "/assets/models/camel-blazer.glb",
        "sizes": [
            {"size_label": "S", "chest_circumference": 40.5, "shoulder_width": 18.0, "body_length": 27.5, "sleeve_length": 24.5, "stock_quantity": 8},
            {"size_label": "M", "chest_circumference": 42.5, "shoulder_width": 19.0, "body_length": 28.5, "sleeve_length": 25.0, "stock_quantity": 10},
            {"size_label": "L", "chest_circumference": 44.5, "shoulder_width": 20.0, "body_length": 29.5, "sleeve_length": 25.5, "stock_quantity": 9},
            {"size_label": "XL", "chest_circumference": 46.5, "shoulder_width": 21.0, "body_length": 30.5, "sleeve_length": 26.0, "stock_quantity": 5},
        ],
    },
    {
        "external_sku": "fv-trousers-sand-01",
        "name": "Sandstone Pleated Trousers",
        "category": "trousers",
        "garment_group": "lower_body",
        "data_status": "VERIFIED",
        "thumbnail_url": "/assets/thumbnails/sand-trousers.png",
        "model_asset_url": "/assets/models/sand-trousers.glb",
        "sizes": [
            {"size_label": "30", "waist_circumference": 31.0, "hip_circumference": 38.5, "inseam_length": 31.0, "stock_quantity": 10},
            {"size_label": "32", "waist_circumference": 33.0, "hip_circumference": 40.5, "inseam_length": 32.0, "stock_quantity": 14},
            {"size_label": "34", "waist_circumference": 35.0, "hip_circumference": 42.5, "inseam_length": 32.0, "stock_quantity": 12},
            {"size_label": "36", "waist_circumference": 37.0, "hip_circumference": 44.5, "inseam_length": 33.0, "stock_quantity": 7},
        ],
    },
]


def run_seed() -> None:
    db = SessionLocal()
    try:
        merchant = get_merchant_by_email(db, "demo@fitverse.ng")
        if not merchant:
            merchant = Merchant(
                name="FitVerse Demo Store Lagos",
                email="demo@fitverse.ng",
                storefront_url="https://demo.fitverse.ng",
                is_active=True,
            )
            db.add(merchant)
            db.commit()
            db.refresh(merchant)
            print(f"Created merchant: {merchant.name} (id={merchant.id})")
        else:
            print(f"Merchant already exists: {merchant.name} (id={merchant.id})")

        for item in DEMO_CATALOG:
            existing = get_product_by_sku(db, merchant.id, item["external_sku"])
            if existing:
                print(f"Product '{existing.name}' already exists (id={existing.id}).")
                continue

            product = Product(
                merchant_id=merchant.id,
                external_sku=item["external_sku"],
                name=item["name"],
                category=item["category"],
                garment_group=item["garment_group"],
                data_status=item["data_status"],
                unit="inches",
                thumbnail_url=item["thumbnail_url"],
                model_asset_url=item["model_asset_url"],
                is_active=True,
            )
            for sz in item["sizes"]:
                product.sizes.append(ProductSize(**sz, is_available=True))

            db.add(product)
            db.commit()
            db.refresh(product)
            print(f"Seeded '{product.name}' (id={product.id}, group={product.garment_group}) with {len(product.sizes)} sizes.")
    finally:
        db.close()


if __name__ == "__main__":
    run_seed()