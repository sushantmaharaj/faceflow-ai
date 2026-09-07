"""
FaceFlow AI — Image Utilities
Validation, resizing, compression.
"""

import io
import hashlib
from typing import Tuple

from PIL import Image
import httpx

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)

ALLOWED_MIME_TYPES = {"image/jpeg", "image/jpg", "image/png", "image/webp"}
ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}

# SerpApi image API limit
SERPAPI_MAX_BYTES = 500 * 1024  # 500 KB


def validate_image_bytes(data: bytes, filename: str = "") -> Tuple[Image.Image, str]:
    """
    Validate uploaded image bytes.
    Returns (PIL Image, detected mime type) or raises ValueError.
    """
    if len(data) > settings.max_upload_bytes:
        raise ValueError(
            f"File exceeds maximum size of {settings.max_upload_mb} MB"
        )

    # Try to open with Pillow — catches corrupted images
    try:
        img = Image.open(io.BytesIO(data))
        img.verify()  # checks file integrity
        img = Image.open(io.BytesIO(data))  # re-open after verify (verify closes it)
        img.load()
    except Exception as e:
        raise ValueError(f"Cannot decode image: {e}")

    fmt = (img.format or "").lower()
    mime_map = {"jpeg": "image/jpeg", "png": "image/png", "webp": "image/webp"}
    detected_mime = mime_map.get(fmt, "application/octet-stream")

    if detected_mime not in ALLOWED_MIME_TYPES:
        raise ValueError(
            f"Unsupported image format '{fmt}'. Allowed: JPEG, PNG, WebP"
        )

    return img, detected_mime


def compress_for_serpapi(image_bytes: bytes) -> bytes:
    """
    Compress image to ≤ 500 KB for SerpApi Image API upload.
    Returns JPEG bytes.
    """
    if len(image_bytes) <= SERPAPI_MAX_BYTES:
        return image_bytes

    img = Image.open(io.BytesIO(image_bytes)).convert("RGB")

    # Progressive JPEG compression
    for quality in [85, 75, 65, 50, 35]:
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=quality, optimize=True)
        compressed = buf.getvalue()
        if len(compressed) <= SERPAPI_MAX_BYTES:
            logger.info(
                "Compressed image for SerpApi: %d KB (quality=%d)",
                len(compressed) // 1024,
                quality,
            )
            return compressed

    # Last resort: resize down
    w, h = img.size
    while True:
        w, h = int(w * 0.8), int(h * 0.8)
        if w < 100 or h < 100:
            break
        img_small = img.resize((w, h), Image.LANCZOS)
        buf = io.BytesIO()
        img_small.save(buf, format="JPEG", quality=60, optimize=True)
        compressed = buf.getvalue()
        if len(compressed) <= SERPAPI_MAX_BYTES:
            return compressed

    # Return whatever we have at this point
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=30)
    return buf.getvalue()


def image_to_bgr_array(image_bytes: bytes):
    """Convert image bytes to BGR numpy array for InsightFace/OpenCV."""
    import numpy as np
    import cv2

    nparr = np.frombuffer(image_bytes, np.uint8)
    img_bgr = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
    if img_bgr is None:
        raise ValueError("OpenCV could not decode image")
    return img_bgr


def sha256_of_file(data: bytes) -> str:
    """Return SHA-256 hex digest of raw file bytes."""
    return hashlib.sha256(data).hexdigest()
