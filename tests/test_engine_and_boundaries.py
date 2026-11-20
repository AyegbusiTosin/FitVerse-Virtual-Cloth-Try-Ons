"""
FitVerse — Automated Test Suite

Covers:
1. Deterministic sizing calculations and boundary conditions.
2. Input validation guards (body profile & garment specs).
3. Repository adapter stock filtering.
4. Shopper vs. Merchant information boundary enforcement.
5. FastAPI endpoint integration (422, 404, out_of_stock, and success paths).
"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from cloth_data import SAMPLE_HOODIE
from database import Base, get_db
from main import app
from models import Merchant, Product, ProductSize
from recommendation import evaluate_size, recommend_size, validate_garment_data
from repositories.product_repo import to_recommendation_garment_dict


# ============================================================
# TEST FIXTURES (Isolated In-Memory DB for API Tests)
# ============================================================

@pytest.fixture()
def db_session():
    """
    Provide a clean, isolated SQLite in-memory database per test function
    so API tests never pollute the development PostgreSQL instance.
    """
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    TestingSessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    Base.metadata.create_all(bind=engine)

    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)


@pytest.fixture()
def client(db_session):
    """FastAPI TestClient wired to the isolated test database session."""
    def override_get_db():
        try:
            yield db_session
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture()
def standard_body() -> dict:
    return {
        "chest_circumference": 38.0,
        "shoulder_width": 18.0,
        "preferred_body_length": 28.0,
        "preferred_sleeve_length": 25.0,
    }


# ============================================================
# 1. RECOMMENDATION ENGINE UNIT TESTS
# ============================================================

def test_recommend_size_normal_relaxed_match(standard_body):
    result = recommend_size(
        body=standard_body,
        garment_data=SAMPLE_HOODIE,
        fit_preference="relaxed",
    )
    assert result["status"] == "success"
    assert result["recommended_size"] == "L"
    assert result["fit_details"]["chest_ease"] == 6.0
    assert result["fit_details"]["shoulder_ease"] == 2.0
    assert result["fit_details"]["score"] == 0.0
    assert "M" in result["other_acceptable_sizes"]
    assert "XL" in result["other_acceptable_sizes"]


def test_recommend_size_boundary_exact_min_chest_ease():
    """
    Regular fit requires min_chest_ease=2.0 and min_shoulder_ease=-1.0.
    Sample size S has chest=40.0, shoulder=18.0.
    A 38.0 chest + 19.0 shoulder hits exact lower boundaries (2.0 and -1.0)
    for Size S, so S must be accepted even though M scores closer overall.
    """
    boundary_body = {
        "chest_circumference": 38.0,
        "shoulder_width": 19.0,
        "preferred_body_length": 26.0,
        "preferred_sleeve_length": 24.0,
    }
    result = recommend_size(
        body=boundary_body,
        garment_data=SAMPLE_HOODIE,
        fit_preference="regular",
    )
    assert result["status"] == "success"
    assert result["recommended_size"] == "M"
    assert "S" in result["other_acceptable_sizes"]


def test_recommend_size_no_matching_size_for_extreme_sleeve(standard_body):
    extreme_body = {**standard_body, "preferred_sleeve_length": 35.0}
    result = recommend_size(
        body=extreme_body,
        garment_data=SAMPLE_HOODIE,
        fit_preference="relaxed",
    )
    assert result["status"] == "no_matching_size"
    assert len(result["closest_candidates"]) == 2


def test_recommend_size_surfaces_corrupted_size_row(standard_body):
    garment_with_bad_size = {
        "product_id": "test-corrupt-01",
        "product_name": "Corrupt Test Hoodie",
        "data_status": "SAMPLE_NOT_VERIFIED",
        "sizes": {
            "BAD": {
                "chest_circumference": 999.0,  # Out of bounds (20-100)
                "shoulder_width": 18.0,
                "body_length": 26.0,
                "sleeve_length": 24.0,
            },
            "L": SAMPLE_HOODIE["sizes"]["L"],
        },
    }
    result = recommend_size(body=standard_body, garment_data=garment_with_bad_size)
    assert result["status"] == "success"
    assert result["recommended_size"] == "L"
    assert len(result["invalid_sizes"]) == 1
    assert result["invalid_sizes"][0]["size"] == "BAD"


@pytest.mark.parametrize(
    "bad_garment",
    [
        {"chest_circumference": 1000, "shoulder_width": 20, "body_length": 28, "sleeve_length": 25},
        {"chest_circumference": 44, "body_length": 28, "sleeve_length": 25},  # missing shoulder_width
        {"chest_circumference": True, "shoulder_width": 20, "body_length": 28, "sleeve_length": 25},
    ],
)
def test_validate_garment_data_rejects_invalid_specs(bad_garment):
    with pytest.raises(ValueError):
        validate_garment_data(bad_garment)


# ============================================================
# 2. REPOSITORY ADAPTER TESTS
# ============================================================

def test_repository_adapter_filters_out_of_stock_sizes():
    product = Product(
        id=1,
        merchant_id=1,
        external_sku="hoodie-stock-test",
        name="Stock Test Hoodie",
        category="hoodie",
        data_status="VERIFIED",
        unit="inches",
        sizes=[
            ProductSize(
                size_label="M",
                chest_circumference=42.0,
                shoulder_width=19.0,
                body_length=27.0,
                sleeve_length=24.5,
                stock_quantity=0,  # Out of stock
                is_available=True,
            ),
            ProductSize(
                size_label="L",
                chest_circumference=44.0,
                shoulder_width=20.0,
                body_length=28.0,
                sleeve_length=25.0,
                stock_quantity=5,
                is_available=True,
            ),
        ],
    )

    shopper_garment = to_recommendation_garment_dict(product, only_available=True)
    assert list(shopper_garment["sizes"].keys()) == ["L"]

    merchant_garment = to_recommendation_garment_dict(product, only_available=False)
    assert set(merchant_garment["sizes"].keys()) == {"M", "L"}


# ============================================================
# 3. API & PRIVACY BOUNDARY INTEGRATION TESTS
# ============================================================

def test_shopper_endpoint_hides_internal_diagnostics_and_returns_avatar_zones(client, standard_body):
    response = client.post(
        "/api/recommend-size",
        json={"body": standard_body, "fit_preference": "relaxed"},
    )
    assert response.status_code == 200
    data = response.json()

    # Shopper receives recommendation + visual avatar fit zones
    assert data["status"] == "success"
    assert data["recommended_size"] == "L"
    assert data["avatar_fit_zones"] == {
        "chest": "relaxed",
        "shoulders": "relaxed",
        "body_length": "standard",
        "sleeve_length": "standard",
    }

    # Privacy boundary: internal calculations must NEVER leak to shoppers
    forbidden_keys = {"fit_details", "score", "chest_ease", "shoulder_ease", "closest_candidates", "invalid_sizes"}
    assert forbidden_keys.isdisjoint(data.keys())


def test_shopper_endpoint_rejects_out_of_range_body_with_422(client, standard_body):
    invalid_body = {**standard_body, "chest_circumference": 12.0}  # Below minimum 20.0
    response = client.post(
        "/api/recommend-size",
        json={"body": invalid_body, "fit_preference": "relaxed"},
    )
    assert response.status_code == 422


def test_shopper_endpoint_returns_404_for_unknown_product(client, standard_body):
    response = client.post(
        "/api/recommend-size",
        json={"product_id": 9999, "body": standard_body, "fit_preference": "relaxed"},
    )
    assert response.status_code == 404


def test_merchant_crud_and_diagnostic_workflow(client, standard_body):
    # 1. Register merchant
    m_res = client.post(
        "/api/merchants",
        json={"name": "Abuja Tailors", "email": "hello@abujatailors.ng"},
    )
    assert m_res.status_code == 201
    merchant_id = m_res.json()["id"]

    # 2. Create verified product with size matrix
    p_res = client.post(
        f"/api/merchants/{merchant_id}/products",
        json={
            "external_sku": "abj-shirt-01",
            "name": "Abuja Oxford Shirt",
            "category": "shirt",
            "data_status": "VERIFIED",
            "sizes": [
                {
                    "size_label": "L",
                    "chest_circumference": 44.0,
                    "shoulder_width": 20.0,
                    "body_length": 28.0,
                    "sleeve_length": 25.0,
                    "stock_quantity": 4,
                }
            ],
        },
    )
    assert p_res.status_code == 201
    product_id = p_res.json()["id"]

    # 3. Merchant diagnostic endpoint exposes internal ease and score
    diag_res = client.post(
        f"/api/merchants/products/{product_id}/diagnose?fit_preference=relaxed",
        json=standard_body,
    )
    assert diag_res.status_code == 200
    diag_data = diag_res.json()
    assert diag_data["recommended_size"] == "L"
    assert diag_data["fit_details"]["chest_ease"] == 6.0
    assert diag_data["fit_details"]["score"] == 0.0


def test_storefront_catalog_hides_merchant_stock_counts_and_matrices(client):
    # Create merchant and product with one in-stock size and one out-of-stock size
    m_res = client.post(
        "/api/merchants",
        json={"name": "Lagos Streetwear", "email": "ops@lagosstreetwear.ng"},
    )
    merchant_id = m_res.json()["id"]

    client.post(
        f"/api/merchants/{merchant_id}/products",
        json={
            "external_sku": "lsw-hoodie-01",
            "name": "Eko Heavyweight Hoodie",
            "category": "hoodie",
            "data_status": "VERIFIED",
            "thumbnail_url": "https://cdn.fitverse.ng/hoodie-thumb.png",
            "model_asset_url": "https://cdn.fitverse.ng/hoodie-3d.glb",
            "sizes": [
                {
                    "size_label": "M",
                    "chest_circumference": 42.0,
                    "shoulder_width": 19.0,
                    "body_length": 27.0,
                    "sleeve_length": 24.5,
                    "stock_quantity": 0,  # Out of stock
                },
                {
                    "size_label": "L",
                    "chest_circumference": 44.0,
                    "shoulder_width": 20.0,
                    "body_length": 28.0,
                    "sleeve_length": 25.0,
                    "stock_quantity": 12,
                },
            ],
        },
    )

    cat_res = client.get("/api/catalog/products?category=hoodie")
    assert cat_res.status_code == 200
    items = cat_res.json()
    assert len(items) == 1
    assert items[0]["available_sizes"] == ["L"]
    assert items[0]["model_asset_url"] == "https://cdn.fitverse.ng/hoodie-3d.glb"
    # Ensure internal size matrices and exact stock counts are not leaked
    assert "sizes" not in items[0]
    assert "stock_quantity" not in items[0]


def test_multi_garment_outfit_try_on_endpoint(client, standard_body):
    m_res = client.post(
        "/api/merchants",
        json={"name": "VI Bespoke", "email": "hello@vibespokeng.com"},
    )
    merchant_id = m_res.json()["id"]

    p1 = client.post(
        f"/api/merchants/{merchant_id}/products",
        json={
            "external_sku": "vi-polo-01",
            "name": "Emerald Knit Polo",
            "category": "polo",
            "data_status": "VERIFIED",
            "sizes": [
                {
                    "size_label": "L",
                    "chest_circumference": 42.0,
                    "shoulder_width": 19.0,
                    "body_length": 28.0,
                    "sleeve_length": 25.0,
                    "stock_quantity": 5,
                }
            ],
        },
    ).json()

    p2 = client.post(
        f"/api/merchants/{merchant_id}/products",
        json={
            "external_sku": "vi-blazer-01",
            "name": "Camel Linen Blazer",
            "category": "blazer",
            "data_status": "VERIFIED",
            "sizes": [
                {
                    "size_label": "L",
                    "chest_circumference": 44.0,
                    "shoulder_width": 20.0,
                    "body_length": 28.0,
                    "sleeve_length": 25.0,
                    "stock_quantity": 3,
                }
            ],
        },
    ).json()

    look_res = client.post(
        "/api/try-on/look",
        json={
            "body": standard_body,
            "items": [
                {"product_id": p1["id"], "fit_preference": "regular"},
                {"product_id": p2["id"], "fit_preference": "relaxed"},
            ],
        },
    )
    assert look_res.status_code == 200
    payload = look_res.json()
    assert payload["total_items"] == 2
    assert payload["recommendations"][0]["recommended_size"] == "L"
    assert payload["recommendations"][0]["avatar_fit_zones"]["chest"] == "true_to_size"
    assert payload["recommendations"][1]["avatar_fit_zones"]["chest"] == "relaxed"


def test_lower_body_trousers_sizing_and_head_to_toe_outfit(client):
    # 1. Register merchant
    m_res = client.post(
        "/api/merchants",
        json={"name": "Lekki Tailored", "email": "fit@lekkitailored.ng"},
    )
    assert m_res.status_code == 201
    merchant_id = m_res.json()["id"]

    # 2. Create upper-body shirt
    shirt_res = client.post(
        f"/api/merchants/{merchant_id}/products",
        json={
            "external_sku": "lk-shirt-01",
            "name": "Lekki Crisp Poplin Shirt",
            "category": "shirt",
            "garment_group": "upper_body",
            "data_status": "VERIFIED",
            "sizes": [
                {
                    "size_label": "L",
                    "chest_circumference": 42.0,
                    "shoulder_width": 19.0,
                    "body_length": 28.0,
                    "sleeve_length": 25.0,
                    "stock_quantity": 8,
                }
            ],
        },
    )
    assert shirt_res.status_code == 201
    shirt_id = shirt_res.json()["id"]

    # 3. Create lower-body trousers
    trouser_res = client.post(
        f"/api/merchants/{merchant_id}/products",
        json={
            "external_sku": "lk-chino-01",
            "name": "Lekki Pleated Chinos",
            "category": "trousers",
            "garment_group": "lower_body",
            "data_status": "VERIFIED",
            "sizes": [
                {
                    "size_label": "32",
                    "waist_circumference": 33.0,
                    "hip_circumference": 40.5,
                    "inseam_length": 32.0,
                    "stock_quantity": 6,
                },
                {
                    "size_label": "34",
                    "waist_circumference": 35.0,
                    "hip_circumference": 42.5,
                    "inseam_length": 32.0,
                    "stock_quantity": 6,
                },
            ],
        },
    )
    assert trouser_res.status_code == 201
    trouser_id = trouser_res.json()["id"]

    # 4. Evaluate head-to-toe outfit (shirt + trousers)
    full_body = {
        "chest_circumference": 38.0,
        "shoulder_width": 18.0,
        "preferred_body_length": 28.0,
        "preferred_sleeve_length": 25.0,
        "waist_circumference": 32.0,
        "hip_circumference": 38.0,
        "preferred_inseam_length": 32.0,
    }

    look_res = client.post(
        "/api/try-on/look",
        json={
            "body": full_body,
            "items": [
                {"product_id": shirt_id, "fit_preference": "regular"},
                {"product_id": trouser_id, "fit_preference": "regular"},
            ],
        },
    )
    assert look_res.status_code == 200
    data = look_res.json()
    assert data["total_items"] == 2

    # Shirt recommendation (upper_body)
    shirt_rec = data["recommendations"][0]
    assert shirt_rec["garment_group"] == "upper_body"
    assert shirt_rec["recommended_size"] == "L"
    assert "waist" not in shirt_rec["avatar_fit_zones"]

    # Trouser recommendation (lower_body)
    trouser_rec = data["recommendations"][1]
    assert trouser_rec["garment_group"] == "lower_body"
    assert trouser_rec["recommended_size"] == "32"
    assert trouser_rec["avatar_fit_zones"] == {
        "waist": "true_to_size",
        "hips": "true_to_size",
        "inseam": "standard",
    }


def test_lower_body_garment_rejects_missing_waist_hip_inseam_with_422(client):
    m_res = client.post(
        "/api/merchants",
        json={"name": "Yaba Denim", "email": "denim@yabadenim.ng"},
    )
    merchant_id = m_res.json()["id"]

    trouser_res = client.post(
        f"/api/merchants/{merchant_id}/products",
        json={
            "external_sku": "yb-jean-01",
            "name": "Yaba Selvedge Jeans",
            "category": "jeans",
            "garment_group": "lower_body",
            "data_status": "VERIFIED",
            "sizes": [
                {
                    "size_label": "32",
                    "waist_circumference": 33.0,
                    "hip_circumference": 40.5,
                    "inseam_length": 32.0,
                    "stock_quantity": 4,
                }
            ],
        },
    )
    trouser_id = trouser_res.json()["id"]

    # Upper-body-only profile missing waist, hip, and inseam
    upper_only_body = {
        "chest_circumference": 38.0,
        "shoulder_width": 18.0,
        "preferred_body_length": 28.0,
        "preferred_sleeve_length": 25.0,
    }

    res = client.post(
        "/api/recommend-size",
        json={"product_id": trouser_id, "body": upper_only_body, "fit_preference": "regular"},
    )
    assert res.status_code == 422


def test_shopper_profile_upsert_and_save_look_lifecycle(client):
    # 1. Create merchant + upper-body shirt + lower-body trousers
    m_res = client.post(
        "/api/merchants",
        json={"name": "Ikoyi Atelier", "email": "studio@ikoyiatelier.ng"},
    )
    merchant_id = m_res.json()["id"]

    shirt = client.post(
        f"/api/merchants/{merchant_id}/products",
        json={
            "external_sku": "ik-polo-01",
            "name": "Ikoyi Silk-Cotton Polo",
            "category": "polo",
            "garment_group": "upper_body",
            "data_status": "VERIFIED",
            "model_asset_url": "https://cdn.fitverse.ng/ik-polo.glb",
            "sizes": [
                {
                    "size_label": "L",
                    "chest_circumference": 42.0,
                    "shoulder_width": 19.0,
                    "body_length": 28.0,
                    "sleeve_length": 25.0,
                    "stock_quantity": 5,
                }
            ],
        },
    ).json()

    trousers = client.post(
        f"/api/merchants/{merchant_id}/products",
        json={
            "external_sku": "ik-trouser-01",
            "name": "Ikoyi Tailored Trousers",
            "category": "trousers",
            "garment_group": "lower_body",
            "data_status": "VERIFIED",
            "model_asset_url": "https://cdn.fitverse.ng/ik-trouser.glb",
            "sizes": [
                {
                    "size_label": "32",
                    "waist_circumference": 33.0,
                    "hip_circumference": 40.5,
                    "inseam_length": 32.0,
                    "stock_quantity": 5,
                }
            ],
        },
    ).json()

    # 2. Save shopper avatar profile (PUT upsert)
    shopper_id = "amaka.lagos@example.com"
    prof_res = client.put(
        f"/api/shoppers/{shopper_id}/profile",
        json={
            "display_name": "Amaka",
            "avatar_preset": "athletic",
            "height_inches": 67.0,
            "body": {
                "chest_circumference": 38.0,
                "shoulder_width": 18.0,
                "preferred_body_length": 28.0,
                "preferred_sleeve_length": 25.0,
                "waist_circumference": 32.0,
                "hip_circumference": 38.0,
                "preferred_inseam_length": 32.0,
            },
        },
    )
    assert prof_res.status_code == 200
    assert prof_res.json()["avatar_preset"] == "athletic"

    # 3. Save a complete head-to-toe look
    save_res = client.post(
        f"/api/shoppers/{shopper_id}/looks",
        json={
            "look_name": "Friday Gallery Opening",
            "notes": "Smart casual evening look",
            "items": [
                {"product_id": shirt["id"], "fit_preference": "regular"},
                {"product_id": trousers["id"], "fit_preference": "regular"},
            ],
        },
    )
    assert save_res.status_code == 201
    saved_look = save_res.json()
    assert saved_look["look_name"] == "Friday Gallery Opening"
    assert len(saved_look["items"]) == 2
    assert saved_look["items"][0]["recommended_size"] == "L"
    assert saved_look["items"][1]["recommended_size"] == "32"

    # 4. Reload saved looks and verify 3D model URLs + zero leaked diagnostics
    list_res = client.get(f"/api/shoppers/{shopper_id}/looks")
    assert list_res.status_code == 200
    looks = list_res.json()
    assert len(looks) == 1
    assert looks[0]["items"][0]["model_asset_url"] == "https://cdn.fitverse.ng/ik-polo.glb"
    assert "score" not in looks[0]["items"][0]

    # 5. Delete saved look
    del_res = client.delete(f"/api/shoppers/{shopper_id}/looks/{saved_look['id']}")
    assert del_res.status_code == 204
    assert client.get(f"/api/shoppers/{shopper_id}/looks").json() == []


def test_pose_estimator_produces_valid_mannequin_body_profile_draft():
    from types import SimpleNamespace
    from mediapipe.tasks.python import vision
    from pose_estimator import estimate_mannequin_from_landmarks
    from schemas import BodyProfile

    # Create mock normalized MediaPipe landmarks for a standing human figure
    landmarks = [SimpleNamespace(x=0.5, y=0.5) for _ in range(33)]
    landmarks[vision.PoseLandmark.NOSE] = SimpleNamespace(x=0.50, y=0.10)
    landmarks[vision.PoseLandmark.LEFT_SHOULDER] = SimpleNamespace(x=0.60, y=0.22)
    landmarks[vision.PoseLandmark.RIGHT_SHOULDER] = SimpleNamespace(x=0.40, y=0.22)
    landmarks[vision.PoseLandmark.LEFT_ELBOW] = SimpleNamespace(x=0.63, y=0.36)
    landmarks[vision.PoseLandmark.RIGHT_ELBOW] = SimpleNamespace(x=0.37, y=0.36)
    landmarks[vision.PoseLandmark.LEFT_WRIST] = SimpleNamespace(x=0.64, y=0.49)
    landmarks[vision.PoseLandmark.RIGHT_WRIST] = SimpleNamespace(x=0.36, y=0.49)
    landmarks[vision.PoseLandmark.LEFT_HIP] = SimpleNamespace(x=0.57, y=0.50)
    landmarks[vision.PoseLandmark.RIGHT_HIP] = SimpleNamespace(x=0.43, y=0.50)
    landmarks[vision.PoseLandmark.LEFT_KNEE] = SimpleNamespace(x=0.57, y=0.70)
    landmarks[vision.PoseLandmark.RIGHT_KNEE] = SimpleNamespace(x=0.43, y=0.70)
    landmarks[vision.PoseLandmark.LEFT_ANKLE] = SimpleNamespace(x=0.57, y=0.90)
    landmarks[vision.PoseLandmark.RIGHT_ANKLE] = SimpleNamespace(x=0.43, y=0.90)
    landmarks[vision.PoseLandmark.LEFT_HEEL] = SimpleNamespace(x=0.57, y=0.92)
    landmarks[vision.PoseLandmark.RIGHT_HEEL] = SimpleNamespace(x=0.43, y=0.92)

    result = estimate_mannequin_from_landmarks(
        landmarks=landmarks,
        image_width=1000,
        image_height=1000,
        height_inches=68.0,
    )

    assert result["measurement_source"] == "ESTIMATED_FROM_PHOTO"
    assert result["suggested_avatar_preset"] in {"slim", "athletic", "average", "curvy", "broad"}

    # Prove the draft validates cleanly as a BodyProfile for the 3D mannequin
    profile = BodyProfile(**result["body_profile_draft"])
    assert profile.shoulder_width > 0
    assert profile.waist_circumference is not None
    assert profile.preferred_inseam_length is not None