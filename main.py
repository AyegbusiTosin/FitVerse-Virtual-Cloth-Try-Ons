"""
FitVerse — Backend API Entry Point

Responsibilities:
1. Manage MediaPipe PoseLandmarker lifecycle.
2. Serve shopper-facing pose measurement extraction (/api/extract-measurements).
3. Mount shopper catalog/try-on routes and merchant management routes.

Run locally with:
    uvicorn main:app --reload
"""

import math
from contextlib import asynccontextmanager
from pathlib import Path

import cv2
import mediapipe as mp
import numpy as np
from fastapi import FastAPI, File, Form, HTTPException, UploadFile, status
from fastapi.concurrency import run_in_threadpool
from fastapi.middleware.cors import CORSMiddleware
from mediapipe.tasks import python
from mediapipe.tasks.python import vision

from routers.merchants import router as merchants_router
from routers.shopper import router as shopper_router


# ============================================================
# 1. CONFIGURATION
# ============================================================

BASE_DIR = Path(__file__).resolve().parent
MODEL_PATH = BASE_DIR / "models" / "pose_landmarker_lite.task"

MIN_DETECTION_CONFIDENCE = 0.5
API_ROUTE = "/api/extract-measurements"


# ============================================================
# 2. APPLICATION LIFECYCLE
# ============================================================

@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Initialize MediaPipe PoseLandmarker once at startup and release
    resources cleanly on shutdown.
    """
    if not MODEL_PATH.is_file():
        raise RuntimeError(
            f"Pose model not found at {MODEL_PATH}. "
            "Ensure pose_landmarker_lite.task is inside the model/ folder."
        )

    options = vision.PoseLandmarkerOptions(
        base_options=python.BaseOptions(
            model_asset_path=str(MODEL_PATH)
        ),
        running_mode=vision.RunningMode.IMAGE,
        min_pose_detection_confidence=MIN_DETECTION_CONFIDENCE,
    )

    app.state.pose_landmarker = (
        vision.PoseLandmarker.create_from_options(options)
    )

    try:
        yield
    finally:
        app.state.pose_landmarker.close()


app = FastAPI(
    title="FitVerse Backend API",
    description="Computer-vision body estimation and deterministic garment sizing.",
    lifespan=lifespan,
)


# ============================================================
# 3. CORS & ROUTERS
# ============================================================

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(shopper_router)
app.include_router(merchants_router)


# ============================================================
# 4. POSE MEASUREMENT PIPELINE HELPERS
# ============================================================

async def read_image(file: UploadFile) -> np.ndarray:
    """Read uploaded bytes and decode into an OpenCV BGR image."""
    contents = await file.read()

    if not contents:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="The uploaded image is empty.",
        )

    image_bytes = np.frombuffer(contents, dtype=np.uint8)
    image = cv2.imdecode(image_bytes, cv2.IMREAD_COLOR)

    if image is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or unsupported image file.",
        )

    return image


def detect_landmarks(image: np.ndarray, pose_landmarker):
    """Detect pose landmarks using MediaPipe Tasks API."""
    image_rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
    mp_image = mp.Image(
        image_format=mp.ImageFormat.SRGB,
        data=image_rgb,
    )
    results = pose_landmarker.detect(mp_image)

    if not results.pose_landmarks:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                "No human figure detected. Please stand fully "
                "in frame with clear lighting."
            ),
        )

    return results.pose_landmarks[0]


def get_pixel_point(
    landmarks,
    landmark_id,
    image_width: int,
    image_height: int,
) -> tuple[float, float]:
    """Convert a normalized MediaPipe landmark into pixel coordinates."""
    landmark = landmarks[landmark_id]
    return landmark.x * image_width, landmark.y * image_height


def calculate_shoulder_width(
    landmarks,
    image_width: int,
    image_height: int,
    height_inches: float,
) -> float:
    """
    Estimate shoulder width in inches using reported height as scale reference.
    """
    left_shoulder = get_pixel_point(
        landmarks, vision.PoseLandmark.LEFT_SHOULDER, image_width, image_height
    )
    right_shoulder = get_pixel_point(
        landmarks, vision.PoseLandmark.RIGHT_SHOULDER, image_width, image_height
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

    shoulder_width_pixels = math.dist(left_shoulder, right_shoulder)
    average_heel_y = (left_heel[1] + right_heel[1]) / 2
    body_reference_pixels = abs(average_heel_y - nose[1])

    if not math.isfinite(body_reference_pixels) or body_reference_pixels <= 0:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Unable to calculate valid body proportions.",
        )

    inches_per_pixel = height_inches / body_reference_pixels
    shoulder_width_inches = shoulder_width_pixels * inches_per_pixel

    if not math.isfinite(shoulder_width_inches) or shoulder_width_inches <= 0:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Unable to estimate a valid shoulder width.",
        )

    return shoulder_width_inches


# ============================================================
# 5. POSE MEASUREMENT ENDPOINT
# ============================================================

@app.post(API_ROUTE, tags=["Shopper Catalog & Virtual Try-On"])
async def extract_measurements(
    height_inches: float = Form(..., gt=0),
    file: UploadFile = File(...),
):
    """
    Accept an uploaded photo and height to estimate shoulder width.
    Offloads CPU-bound pose detection to a worker threadpool.
    """
    image = await read_image(file)
    image_height, image_width = image.shape[:2]

    landmarks = await run_in_threadpool(
        detect_landmarks,
        image=image,
        pose_landmarker=app.state.pose_landmarker,
    )

    shoulder_width = calculate_shoulder_width(
        landmarks=landmarks,
        image_width=image_width,
        image_height=image_height,
        height_inches=height_inches,
    )

    return {
        "status": "success",
        "measurements": {
            "estimated_shoulder_width_inches": round(shoulder_width, 1),
            "user_reported_height_inches": height_inches,
        },
        "privacy_notice": (
            "This endpoint does not intentionally persist the "
            "uploaded image. Image bytes are processed in memory."
        ),
    }


# ============================================================
# 6. LOCAL DEVELOPMENT ENTRY POINT
# ============================================================

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "main:app",
        host="127.0.0.1",
        port=8000,
        reload=True,
    )