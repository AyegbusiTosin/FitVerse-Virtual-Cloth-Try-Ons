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