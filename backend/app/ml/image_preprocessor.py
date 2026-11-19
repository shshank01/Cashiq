"""
CashIQ Conditional Image Preprocessing Pipeline for Receipt & Document OCR.

Analyzes image quality before applying any destructive transformation:
- EXIF orientation correction & alpha-to-white flattening
- Resolution check & conditional upscaling/downscaling
- Perspective correction for photographed receipts on contrasting backgrounds
- Fine deskewing only when measurable skew exceeds threshold
- Blur, low-light, and low-contrast quality scoring
- Conditional contrast enhancement (CLAHE) and adaptive thresholding variants
- Targeted crop enhancement for low-confidence field retries

Always preserves the clean EXIF-normalized original image so OCR engines can compare
results rather than degrading already-clear digital or high-quality scans.
"""

from dataclasses import dataclass
import math
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
from PIL import Image, ImageEnhance, ImageOps

try:
    import cv2
    HAS_CV2 = True
except ImportError:
    cv2 = None
    HAS_CV2 = False


@dataclass
class ImageQualityMetrics:
    width: int
    height: int
    sharpness: float          # Laplacian variance (higher = sharper; < 80 is blurry)
    brightness: float         # Mean luminance 0..255 (< 95 is low-light)
    contrast: float           # Luminance std 0..128 (< 35 is low-contrast)
    skew_angle_deg: float     # Estimated text skew in degrees
    is_low_res: bool
    is_blurry: bool
    is_low_light: bool
    is_low_contrast: bool
    needs_deskew: bool
    has_document_quad: bool

    def to_dict(self) -> Dict[str, Any]:
        return {
            "width": self.width,
            "height": self.height,
            "sharpness": round(self.sharpness, 2),
            "brightness": round(self.brightness, 2),
            "contrast": round(self.contrast, 2),
            "skew_angle_deg": round(self.skew_angle_deg, 2),
            "is_low_res": self.is_low_res,
            "is_blurry": self.is_blurry,
            "is_low_light": self.is_low_light,
            "is_low_contrast": self.is_low_contrast,
            "needs_deskew": self.needs_deskew,
            "has_document_quad": self.has_document_quad,
        }


def pil_to_bgr(img: Image.Image) -> np.ndarray:
    rgb = np.array(img.convert("RGB"))
    if HAS_CV2:
        return cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)
    return rgb[:, :, ::-1].copy()


def bgr_to_pil(arr: np.ndarray) -> Image.Image:
    if arr.ndim == 2:
        return Image.fromarray(arr).convert("RGB")
    if HAS_CV2:
        rgb = cv2.cvtColor(arr, cv2.COLOR_BGR2RGB)
    else:
        rgb = arr[:, :, ::-1]
    return Image.fromarray(rgb)


def normalize_base_image(img: Image.Image) -> Image.Image:
    """Applies EXIF orientation transpose and flattens alpha onto white background without degrading clarity."""
    try:
        img = ImageOps.exif_transpose(img)
    except Exception:
        pass

    if img.mode in ("RGBA", "LA", "P"):
        bg = Image.new("RGB", img.size, (255, 255, 255))
        if img.mode == "P":
            img = img.convert("RGBA")
        if "A" in img.mode:
            bg.paste(img, mask=img.split()[-1])
        else:
            bg.paste(img)
        img = bg
    elif img.mode != "RGB":
        img = img.convert("RGB")

    # Cap massive camera photos (> 2600px) to keep CPU inference fast while keeping text crisp
    max_dim = max(img.width, img.height)
    if max_dim > 2600:
        scale = 2600.0 / max_dim
        img = img.resize((int(img.width * scale), int(img.height * scale)), Image.Resampling.LANCZOS)

    return img


def _order_quad_points(pts: np.ndarray) -> np.ndarray:
    """Orders 4 corner points as [top-left, top-right, bottom-right, bottom-left]."""
    rect = np.zeros((4, 2), dtype="float32")
    s = pts.sum(axis=1)
    rect[0] = pts[np.argmin(s)]
    rect[2] = pts[np.argmax(s)]
    diff = np.diff(pts, axis=1)
    rect[1] = pts[np.argmin(diff)]
    rect[3] = pts[np.argmax(diff)]
    return rect


def detect_document_quad(bgr: np.ndarray) -> Optional[np.ndarray]:
    """
    Detects a strong 4-point receipt/document contour against a contrasting background
    (typical of photographed receipts on a desk). Returns None for clean digital images
    where the document already fills the frame.
    """
    if not HAS_CV2:
        return None
    h, w = bgr.shape[:2]
    img_area = float(h * w)
    if img_area < 40000:
        return None

    # Check border darkness/variance: digital receipts usually have uniform white borders
    border_pixels = np.concatenate([
        bgr[0, :, :], bgr[-1, :, :], bgr[:, 0, :], bgr[:, -1, :]
    ], axis=0)
    if float(np.mean(border_pixels)) > 235.0 and float(np.std(border_pixels)) < 12.0:
        return None

    scale = min(1.0, 800.0 / max(h, w))
    small = cv2.resize(bgr, (int(w * scale), int(h * scale))) if scale < 1.0 else bgr
    gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)
    blurred = cv2.GaussianBlur(gray, (5, 5), 0)
    edges = cv2.Canny(blurred, 50, 150)
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (5, 5))
    edges = cv2.dilate(edges, kernel, iterations=1)

    contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        return None

    small_area = float(small.shape[0] * small.shape[1])
    for cnt in sorted(contours, key=cv2.contourArea, reverse=True)[:5]:
        area = cv2.contourArea(cnt)
        area_ratio = area / small_area
        if area_ratio < 0.22 or area_ratio > 0.94:
            continue
        peri = cv2.arcLength(cnt, True)
        approx = cv2.approxPolyDP(cnt, 0.025 * peri, True)
        if len(approx) == 4 and cv2.isContourConvex(approx):
            pts = approx.reshape(4, 2).astype("float32") / scale
            return _order_quad_points(pts)
    return None


def apply_perspective_correction(bgr: np.ndarray, quad: np.ndarray) -> np.ndarray:
    """Warps a photographed receipt quadrilateral to a flat top-down view."""
    if not HAS_CV2:
        return bgr
    tl, tr, br, bl = quad
    width_a = float(np.linalg.norm(br - bl))
    width_b = float(np.linalg.norm(tr - tl))
    max_w = max(int(max(width_a, width_b)), 100)

    height_a = float(np.linalg.norm(tr - br))
    height_b = float(np.linalg.norm(tl - bl))
    max_h = max(int(max(height_a, height_b)), 100)

    dst = np.array([
        [0, 0],
        [max_w - 1, 0],
        [max_w - 1, max_h - 1],
        [0, max_h - 1],
    ], dtype="float32")
    M = cv2.getPerspectiveTransform(quad, dst)
    return cv2.warpPerspective(bgr, M, (max_w, max_h), flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_REPLICATE)


def estimate_skew_angle(gray: np.ndarray) -> float:
    """Estimates small document skew angle (in degrees, within [-18, +18]) using Hough lines."""
    if not HAS_CV2:
        return 0.0
    h, w = gray.shape[:2]
    scale = min(1.0, 1000.0 / max(h, w))
    small = cv2.resize(gray, (int(w * scale), int(h * scale))) if scale < 1.0 else gray
    edges = cv2.Canny(small, 50, 150, apertureSize=3)
    min_line_len = max(40, int(small.shape[1] * 0.12))
    lines = cv2.HoughLinesP(edges, 1, np.pi / 180.0, threshold=60, minLineLength=min_line_len, maxLineGap=15)
    if lines is None or len(lines) < 3:
        return 0.0

    angles: List[float] = []
    for line in lines:
        coords = np.asarray(line).reshape(-1)
        if coords.size < 4:
            continue
        x1, y1, x2, y2 = float(coords[0]), float(coords[1]), float(coords[2]), float(coords[3])
        dx = x2 - x1
        dy = y2 - y1
        if abs(dx) < 10:
            continue
        ang = math.degrees(math.atan2(dy, dx))
        if -18.0 <= ang <= 18.0:
            angles.append(ang)

    if len(angles) < 3:
        return 0.0
    med = float(np.median(angles))
    # Only trust estimate if angles cluster consistently
    mad = float(np.median(np.abs(np.array(angles) - med)))
    if mad > 2.5:
        return 0.0
    return med


def deskew_image(bgr: np.ndarray, angle_deg: float) -> np.ndarray:
    """Rotates image cleanly around center to remove fine skew without clipping text."""
    if not HAS_CV2 or abs(angle_deg) < 1.0:
        return bgr
    h, w = bgr.shape[:2]
    center = (w / 2.0, h / 2.0)
    M = cv2.getRotationMatrix2D(center, angle_deg, 1.0)
    cos = abs(M[0, 0])
    sin = abs(M[0, 1])
    new_w = int((h * sin) + (w * cos))
    new_h = int((h * cos) + (w * sin))
    M[0, 2] += (new_w / 2.0) - center[0]
    M[1, 2] += (new_h / 2.0) - center[1]
    return cv2.warpAffine(
        bgr, M, (new_w, new_h),
        flags=cv2.INTER_CUBIC,
        borderMode=cv2.BORDER_CONSTANT,
        borderValue=(255, 255, 255),
    )


def assess_image_quality(img: Image.Image) -> Tuple[ImageQualityMetrics, Optional[np.ndarray]]:
    """Computes objective sharpness, luminance, contrast, resolution, skew, and contour metrics."""
    w, h = img.size
    is_low_res = min(w, h) < 700

    if not HAS_CV2:
        gray_np = np.array(img.convert("L"), dtype=np.float32)
        brightness = float(np.mean(gray_np))
        contrast = float(np.std(gray_np))
        return ImageQualityMetrics(
            width=w,
            height=h,
            sharpness=150.0,
            brightness=brightness,
            contrast=contrast,
            skew_angle_deg=0.0,
            is_low_res=is_low_res,
            is_blurry=False,
            is_low_light=brightness < 95.0,
            is_low_contrast=contrast < 35.0,
            needs_deskew=False,
            has_document_quad=False,
        ), None

    bgr = pil_to_bgr(img)
    gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
    sharpness = float(cv2.Laplacian(gray, cv2.CV_64F).var())
    brightness = float(np.mean(gray))
    contrast = float(np.std(gray))
    skew = estimate_skew_angle(gray)
    quad = detect_document_quad(bgr)

    metrics = ImageQualityMetrics(
        width=w,
        height=h,
        sharpness=sharpness,
        brightness=brightness,
        contrast=contrast,
        skew_angle_deg=skew,
        is_low_res=is_low_res,
        is_blurry=sharpness < 75.0,
        is_low_light=brightness < 105.0,
        is_low_contrast=contrast < 38.0,
        needs_deskew=abs(skew) >= 1.3,
        has_document_quad=quad is not None,
    )
    return metrics, quad


def build_enhanced_variant(img: Image.Image, metrics: ImageQualityMetrics, quad: Optional[np.ndarray] = None) -> Image.Image:
    """
    Produces a conditionally enhanced variant for difficult images (low-light, blurry,
    skewed, or photographed receipts) using CLAHE illumination normalization + gentle
    unsharp mask + optional deskew/perspective correction.
    """
    if not HAS_CV2:
        out = img
        if metrics.is_low_res:
            scale = 1200.0 / max(1, min(out.width, out.height))
            out = out.resize((int(out.width * scale), int(out.height * scale)), Image.Resampling.LANCZOS)
        if metrics.is_low_light:
            out = ImageEnhance.Brightness(out).enhance(1.35)
        if metrics.is_low_contrast:
            out = ImageEnhance.Contrast(out).enhance(1.6)
        return out

    bgr = pil_to_bgr(img)

    # 1. Perspective correction only when a clear document quad exists
    if quad is not None:
        bgr = apply_perspective_correction(bgr, quad)

    # 2. Conditional deskewing
    if metrics.needs_deskew:
        bgr = deskew_image(bgr, metrics.skew_angle_deg)

    # 3. Upscale low-resolution images
    h, w = bgr.shape[:2]
    if min(w, h) < 850:
        scale = min(2.2, 1100.0 / max(1, min(w, h)))
        bgr = cv2.resize(bgr, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_CUBIC)

    # 4. Illumination / low-light / contrast normalization via CLAHE on L channel
    if metrics.is_low_light or metrics.is_low_contrast or metrics.is_blurry:
        lab = cv2.cvtColor(bgr, cv2.COLOR_BGR2LAB)
        l_chan, a_chan, b_chan = cv2.split(lab)
        clip = 3.2 if metrics.is_low_light else 2.2
        clahe = cv2.createCLAHE(clipLimit=clip, tileGridSize=(8, 8))
        l_eq = clahe.apply(l_chan)
        if metrics.is_low_light:
            # Gentle gamma brightening to recover dark receipt photos
            lut = np.array([min(255, int(((i / 255.0) ** 0.65) * 255)) for i in range(256)], dtype=np.uint8)
            l_eq = cv2.LUT(l_eq, lut)
        bgr = cv2.cvtColor(cv2.merge((l_eq, a_chan, b_chan)), cv2.COLOR_LAB2BGR)

    # 5. Gentle unsharp masking for blurry images
    if metrics.is_blurry:
        blurred = cv2.GaussianBlur(bgr, (0, 0), sigmaX=1.5)
        bgr = cv2.addWeighted(bgr, 1.55, blurred, -0.55, 0)

    return bgr_to_pil(bgr)


def build_adaptive_threshold_variant(img: Image.Image) -> Image.Image:
    """
    Produces an illumination-invariant adaptive-thresholded image variant for heavily
    shadowed or uneven low-light receipt photographs (used only as a fallback/comparison).
    """
    if not HAS_CV2:
        gray = ImageOps.grayscale(img)
        return ImageEnhance.Contrast(gray).enhance(2.2).convert("RGB")

    bgr = pil_to_bgr(img)
    gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
    # Remove uneven illumination via morphological background division
    bg = cv2.GaussianBlur(gray, (51, 51), 0)
    norm = cv2.divide(gray, np.maximum(bg, 1), scale=255)
    denoised = cv2.fastNlMeansDenoising(norm, h=8)
    thresh = cv2.adaptiveThreshold(
        denoised, 255,
        cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY,
        31, 12,
    )
    return bgr_to_pil(thresh)


def enhance_crop_for_retry(
    img: Image.Image,
    bbox: List[float],
    mode: str = "clahe",
    pad: int = 12,
) -> Optional[Image.Image]:
    """
    Crops a specific bounding box region [x1, y1, x2, y2], pads and upscales it,
    and applies targeted enhancement for retrying low-confidence financial fields.
    """
    w, h = img.size
    x1 = max(0, int(bbox[0]) - pad)
    y1 = max(0, int(bbox[1]) - pad)
    x2 = min(w, int(bbox[2]) + pad)
    y2 = min(h, int(bbox[3]) + pad)
    if x2 - x1 < 8 or y2 - y1 < 6:
        return None

    crop = img.crop((x1, y1, x2, y2))
    # Upscale crop 2.5x for crisp digit recognition
    scale = 2.5 if crop.height < 60 else 1.8
    crop = crop.resize((max(20, int(crop.width * scale)), max(20, int(crop.height * scale))), Image.Resampling.LANCZOS)

    if not HAS_CV2:
        if mode == "clahe":
            return ImageEnhance.Contrast(crop).enhance(1.7)
        return ImageOps.grayscale(crop).convert("RGB")

    bgr = pil_to_bgr(crop)
    if mode == "otsu":
        gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
        _, th = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        out = bgr_to_pil(th)
    else:
        lab = cv2.cvtColor(bgr, cv2.COLOR_BGR2LAB)
        l_ch, a_ch, b_ch = cv2.split(lab)
        l_eq = cv2.createCLAHE(clipLimit=2.8, tileGridSize=(4, 4)).apply(l_ch)
        merged = cv2.cvtColor(cv2.merge((l_eq, a_ch, b_ch)), cv2.COLOR_LAB2BGR)
        blur = cv2.GaussianBlur(merged, (0, 0), sigmaX=1.0)
        sharp = cv2.addWeighted(merged, 1.5, blur, -0.5, 0)
        out = bgr_to_pil(sharp)

    # Add white border padding (helps recognition models on tight crops)
    return ImageOps.expand(out, border=16, fill=(255, 255, 255))
