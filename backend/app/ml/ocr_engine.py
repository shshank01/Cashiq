"""
CashIQ Unified OCR Engine Manager (CPU-safe, Lazy Singleton, Multi-Backend).

Engine hierarchy & design:
1. Optional PaddleOCR (PP-OCR + PP-StructureV3) when `paddleocr` + `paddlepaddle`
   are installed. Uses PP-StructureV3 selectively for multi-column tables/statements,
   never applying its heavier layout pipeline unnecessarily to simple receipts.
2. RapidOCR (PP-OCRv6 / PP-OCRv4 on ONNX Runtime CPU) — lightweight, zero GPU
   dependency, detect-then-recognize with exact bounding boxes and confidence scores.
3. Native Windows OCR (`winocr`) fallback with word/line bounding boxes.
4. Tesseract (`pytesseract`) fallback with `image_to_data` boxes and confidences.

All models are loaded once and reused across requests. Supports:
- Preserving bounding boxes, text, and confidence scores
- Reading-order line reconstruction preserving horizontal column alignment
- Orientation detection & recovery (0/90/180/270 degrees)
- Conditional preprocessing comparison (retaining original vs enhanced)
- Targeted crop retries ONLY on low-confidence or critical financial regions
"""

import asyncio
from dataclasses import dataclass, field
import os
import re
import threading
import time
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
from PIL import Image

from app.ml.image_preprocessor import (
    ImageQualityMetrics,
    assess_image_quality,
    build_adaptive_threshold_variant,
    build_enhanced_variant,
    enhance_crop_for_retry,
    normalize_base_image,
)


@dataclass
class OCRBox:
    text: str
    confidence: float
    bbox: List[float]  # [x1, y1, x2, y2]
    polygon: Optional[List[List[float]]] = None
    engine: str = "unknown"

    @property
    def x1(self) -> float:
        return self.bbox[0]

    @property
    def y1(self) -> float:
        return self.bbox[1]

    @property
    def x2(self) -> float:
        return self.bbox[2]

    @property
    def y2(self) -> float:
        return self.bbox[3]

    @property
    def y_center(self) -> float:
        return (self.bbox[1] + self.bbox[3]) * 0.5

    @property
    def height(self) -> float:
        return max(1.0, self.bbox[3] - self.bbox[1])

    def to_dict(self) -> Dict[str, Any]:
        return {
            "text": self.text,
            "confidence": round(float(self.confidence), 4),
            "bbox": [round(float(v), 1) for v in self.bbox],
            "engine": self.engine,
        }


@dataclass
class OCRLine:
    text: str
    confidence: float
    bbox: List[float]
    boxes: List[OCRBox] = field(default_factory=list)


@dataclass
class OCRResult:
    boxes: List[OCRBox]
    lines: List[OCRLine]
    text: str
    mean_confidence: float
    engine: str
    rotation_applied: int = 0
    variant_used: str = "original"
    retries_performed: int = 0
    layout_tables: List[List[List[str]]] = field(default_factory=list)
    quality_metrics: Optional[Dict[str, Any]] = None
    processing_ms: float = 0.0


def group_boxes_into_lines(boxes: List[OCRBox]) -> Tuple[List[OCRLine], str]:
    """
    Groups detected OCR text boxes into visual rows preserving reading order
    (top-to-bottom, left-to-right) and column spacing so labels and amounts stay paired.
    """
    valid = [b for b in boxes if b.text and b.text.strip()]
    if not valid:
        return [], ""

    # Sort top-to-bottom, then left-to-right
    valid.sort(key=lambda b: (b.y_center, b.x1))
    median_h = float(np.median([b.height for b in valid]))
    y_tol = max(8.0, median_h * 0.58)

    row_groups: List[List[OCRBox]] = []
    for box in valid:
        placed = False
        for row in reversed(row_groups[-6:]):
            row_y = float(np.mean([r.y_center for r in row]))
            row_h = float(np.mean([r.height for r in row]))
            if abs(box.y_center - row_y) <= max(y_tol, row_h * 0.55):
                row.append(box)
                placed = True
                break
        if not placed:
            row_groups.append([box])

    # Sort rows by vertical center, and boxes within each row left-to-right
    row_groups.sort(key=lambda r: float(np.mean([b.y_center for b in r])))

    ocr_lines: List[OCRLine] = []
    text_lines: List[str] = []
    for row in row_groups:
        row.sort(key=lambda b: b.x1)
        parts: List[str] = []
        for idx, b in enumerate(row):
            if idx > 0:
                gap = b.x1 - row[idx - 1].x2
                sep = "   " if gap > max(18.0, median_h * 1.2) else " "
                parts.append(sep)
            parts.append(b.text.strip())
        line_text = "".join(parts).strip()
        if not line_text:
            continue
        x1 = min(b.x1 for b in row)
        y1 = min(b.y1 for b in row)
        x2 = max(b.x2 for b in row)
        y2 = max(b.y2 for b in row)
        conf = float(np.mean([b.confidence for b in row]))
        ocr_lines.append(OCRLine(text=line_text, confidence=conf, bbox=[x1, y1, x2, y2], boxes=row))
        text_lines.append(line_text)

    return ocr_lines, "\n".join(text_lines)


def _polygon_to_bbox(poly: Any) -> List[float]:
    arr = np.array(poly, dtype=np.float64)
    if arr.ndim == 2 and arr.shape[1] >= 2:
        return [float(arr[:, 0].min()), float(arr[:, 1].min()), float(arr[:, 0].max()), float(arr[:, 1].max())]
    if arr.size == 4:
        flat = arr.flatten().tolist()
        return [float(v) for v in flat]
    return [0.0, 0.0, 0.0, 0.0]


def _boxes_indicate_sideways_orientation(boxes: List[OCRBox]) -> bool:
    """
    Detects 90°/270° sideways document orientation directly from OCR text-box geometry:
    on upright documents, multi-character text lines are wider than tall; on sideways
    photographs, a majority of text boxes are taller than wide.
    """
    if len(boxes) < 3:
        return False
    vertical_count = 0
    measurable = 0
    for b in boxes:
        w = max(1.0, b.x2 - b.x1)
        h = max(1.0, b.y2 - b.y1)
        if max(w, h) < 16.0:
            continue
        measurable += 1
        if h > w * 1.15:
            vertical_count += 1
    return measurable >= 3 and (vertical_count / measurable) >= 0.45


def _score_ocr_result(res: OCRResult) -> float:
    """
    Scores an OCR pass for comparing original vs preprocessed/rotated variants.
    Combines mean confidence, meaningful alphanumeric character yield, box orientation,
    and financial cues.
    """
    if not res.boxes or not res.text.strip():
        return 0.0
    txt = res.text.strip()
    alnum = sum(1 for c in txt if c.isalnum())
    if alnum < 4:
        return 0.05
    cue_bonus = 0.0
    if re.search(r"\b(?:total|amount|invoice|subtotal|tax|gst|date|rs\.?|inr|upi|\$|₹)\b", txt, re.IGNORECASE):
        cue_bonus += 0.15
    if re.search(r"\d+[.,]\d{2}", txt):
        cue_bonus += 0.10
    length_factor = min(1.0, alnum / 80.0)
    score = res.mean_confidence * 0.55 + length_factor * 0.25 + cue_bonus
    # Penalize sideways vertical-box layouts so upright rotations win cleanly
    if _boxes_indicate_sideways_orientation(res.boxes):
        score *= 0.45
    return round(score, 4)


class OCREngineManager:
    """
    Lazy-loaded singleton OCR engine manager.
    Loads heavy OCR models once on first use and reuses them safely across requests.
    """

    def __init__(self):
        self._lock = threading.Lock()
        self._paddle_ocr = None
        self._paddle_structure = None
        self._paddle_checked = False
        self._rapid_ocr = None
        self._rapid_checked = False
        self._winocr_checked = False
        self._winocr_available = False
        self._tesseract_checked = False
        self._tesseract_available = False

    def _init_paddle_ocr(self):
        if self._paddle_checked:
            return self._paddle_ocr
        with self._lock:
            if self._paddle_checked:
                return self._paddle_ocr
            self._paddle_checked = True
            if os.environ.get("CASHIQ_DISABLE_PADDLEOCR", "").lower() in {"1", "true", "yes"}:
                return None
            try:
                import paddle  # noqa: F401
                from paddleocr import PaddleOCR
                # CPU-only safe initialization
                try:
                    self._paddle_ocr = PaddleOCR(
                        use_textline_orientation=True,
                        lang="en",
                        device="cpu",
                    )
                except TypeError:
                    self._paddle_ocr = PaddleOCR(
                        use_angle_cls=True,
                        lang="en",
                        use_gpu=False,
                        show_log=False,
                    )
            except Exception:
                self._paddle_ocr = None
        return self._paddle_ocr

    def _init_paddle_structure(self):
        """Lazily initializes PP-StructureV3 ONLY when layout/table extraction is needed."""
        if self._paddle_structure is not None:
            return self._paddle_structure
        if not self._init_paddle_ocr():
            return None
        with self._lock:
            if self._paddle_structure is not None:
                return self._paddle_structure
            try:
                from paddleocr import PPStructureV3
                self._paddle_structure = PPStructureV3(device="cpu")
            except Exception:
                self._paddle_structure = None
        return self._paddle_structure

    def _init_rapid_ocr(self):
        if self._rapid_checked:
            return self._rapid_ocr
        with self._lock:
            if self._rapid_checked:
                return self._rapid_ocr
            self._rapid_checked = True
            if os.environ.get("CASHIQ_DISABLE_RAPIDOCR", "").lower() in {"1", "true", "yes"}:
                return None
            try:
                from rapidocr import RapidOCR
                self._rapid_ocr = RapidOCR()
            except Exception as e:
                print(f"[OCREngineManager] RapidOCR unavailable: {e}")
                self._rapid_ocr = None
        return self._rapid_ocr

    def _check_winocr(self) -> bool:
        if not self._winocr_checked:
            self._winocr_checked = True
            try:
                import winocr  # noqa: F401
                self._winocr_available = True
            except Exception:
                self._winocr_available = False
        return self._winocr_available

    def _check_tesseract(self) -> bool:
        if not self._tesseract_checked:
            self._tesseract_checked = True
            try:
                import pytesseract
                pytesseract.get_tesseract_version()
                self._tesseract_available = True
            except Exception:
                self._tesseract_available = False
        return self._tesseract_available

    def get_available_engines(self) -> Dict[str, bool]:
        return {
            "paddleocr": self._init_paddle_ocr() is not None,
            "rapidocr_ppocr": self._init_rapid_ocr() is not None,
            "winocr": self._check_winocr(),
            "pytesseract": self._check_tesseract(),
        }

    def _run_paddle_single(self, img: Image.Image, use_structure: bool = False) -> Optional[OCRResult]:
        t0 = time.perf_counter()
        arr = np.array(img.convert("RGB"))
        if use_structure:
            struct_engine = self._init_paddle_structure()
            if struct_engine is not None:
                try:
                    out = struct_engine.predict(arr)
                    boxes: List[OCRBox] = []
                    tables: List[List[List[str]]] = []
                    for page_res in out or []:
                        rec_texts = getattr(page_res, "rec_texts", None) or (page_res.get("rec_texts") if isinstance(page_res, dict) else [])
                        rec_scores = getattr(page_res, "rec_scores", None) or (page_res.get("rec_scores") if isinstance(page_res, dict) else [])
                        rec_polys = getattr(page_res, "rec_polys", None) or (page_res.get("rec_polys") if isinstance(page_res, dict) else [])
                        for txt, sc, poly in zip(rec_texts or [], rec_scores or [], rec_polys or []):
                            if str(txt).strip():
                                boxes.append(OCRBox(
                                    text=str(txt).strip(),
                                    confidence=float(sc),
                                    bbox=_polygon_to_bbox(poly),
                                    engine="paddleocr_structure_v3",
                                ))
                    if boxes:
                        lines, full_text = group_boxes_into_lines(boxes)
                        return OCRResult(
                            boxes=boxes,
                            lines=lines,
                            text=full_text,
                            mean_confidence=float(np.mean([b.confidence for b in boxes])),
                            engine="paddleocr_structure_v3",
                            layout_tables=tables,
                            processing_ms=round((time.perf_counter() - t0) * 1000, 1),
                        )
                except Exception:
                    pass

        engine = self._init_paddle_ocr()
        if engine is None:
            return None
        try:
            boxes = []
            if hasattr(engine, "predict"):
                res_list = engine.predict(arr)
                for res in res_list or []:
                    rec_texts = res.get("rec_texts", []) if isinstance(res, dict) else getattr(res, "rec_texts", [])
                    rec_scores = res.get("rec_scores", []) if isinstance(res, dict) else getattr(res, "rec_scores", [])
                    rec_polys = res.get("rec_polys", []) if isinstance(res, dict) else getattr(res, "rec_polys", [])
                    for txt, sc, poly in zip(rec_texts or [], rec_scores or [], rec_polys or []):
                        if str(txt).strip():
                            boxes.append(OCRBox(
                                text=str(txt).strip(),
                                confidence=float(sc),
                                bbox=_polygon_to_bbox(poly),
                                engine="paddleocr_ppocr",
                            ))
            else:
                res = engine.ocr(arr, cls=True)
                for page in res or []:
                    for item in page or []:
                        poly, (txt, sc) = item[0], item[1]
                        if str(txt).strip():
                            boxes.append(OCRBox(
                                text=str(txt).strip(),
                                confidence=float(sc),
                                bbox=_polygon_to_bbox(poly),
                                engine="paddleocr_ppocr",
                            ))
            lines, full_text = group_boxes_into_lines(boxes)
            mean_c = float(np.mean([b.confidence for b in boxes])) if boxes else 0.0
            return OCRResult(
                boxes=boxes,
                lines=lines,
                text=full_text,
                mean_confidence=mean_c,
                engine="paddleocr_ppocr",
                processing_ms=round((time.perf_counter() - t0) * 1000, 1),
            )
        except Exception as e:
            print(f"[OCREngineManager] PaddleOCR error: {e}")
            return None

    def _run_rapid_single(self, img: Image.Image) -> Optional[OCRResult]:
        engine = self._init_rapid_ocr()
        if engine is None:
            return None
        t0 = time.perf_counter()
        try:
            arr = np.array(img.convert("RGB"))
            # RapidOCR expects BGR numpy array when given ndarray
            bgr = arr[:, :, ::-1].copy()
            res = engine(bgr)
            boxes: List[OCRBox] = []

            if res is not None and hasattr(res, "txts") and res.txts is not None:
                txts = res.txts or ()
                scores = res.scores if getattr(res, "scores", None) is not None else [0.85] * len(txts)
                polys = res.boxes if getattr(res, "boxes", None) is not None else [None] * len(txts)
                for txt, sc, poly in zip(txts, scores, polys):
                    s = str(txt).strip()
                    if not s:
                        continue
                    bbox = _polygon_to_bbox(poly) if poly is not None else [0.0, 0.0, 0.0, 0.0]
                    boxes.append(OCRBox(
                        text=s,
                        confidence=float(sc),
                        bbox=bbox,
                        polygon=poly.tolist() if hasattr(poly, "tolist") else None,
                        engine="rapidocr_ppocr",
                    ))
            elif isinstance(res, tuple) and res[0]:
                for item in res[0]:
                    poly, txt, sc = item[0], item[1], item[2]
                    s = str(txt).strip()
                    if s:
                        boxes.append(OCRBox(
                            text=s,
                            confidence=float(sc),
                            bbox=_polygon_to_bbox(poly),
                            engine="rapidocr_ppocr",
                        ))

            lines, full_text = group_boxes_into_lines(boxes)
            mean_c = float(np.mean([b.confidence for b in boxes])) if boxes else 0.0
            return OCRResult(
                boxes=boxes,
                lines=lines,
                text=full_text,
                mean_confidence=mean_c,
                engine="rapidocr_ppocr",
                processing_ms=round((time.perf_counter() - t0) * 1000, 1),
            )
        except Exception as e:
            print(f"[OCREngineManager] RapidOCR error: {e}")
            return None

    async def _run_winocr_single(self, img: Image.Image) -> Optional[OCRResult]:
        if not self._check_winocr():
            return None
        t0 = time.perf_counter()
        try:
            import winocr
            res = await winocr.recognize_pil(img, "en")
            boxes: List[OCRBox] = []
            if hasattr(res, "lines") and res.lines:
                for line in res.lines:
                    txt = (getattr(line, "text", "") or "").strip()
                    if not txt:
                        continue
                    words = getattr(line, "words", None) or []
                    if words:
                        xs1, ys1, xs2, ys2 = [], [], [], []
                        for w in words:
                            br = getattr(w, "bounding_rect", None)
                            if br is not None:
                                xs1.append(float(br.x))
                                ys1.append(float(br.y))
                                xs2.append(float(br.x + br.width))
                                ys2.append(float(br.y + br.height))
                        bbox = [min(xs1), min(ys1), max(xs2), max(ys2)] if xs1 else [0.0, 0.0, 0.0, 0.0]
                    else:
                        bbox = [0.0, 0.0, 0.0, 0.0]
                    boxes.append(OCRBox(text=txt, confidence=0.82, bbox=bbox, engine="winocr"))
            elif isinstance(res, dict):
                for line in res.get("lines", []):
                    txt = (line.get("text") or "").strip()
                    if txt:
                        boxes.append(OCRBox(text=txt, confidence=0.82, bbox=[0.0, 0.0, 0.0, 0.0], engine="winocr"))

            lines, full_text = group_boxes_into_lines(boxes)
            if not full_text and hasattr(res, "text") and res.text:
                full_text = res.text.strip()
            mean_c = float(np.mean([b.confidence for b in boxes])) if boxes else 0.0
            return OCRResult(
                boxes=boxes,
                lines=lines,
                text=full_text,
                mean_confidence=mean_c,
                engine="winocr",
                processing_ms=round((time.perf_counter() - t0) * 1000, 1),
            )
        except Exception as e:
            print(f"[OCREngineManager] winocr error: {e}")
            return None

    def _run_tesseract_single(self, img: Image.Image) -> Optional[OCRResult]:
        if not self._check_tesseract():
            return None
        t0 = time.perf_counter()
        try:
            import pytesseract
            data = pytesseract.image_to_data(img, output_type=pytesseract.Output.DICT)
            boxes: List[OCRBox] = []
            n = len(data.get("text", []))
            for i in range(n):
                txt = (data["text"][i] or "").strip()
                conf_raw = float(data["conf"][i]) if str(data["conf"][i]).lstrip("-").isdigit() else -1.0
                if not txt or conf_raw < 0:
                    continue
                x = float(data["left"][i])
                y = float(data["top"][i])
                w = float(data["width"][i])
                h = float(data["height"][i])
                boxes.append(OCRBox(
                    text=txt,
                    confidence=max(0.0, min(1.0, conf_raw / 100.0)),
                    bbox=[x, y, x + w, y + h],
                    engine="pytesseract",
                ))
            lines, full_text = group_boxes_into_lines(boxes)
            mean_c = float(np.mean([b.confidence for b in boxes])) if boxes else 0.0
            return OCRResult(
                boxes=boxes,
                lines=lines,
                text=full_text,
                mean_confidence=mean_c,
                engine="pytesseract",
                processing_ms=round((time.perf_counter() - t0) * 1000, 1),
            )
        except Exception as e:
            print(f"[OCREngineManager] pytesseract error: {e}")
            return None

    async def _run_primary_single(
        self,
        img: Image.Image,
        preferred_engine: Optional[str] = None,
        use_structure: bool = False,
    ) -> OCRResult:
        """Runs a single OCR pass using the configured/best available backend."""
        if preferred_engine == "winocr":
            r = await self._run_winocr_single(img)
            if r is not None:
                return r
        elif preferred_engine == "rapidocr":
            r = await asyncio.to_thread(self._run_rapid_single, img)
            if r is not None:
                return r
        elif preferred_engine == "paddleocr":
            r = await asyncio.to_thread(self._run_paddle_single, img, use_structure)
            if r is not None:
                return r
        elif preferred_engine == "tesseract":
            r = await asyncio.to_thread(self._run_tesseract_single, img)
            if r is not None:
                return r

        # Default priority: PaddleOCR (if installed) -> RapidOCR (PP-OCR ONNX CPU) -> WinOCR -> Tesseract
        for fn in [
            lambda: asyncio.to_thread(self._run_paddle_single, img, use_structure),
            lambda: asyncio.to_thread(self._run_rapid_single, img),
            lambda: self._run_winocr_single(img),
            lambda: asyncio.to_thread(self._run_tesseract_single, img),
        ]:
            r = await fn()
            if r is not None and (r.boxes or r.text.strip()):
                return r

        return OCRResult(boxes=[], lines=[], text="", mean_confidence=0.0, engine="none")

    async def _targeted_retry_low_confidence_boxes(
        self,
        img: Image.Image,
        result: OCRResult,
        preferred_engine: Optional[str] = None,
        confidence_threshold: float = 0.82,
        max_retries: int = 5,
    ) -> OCRResult:
        """
        Retries ONLY low-confidence boxes (prioritizing financial/numeric/date lines)
        using targeted upscaled crops rather than blindly reprocessing the full document.
        """
        if not result.boxes:
            return result

        # Prioritize boxes with low confidence, especially numeric/financial/date candidates
        candidates: List[Tuple[int, int, OCRBox]] = []
        for idx, b in enumerate(result.boxes):
            if b.confidence >= confidence_threshold:
                continue
            if b.x2 - b.x1 < 10 or b.y2 - b.y1 < 8:
                continue
            is_financial = bool(re.search(r"[\d₹\$]|total|tax|gst|date|sub|rs", b.text, re.IGNORECASE))
            priority = 0 if is_financial else 1
            candidates.append((priority, idx, b))

        if not candidates:
            return result

        candidates.sort(key=lambda item: (item[0], item[2].confidence))
        updated_boxes = list(result.boxes)
        retries = 0

        for _, idx, box in candidates[:max_retries]:
            crop = enhance_crop_for_retry(img, box.bbox, mode="clahe")
            if crop is None:
                continue
            retries += 1
            retry_res = await self._run_primary_single(crop, preferred_engine=preferred_engine)
            if retry_res.boxes:
                new_text = " ".join(rb.text.strip() for rb in retry_res.boxes if rb.text.strip()).strip()
                new_conf = float(np.mean([rb.confidence for rb in retry_res.boxes]))
                if new_text and new_conf > box.confidence + 0.03:
                    updated_boxes[idx] = OCRBox(
                        text=new_text,
                        confidence=new_conf,
                        bbox=box.bbox,
                        polygon=box.polygon,
                        engine=f"{box.engine}+retry",
                    )

        if retries > 0:
            lines, full_text = group_boxes_into_lines(updated_boxes)
            mean_c = float(np.mean([b.confidence for b in updated_boxes])) if updated_boxes else 0.0
            result.boxes = updated_boxes
            result.lines = lines
            result.text = full_text
            result.mean_confidence = mean_c
            result.retries_performed += retries

        return result

    async def recognize_image(
        self,
        raw_img: Image.Image,
        preferred_engine: Optional[str] = None,
        use_structure: bool = False,
        enable_targeted_retries: bool = True,
    ) -> OCRResult:
        """
        Full adaptive image OCR workflow:
        1. Normalize EXIF & alpha (retaining clean original).
        2. Assess quality metrics (resolution, sharpness, lighting, contrast, skew, perspective).
        3. For already-clear images, run OCR directly on original without degrading it.
        4. For degraded/skewed/low-light/photographed images (or weak initial OCR), run
           conditionally enhanced variant and compare scores against original!
        5. Detect sideways/upside-down orientations only if needed.
        6. Run targeted crop retries ONLY on low-confidence boxes.
        """
        t0 = time.perf_counter()
        orig_img = normalize_base_image(raw_img)
        metrics, quad = assess_image_quality(orig_img)

        image_looks_difficult = (
            metrics.is_low_res
            or metrics.is_blurry
            or metrics.is_low_light
            or metrics.is_low_contrast
            or metrics.needs_deskew
            or metrics.has_document_quad
        )

        best_img = orig_img
        best_res: Optional[OCRResult] = None

        # Step 1: Run on original image first (preserves sharp digital/clean images)
        orig_res = await self._run_primary_single(
            orig_img,
            preferred_engine=preferred_engine,
            use_structure=use_structure,
        )
        orig_res.variant_used = "original"
        best_res = orig_res
        best_score = _score_ocr_result(orig_res)

        # Step 2: Conditionally preprocess and compare ONLY if image quality indicates degradation
        # or initial OCR score/confidence is weak
        if image_looks_difficult or best_score < 0.72 or orig_res.mean_confidence < 0.80:
            enh_img = build_enhanced_variant(orig_img, metrics, quad=quad)
            enh_res = await self._run_primary_single(
                enh_img,
                preferred_engine=preferred_engine,
                use_structure=use_structure,
            )
            enh_res.variant_used = "enhanced"
            enh_score = _score_ocr_result(enh_res)
            if enh_score > best_score + 0.015:
                best_res = enh_res
                best_score = enh_score
                best_img = enh_img

            # Adaptive threshold fallback only for severely low-light/low-contrast or poor extraction
            if (metrics.is_low_light or best_score < 0.50) and (len(best_res.text.strip()) < 60 or best_res.mean_confidence < 0.75):
                bin_img = build_adaptive_threshold_variant(enh_img)
                bin_res = await self._run_primary_single(
                    bin_img,
                    preferred_engine=preferred_engine,
                    use_structure=False,
                )
                bin_res.variant_used = "adaptive_threshold"
                bin_score = _score_ocr_result(bin_res)
                if bin_score > best_score + 0.02:
                    best_res = bin_res
                    best_score = bin_score
                    best_img = bin_img

        # Step 3: Orientation detection & recovery (90/270/180 deg) when boxes are sideways
        # OR result score/text is weak
        is_sideways = _boxes_indicate_sideways_orientation(best_res.boxes)
        if is_sideways or best_score < 0.55 or len(best_res.text.strip()) < 30:
            base_for_rot = best_img
            # Test 270 and 90 first when sideways (PIL rotate(270) undoes rotate(90))
            candidate_angles = (270, 90, 180) if is_sideways else (90, 270, 180)
            for angle in candidate_angles:
                rot_img = base_for_rot.rotate(angle, expand=True)
                rot_res = await self._run_primary_single(
                    rot_img,
                    preferred_engine=preferred_engine,
                    use_structure=use_structure,
                )
                rot_score = _score_ocr_result(rot_res)
                if rot_score > best_score + 0.08:
                    rot_res.rotation_applied = angle
                    rot_res.variant_used = f"{best_res.variant_used}_rot{angle}"
                    best_res = rot_res
                    best_score = rot_score
                    best_img = rot_img
                    if best_score >= 0.78 and not _boxes_indicate_sideways_orientation(rot_res.boxes):
                        break

        # Step 4: Targeted retries ONLY on low-confidence boxes (never blindly re-OCR full doc)
        if enable_targeted_retries and best_res.boxes:
            best_res = await self._targeted_retry_low_confidence_boxes(
                best_img,
                best_res,
                preferred_engine=preferred_engine,
            )

        best_res.quality_metrics = metrics.to_dict()
        best_res.processing_ms = round((time.perf_counter() - t0) * 1000, 1)
        return best_res


ocr_engine_manager = OCREngineManager()
