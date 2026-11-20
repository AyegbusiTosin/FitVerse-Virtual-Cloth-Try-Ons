
"""
FitEngine AI — First Size Recommendation Engine

IMPORTANT:
- The garment measurements come from fictional sample data.
- The fit thresholds are provisional development rules.
- This module does not use computer vision or machine learning.
"""

from cloth_data import SAMPLE_HOODIE


# ------------------------------------------------------------
# 1. Fit preference rules
# ------------------------------------------------------------
# Chest ease = garment chest circumference - body chest circumference.
#
# These values are initial assumptions for testing. We must
# calibrate them using real garments and customer fit feedback.

FIT_RULES = {
    "regular": {
        "target_chest_ease": 4.0,
        "min_chest_ease": 2.0,
        "max_chest_ease": 6.0,
        "target_shoulder_ease": 1.0,
        "min_shoulder_ease": -1.0,
        "max_shoulder_ease": 3.0,
    },
    "relaxed": {
        "target_chest_ease": 6.0,
        "min_chest_ease": 4.0,
        "max_chest_ease": 8.0,
        "target_shoulder_ease": 2.0,
        "min_shoulder_ease": 0.0,
        "max_shoulder_ease": 4.0,
    },
    "oversized": {
        "target_chest_ease": 10.0,
        "min_chest_ease": 8.0,
        "max_chest_ease": 14.0,
        "target_shoulder_ease": 3.0,
        "min_shoulder_ease": 1.0,
        "max_shoulder_ease": 6.0,
    },
}


# ------------------------------------------------------------
# 2. Validate the user's inputs
# ------------------------------------------------------------

def validate_body_profile(body: dict) -> None:
    """
    Ensure that required measurements are present and positive.

    We validate at the boundary so invalid values do not
    silently flow into the recommendation calculations.
    """

    required_fields = (
        "chest_circumference",
        "shoulder_width",
        "preferred_body_length",
        "preferred_sleeve_length",
    )

    measurement_limits = {
    "chest_circumference": (20, 80),
    "shoulder_width": (10, 30),
    "preferred_body_length": (15, 40),
    "preferred_sleeve_length": (10, 40),
}

    for field in required_fields:
        value = body.get(field)

        if (
            not isinstance(value, (int, float))
            or isinstance(value, bool)
            or value <= 0
        ):
            raise ValueError(
                f"{field} must be a positive number in inches."
            )

        minimum, maximum = measurement_limits[field]

        if not minimum <= value <= maximum:
            raise ValueError(
                f"{field} must be between {minimum} and {maximum} inches."
        )


# ------------------------------------------------------------
# 3. Calculate fit for one size
# ------------------------------------------------------------

def evaluate_size(
    body: dict,
    garment: dict,
    fit_preference: str,
) -> dict:
    """
    Compare one garment size with the supplied body profile.

    Returns the fit metrics, whether the size passes our
    initial chest/shoulder constraints, and a ranking score.
    Lower scores indicate a closer match to our target values.
    """
    
    validate_garment_data(garment)
    rules = FIT_RULES[fit_preference]

    # Positive chest ease means the garment is larger around
    # the chest than the person's body.
    chest_ease = (
        garment["chest_circumference"]
        - body["chest_circumference"]
    )

    # Positive shoulder ease means the garment's shoulder
    # measurement exceeds the person's shoulder measurement.
    shoulder_ease = (
        garment["shoulder_width"]
        - body["shoulder_width"]
    )

    # These dimensions are compared against the user's desired
    # garment dimensions, not against body anatomy.
    body_length_difference = (
        garment["body_length"]
        - body["preferred_body_length"]
    )

    sleeve_length_difference = (
        garment["sleeve_length"]
        - body["preferred_sleeve_length"]
    )

    # The chest and shoulder ranges are our initial fit
    # constraints. Length and sleeve differences influence
    # ranking, but do not yet automatically disqualify a size.
    chest_is_acceptable = (
        rules["min_chest_ease"]
        <= chest_ease
        <= rules["max_chest_ease"]
    )

    shoulder_is_acceptable = (
        rules["min_shoulder_ease"]
        <= shoulder_ease
        <= rules["max_shoulder_ease"]
    )

    # Provisional limits for how far garment length
    # measurements may differ from the user's preferences.
    max_body_length_deviation = 2.0
    max_sleeve_length_deviation = 2.0

    body_length_is_acceptable = (
        abs(body_length_difference)
        <= max_body_length_deviation
    )

    sleeve_length_is_acceptable = (
        abs(sleeve_length_difference)
        <= max_sleeve_length_deviation
    )


    # Score how closely this size matches the target.
    # The denominators normalize the different dimensions
    # so one measurement does not dominate just because
    # it is expressed on a different numerical scale.
    score = (
        abs(chest_ease - rules["target_chest_ease"]) / 4.0
        + abs(
            shoulder_ease - rules["target_shoulder_ease"]
        ) / 2.0
        + abs(body_length_difference) / 2.0
        + abs(sleeve_length_difference) / 2.0
    )

    return {
        "chest_ease": round(chest_ease, 1),
        "shoulder_ease": round(shoulder_ease, 1),
        "body_length_difference": round(
            body_length_difference, 1
        ),
        "sleeve_length_difference": round(
            sleeve_length_difference, 1
        ),
        "chest_is_acceptable": chest_is_acceptable,
        "shoulder_is_acceptable": shoulder_is_acceptable,
        "body_length_is_acceptable": body_length_is_acceptable,
        "sleeve_length_is_acceptable": sleeve_length_is_acceptable,
        "is_acceptable": (
            chest_is_acceptable 
            and shoulder_is_acceptable
            and body_length_is_acceptable
            and sleeve_length_is_acceptable
        ),
        "score": round(score, 2),
    }


# ------------------------------------------------------------
# 4. Recommend a size
# ------------------------------------------------------------

def recommend_size(
    body: dict,
    garment_data: dict = SAMPLE_HOODIE,
    fit_preference: str = "relaxed",
) -> dict:
    """
    Evaluate each available garment size and return a
    recommendation with transparent fit calculations.

    If no size satisfies the chest and shoulder constraints,
    report that no size matches instead of forcing a choice.
    """

    validate_body_profile(body)

    if fit_preference not in FIT_RULES:
        raise ValueError(
            "fit_preference must be regular, relaxed, or oversized."
        )

    sizes = garment_data["sizes"]

    if not sizes:
        raise ValueError("The garment has no available sizes.")

    # Evaluate every size independently.
    evaluations = []
    invalid_sizes = []

    for size_name, measurements in sizes.items():
        try:
            fit = evaluate_size(
                body=body,
                garment=measurements,
                fit_preference=fit_preference,
            )
        except ValueError as error:
            invalid_sizes.append({
                "size": size_name,
                "reason": str(error),
            })
            continue

        evaluations.append({
            "size": size_name,
            "fit": fit,
        })

    if not evaluations:
        raise ValueError(
            "No valid garment sizes are available for recommendation."
        )

    # Only recommend sizes that satisfy both initial constraints.
    acceptable_sizes = [
        item for item in evaluations
        if item["fit"]["is_acceptable"]
    ]

    # Rank acceptable sizes by their fit score.
    acceptable_sizes.sort(
        key=lambda item: item["fit"]["score"]
    )

    if not acceptable_sizes:
        # Keep the closest candidates available for inspection,
        # but do not pretend that any one is a valid recommendation.
        closest_sizes = sorted(
            evaluations,
            key=lambda item: item["fit"]["score"],
        )[:2]

        return {
            "status": "no_matching_size",
            "product_id": garment_data["product_id"],
            "product_name": garment_data["product_name"],
            "data_status": garment_data["data_status"],
            "fit_preference": fit_preference,
            "message": (
                "No size satisfies the current chest and shoulder "
                "fit rules. Review the closest candidates or "
                "expand the available size range."
            ),
            "closest_candidates": closest_sizes,
            "invalid_sizes": invalid_sizes,
        }

    best = acceptable_sizes[0]

    # Explain the recommendation using the actual computed values.
    explanation = (
        f"Size {best['size']} satisfies the current chest and "
        f"shoulder constraints. Chest ease is "
        f"{best['fit']['chest_ease']} inches, and shoulder ease "
        f"is {best['fit']['shoulder_ease']} inches."
    )

    return {
        "status": "success",
        "product_id": garment_data["product_id"],
        "product_name": garment_data["product_name"],
        "data_status": garment_data["data_status"],
        "fit_preference": fit_preference,
        "recommended_size": best["size"],
        "fit_details": best["fit"],
        "explanation": explanation,
        "other_acceptable_sizes": [
            item["size"] for item in acceptable_sizes[1:]
        ],
        "invalid_sizes": invalid_sizes,
    }


def validate_garment_data(garment: dict) -> None:
    """
    Ensure that garment measurements are present,
    numerically valid, and within acceptable ranges.
    """

    required_fields = (
        "chest_circumference",
        "shoulder_width",
        "body_length",
        "sleeve_length",
    )

    measurement_limits = {
        "chest_circumference": (20, 100),
        "shoulder_width": (5, 40),
        "body_length": (10, 50),
        "sleeve_length": (5, 50),
    }

    for field in required_fields:
        value = garment.get(field)

        if (
            not isinstance(value, (int, float))
            or isinstance(value, bool)
            or value <= 0
        ):
            raise ValueError(
                f"Garment {field} must be a positive number in inches."
            )

        minimum, maximum = measurement_limits[field]

        if not minimum <= value <= maximum:
            raise ValueError(
                f"Garment {field} must be between "
                f"{minimum} and {maximum} inches."
            )

# ============================================================
# 5. LOWER-BODY GARMENT RULES & RECOMMENDATION (TROUSERS / BOTTOMS)
# ============================================================

BOTTOM_FIT_RULES = {
    "regular": {
        "target_waist_ease": 1.0,
        "min_waist_ease": 0.0,
        "max_waist_ease": 2.0,
        "target_hip_ease": 2.5,
        "min_hip_ease": 1.5,
        "max_hip_ease": 4.0,
    },
    "relaxed": {
        "target_waist_ease": 2.0,
        "min_waist_ease": 1.0,
        "max_waist_ease": 3.5,
        "target_hip_ease": 4.5,
        "min_hip_ease": 3.0,
        "max_hip_ease": 6.5,
    },
    "oversized": {
        "target_waist_ease": 3.5,
        "min_waist_ease": 2.0,
        "max_waist_ease": 6.0,
        "target_hip_ease": 7.0,
        "min_hip_ease": 5.0,
        "max_hip_ease": 10.0,
    },
}


def validate_bottom_body_profile(body: dict) -> None:
    """Ensure required lower-body measurements are present and within bounds."""
    measurement_limits = {
        "waist_circumference": (20, 70),
        "hip_circumference": (24, 80),
        "preferred_inseam_length": (15, 42),
    }

    for field, (minimum, maximum) in measurement_limits.items():
        value = body.get(field)
        if (
            value is None
            or not isinstance(value, (int, float))
            or isinstance(value, bool)
            or value <= 0
        ):
            raise ValueError(
                f"{field} is required for lower-body garments and must be a positive number in inches."
            )
        if not minimum <= value <= maximum:
            raise ValueError(
                f"{field} must be between {minimum} and {maximum} inches."
            )


def validate_bottom_garment_data(garment: dict) -> None:
    """Ensure lower-body garment measurements are present and numerically valid."""
    measurement_limits = {
        "waist_circumference": (20, 80),
        "hip_circumference": (24, 90),
        "inseam_length": (10, 45),
    }

    for field, (minimum, maximum) in measurement_limits.items():
        value = garment.get(field)
        if (
            value is None
            or not isinstance(value, (int, float))
            or isinstance(value, bool)
            or value <= 0
        ):
            raise ValueError(
                f"Garment {field} must be a positive number in inches."
            )
        if not minimum <= value <= maximum:
            raise ValueError(
                f"Garment {field} must be between {minimum} and {maximum} inches."
            )


def evaluate_bottom_size(
    body: dict,
    garment: dict,
    fit_preference: str,
) -> dict:
    """Compare one lower-body garment size against the shopper's lower-body profile."""
    validate_bottom_garment_data(garment)
    rules = BOTTOM_FIT_RULES[fit_preference]

    waist_ease = garment["waist_circumference"] - body["waist_circumference"]
    hip_ease = garment["hip_circumference"] - body["hip_circumference"]
    inseam_difference = garment["inseam_length"] - body["preferred_inseam_length"]

    waist_is_acceptable = rules["min_waist_ease"] <= waist_ease <= rules["max_waist_ease"]
    hip_is_acceptable = rules["min_hip_ease"] <= hip_ease <= rules["max_hip_ease"]
    inseam_is_acceptable = abs(inseam_difference) <= 2.0

    score = (
        abs(waist_ease - rules["target_waist_ease"]) / 2.0
        + abs(hip_ease - rules["target_hip_ease"]) / 3.0
        + abs(inseam_difference) / 2.0
    )

    return {
        "waist_ease": round(waist_ease, 1),
        "hip_ease": round(hip_ease, 1),
        "inseam_difference": round(inseam_difference, 1),
        "waist_is_acceptable": waist_is_acceptable,
        "hip_is_acceptable": hip_is_acceptable,
        "inseam_is_acceptable": inseam_is_acceptable,
        "is_acceptable": (
            waist_is_acceptable and hip_is_acceptable and inseam_is_acceptable
        ),
        "score": round(score, 2),
    }


def recommend_bottom_size(
    body: dict,
    garment_data: dict,
    fit_preference: str = "relaxed",
) -> dict:
    """Evaluate all available sizes for a lower-body garment (trousers/bottoms)."""
    validate_bottom_body_profile(body)

    if fit_preference not in BOTTOM_FIT_RULES:
        raise ValueError("fit_preference must be regular, relaxed, or oversized.")

    sizes = garment_data.get("sizes", {})
    if not sizes:
        raise ValueError("The garment has no available sizes.")

    evaluations = []
    invalid_sizes = []

    for size_name, measurements in sizes.items():
        try:
            fit = evaluate_bottom_size(
                body=body,
                garment=measurements,
                fit_preference=fit_preference,
            )
        except ValueError as error:
            invalid_sizes.append({"size": size_name, "reason": str(error)})
            continue

        evaluations.append({"size": size_name, "fit": fit})

    if not evaluations:
        raise ValueError("No valid garment sizes are available for recommendation.")

    acceptable_sizes = [
        item for item in evaluations if item["fit"]["is_acceptable"]
    ]
    acceptable_sizes.sort(key=lambda item: item["fit"]["score"])

    if not acceptable_sizes:
        closest_sizes = sorted(
            evaluations, key=lambda item: item["fit"]["score"]
        )[:2]
        return {
            "status": "no_matching_size",
            "product_id": garment_data["product_id"],
            "product_name": garment_data["product_name"],
            "garment_group": "lower_body",
            "data_status": garment_data["data_status"],
            "fit_preference": fit_preference,
            "message": (
                "No size satisfies the current waist, hip, and inseam "
                "fit rules. Review the closest candidates or expand the size range."
            ),
            "closest_candidates": closest_sizes,
            "invalid_sizes": invalid_sizes,
        }

    best = acceptable_sizes[0]
    explanation = (
        f"Size {best['size']} satisfies the waist, hip, and inseam constraints. "
        f"Waist ease is {best['fit']['waist_ease']} inches, and hip ease is "
        f"{best['fit']['hip_ease']} inches."
    )

    return {
        "status": "success",
        "product_id": garment_data["product_id"],
        "product_name": garment_data["product_name"],
        "garment_group": "lower_body",
        "data_status": garment_data["data_status"],
        "fit_preference": fit_preference,
        "recommended_size": best["size"],
        "fit_details": best["fit"],
        "explanation": explanation,
        "other_acceptable_sizes": [item["size"] for item in acceptable_sizes[1:]],
        "invalid_sizes": invalid_sizes,
    }