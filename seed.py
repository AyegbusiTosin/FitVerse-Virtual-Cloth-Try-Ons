"""
FitVerse — Idempotent Development Database Seeder

Populates PostgreSQL with a default demo merchant and the existing
SAMPLE_HOODIE garment matrix so we can verify DB-to-engine integration.
"""

from cloth_data import SAMPLE_HOODIE
from database import SessionLocal
from models import Merchant, Product, ProductSize
from repositories.product_repo import get_merchant_by_email, get_product_by_sku


def seed_demo_data() -> None:
    db = SessionLocal()
    try:
        # 1. Ensure demo merchant exists
        merchant = get_merchant_by_email(db, "demo@fitverse.ng")
        if not merchant:
            merchant = Merchant(
                name="FitVerse Demo Store Lagos",
                email="demo@fitverse.ng",
                storefront_url="https://demo.fitverse.ng",
                is_active=True,
            )
            db.add(merchant)
            db.flush()  # Assigns merchant.id without committing yet
            print(f"Created merchant: {merchant.name} (id={merchant.id})")
        else:
            print(f"Merchant already exists: {merchant.name} (id={merchant.id})")

        # 2. Ensure sample hoodie exists for this merchant
        sku = SAMPLE_HOODIE["product_id"]
        product = get_product_by_sku(db, merchant.id, sku)
        if not product:
            product = Product(
                merchant_id=merchant.id,
                external_sku=sku,
                name=SAMPLE_HOODIE["product_name"],
                category=SAMPLE_HOODIE["category"],
                data_status=SAMPLE_HOODIE["data_status"],
                unit=SAMPLE_HOODIE["unit"],
                is_active=True,
            )
            for size_label, dims in SAMPLE_HOODIE["sizes"].items():
                product.sizes.append(
                    ProductSize(
                        size_label=size_label,
                        chest_circumference=dims["chest_circumference"],
                        shoulder_width=dims["shoulder_width"],
                        body_length=dims["body_length"],
                        sleeve_length=dims["sleeve_length"],
                        stock_quantity=10,
                        is_available=True,
                    )
                )
            db.add(product)
            db.commit()
            print(f"Seeded product '{product.name}' (id={product.id}) with {len(product.sizes)} sizes.")
        else:
            print(f"Product '{product.name}' already exists (id={product.id}).")

    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    seed_demo_data()