"""
FitVerse — Pose-to-Mannequin Measurement Estimator

Responsibilities:
1. Convert normalized MediaPipe PoseLandmarker coordinates into pixel points.
2. Derive proportional upper- and lower-body measurements (in inches) scaled
   by the shopper's reported height.
3. Compute normalized morph ratios and a suggested 3D avatar preset so the
   React 3D mannequin can initialize directly from a photo or manual sliders.
"""

import math
from mediapipe.tasks.python import vision


def _clamp(value: float, minimum: float, maximum: float) -> float:
    return max(minimum, min(maximum, value))


def get_pixel_point(
    landmarks,
    landmark_id,
    image_width: int,
    image_height: int,
) -> tuple[float, float]:
    """Convert a normalized MediaPipe landmark into pixel coordinates."""
    landmark = landmarks[landmark_id]
    return landmark.x * image_width, landmark.y * image_height


def _midpoint(p1: tuple[float, float], p2: tuple[float, float]) -> tuple[float, float]:
    return (p1[0] + p2[0]) / 2.0, (p1[1] + p2[1]) / 2.0


def classify_avatar_preset(shoulder_to_hip_ratio: float) -> str:
    """
    Map upper-to-lower body width ratio to one of FitVerse's 5 3D mannequin
    presets ('slim', 'athletic', 'average', 'curvy', 'broad').
    """
    if shoulder_to_hip_ratio >= 1.32:
        return "broad"
    if shoulder_to_hip_ratio >= 1.18:
        return "athletic"
    if shoulder_to_hip_ratio <= 0.96:
        return "curvy"
    if shoulder_to_hip_ratio <= 1.05:
        return "slim"
    return "average"


def estimate_mannequin_from_landmarks(
    landmarks,
    image_width: int,
    image_height: int,
    height_inches: float,
) -> dict:
    """
    Compute full upper- and lower-body measurements plus 3D mannequin morph
    parameters from MediaPipe pose landmarks.

    Raises ValueError if body reference proportions are invalid or zero.
    """
    left_shoulder = get_pixel_point(
        landmarks, vision.PoseLandmark.LEFT_SHOULDER, image_width, image_height
    )
    right_shoulder = get_pixel_point(
        landmarks, vision.PoseLandmark.RIGHT_SHOULDER, image_width, image_height
    )
    left_hip = get_pixel_point(
        landmarks, vision.PoseLandmark.LEFT_HIP, image_width, image_height
    )
    right_hip = get_pixel_point(
        landmarks, vision.PoseLandmark.RIGHT_HIP, image_width, image_height
    )
    left_elbow = get_pixel_point(
        landmarks, vision.PoseLandmark.LEFT_ELBOW, image_width, image_height
    )
    right_elbow = get_pixel_point(
        landmarks, vision.PoseLandmark.RIGHT_ELBOW, image_width, image_height
    )
    left_wrist = get_pixel_point(
        landmarks, vision.PoseLandmark.LEFT_WRIST, image_width, image_height
    )
    right_wrist = get_pixel_point(
        landmarks, vision.PoseLandmark.RIGHT_WRIST, image_width, image_height
    )
    left_knee = get_pixel_point(
        landmarks, vision.PoseLandmark.LEFT_KNEE, image_width, image_height
    )
    right_knee = get_pixel_point(
        landmarks, vision.PoseLandmark.RIGHT_KNEE, image_width, image_height
    )
    left_ankle = get_pixel_point(
        landmarks, vision.PoseLandmark.LEFT_ANKLE, image_width, image_height
    )
    right_ankle = get_pixel_point(
        landmarks, vision.PoseLandmark.RIGHT_ANKLE, image_width, image_height
    )
    nose = get_pixel_point(
        landmarks, vision.PoseLandmark.NOSE, image_width, image_height
    )
    left_heel = get_pixel_point(
        landmarks, vision.PoseLandmark.LEFT_HEEL, image_width, image_height
    )
    right_heel = get_pixel_point(
        landmarks, vision.PoseLandmark.RIGHT_HEEL, image_width, image_height
    )

    # Vertical scale reference (nose to average heel + ~4% crown-to-nose offset)
    average_heel_y = (left_heel[1] + right_heel[1]) / 2.0
    nose_to_heel_pixels = abs(average_heel_y - nose[1])

    if not math.isfinite(nose_to_heel_pixels) or nose_to_heel_pixels <= 0:
        raise ValueError("Unable to calculate valid vertical body proportions.")

    effective_height_pixels = nose_to_heel_pixels * 1.04
    inches_per_pixel = height_inches / effective_height_pixels

    # 1. Linear widths & segment lengths in pixels
    shoulder_width_px = math.dist(left_shoulder, right_shoulder)
    hip_width_px = math.dist(left_hip, right_hip)

    if shoulder_width_px <= 0 or hip_width_px <= 0:
        raise ValueError("Detected shoulder or hip landmarks collapsed to zero width.")

    shoulder_mid = _midpoint(left_shoulder, right_shoulder)
    hip_mid = _midpoint(left_hip, right_hip)
    torso_length_px = math.dist(shoulder_mid, hip_mid)

    left_arm_px = math.dist(left_shoulder, left_elbow) + math.dist(left_elbow, left_wrist)
    right_arm_px = math.dist(right_shoulder, right_elbow) + math.dist(right_elbow, right_wrist)
    avg_arm_px = (left_arm_px + right_arm_px) / 2.0

    left_leg_px = math.dist(left_hip, left_knee) + math.dist(left_knee, left_ankle)
    right_leg_px = math.dist(right_hip, right_knee) + math.dist(right_knee, right_ankle)
    avg_leg_px = (left_leg_px + right_leg_px) / 2.0

    # 2. Convert linear segments to inches
    shoulder_width_in = shoulder_width_px * inches_per_pixel
    hip_width_in = hip_width_px * inches_per_pixel
    torso_length_in = torso_length_px * inches_per_pixel
    arm_length_in = avg_arm_px * inches_per_pixel
    leg_length_in = avg_leg_px * inches_per_pixel

    # 3. Anthropometric 2D-to-3D circumference & garment-length approximations
    # Clamped to BodyProfile schema bounds so the draft plugs straight into /api/try-on/look
    est_shoulder = round(_clamp(shoulder_width_in, 10.0, 30.0), 1)
    est_chest = round(_clamp(shoulder_width_in * 2.15, 20.0, 80.0), 1)
    est_body_length = round(_clamp(torso_length_in * 1.28, 15.0, 40.0), 1)
    est_sleeve_length = round(_clamp(arm_length_in * 1.05, 10.0, 40.0), 1)

    est_hip = round(_clamp(hip_width_in * 2.85, 24.0, 80.0), 1)
    est_waist = round(_clamp(est_hip * 0.84, 20.0, 70.0), 1)
    est_inseam = round(_clamp(leg_length_in * 0.92, 15.0, 42.0), 1)

    # 4. 3D Mannequin morph ratios
    shoulder_to_hip_ratio = round(shoulder_width_px / hip_width_px, 2)
    torso_to_leg_ratio = round(
        torso_length_px / max(avg_leg_px, 1.0), 2
    )
    suggested_preset = classify_avatar_preset(shoulder_to_hip_ratio)

    return {
        "measurement_source": "ESTIMATED_FROM_PHOTO",
        "user_reported_height_inches": height_inches,
        "suggested_avatar_preset": suggested_preset,
        "mannequin_morphs": {
            "shoulder_to_hip_ratio": shoulder_to_hip_ratio,
            "torso_to_leg_ratio": torso_to_leg_ratio,
        },
        "body_profile_draft": {
            "chest_circumference": est_chest,
            "shoulder_width": est_shoulder,
            "preferred_body_length": est_body_length,
            "preferred_sleeve_length": est_sleeve_length,
            "waist_circumference": est_waist,
            "hip_circumference": est_hip,
            "preferred_inseam_length": est_inseam,
        },
    }