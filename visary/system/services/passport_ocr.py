from __future__ import annotations

import re
from datetime import date
from io import BytesIO
from shutil import which

import cv2
import numpy as np
import pypdfium2 as pdfium
import pytesseract
from rapidocr_onnxruntime import RapidOCR


class PassportExtractionError(Exception):
    pass


_OCR_ENGINE: RapidOCR | None = None
_TESSERACT_AVAILABLE: bool | None = None
_SUPPORTED_EXTENSIONS = {".png", ".jpg", ".jpeg", ".pdf"}


def extract_passport_data_from_document(uploaded_file) -> dict[str, object]:
    file_bytes = uploaded_file.read()
    if not file_bytes:
        raise PassportExtractionError("Arquivo vazio. Envie um PNG, JPG ou PDF de passaporte.")

    if not _is_supported_file(uploaded_file.name):
        raise PassportExtractionError("Formato não suportado. Use PNG, JPG ou PDF.")

    is_pdf = uploaded_file.name.lower().endswith(".pdf")
    images = _extract_images(uploaded_file.name, file_bytes)
    lines_by_source = _collect_lines_multisource(images, file_bytes=file_bytes, is_pdf=is_pdf)
    lines = _merge_multisource_lines(lines_by_source)
    mrz_lines = _extract_mrz_lines(lines)
    fields = _build_fields(lines_by_source, mrz_lines)
    warnings = _build_warnings(fields, mrz_lines, lines_by_source)
    return {"fields": fields, "warnings": warnings, "raw_lines": lines[:20]}


def _is_supported_file(filename: str) -> bool:
    lowered = (filename or "").lower()
    return any(lowered.endswith(ext) for ext in _SUPPORTED_EXTENSIONS)


def _extract_images(filename: str, file_bytes: bytes) -> list[np.ndarray]:
    if filename.lower().endswith(".pdf"):
        images = _render_pdf_pages(file_bytes)
        if images:
            return images
        raise PassportExtractionError("Não foi possível renderizar as páginas do PDF.")

    image = _decode_image(file_bytes)
    if image is None:
        raise PassportExtractionError("Não foi possível abrir a imagem enviada.")
    return [image]


def _render_pdf_pages(file_bytes: bytes, max_pages: int = 2) -> list[np.ndarray]:
    pdf = pdfium.PdfDocument(BytesIO(file_bytes))
    try:
        total_pages = len(pdf)
        images: list[np.ndarray] = []
        for index in range(min(total_pages, max_pages)):
            pil_image = pdf[index].render(scale=2).to_pil().convert("RGB")
            images.append(np.array(pil_image))
        return images
    finally:
        pdf.close()


def _decode_image(file_bytes: bytes) -> np.ndarray | None:
    np_bytes = np.frombuffer(file_bytes, dtype=np.uint8)
    return cv2.imdecode(np_bytes, cv2.IMREAD_COLOR)


def _collect_lines_multisource(
    images: list[np.ndarray],
    *,
    file_bytes: bytes,
    is_pdf: bool,
) -> dict[str, list[str]]:
    sources: dict[str, list[str]] = {
        "rapidocr": _collect_lines_with_rapidocr(images),
        "pytesseract": _collect_lines_with_tesseract(images),
    }
    if is_pdf:
        sources["pdfminer"] = _extract_pdf_text_lines(file_bytes)
    return {name: _deduplicate_lines(lines) for name, lines in sources.items() if lines}


def _collect_lines_with_rapidocr(images: list[np.ndarray]) -> list[str]:
    lines: list[str] = []
    for image in images:
        candidates = _image_candidates_for_ocr(image)
        for candidate in candidates:
            lines.extend(_run_rapidocr(candidate))
    return lines


def _collect_lines_with_tesseract(images: list[np.ndarray]) -> list[str]:
    if not _is_tesseract_available():
        return []
    lines: list[str] = []
    config = "--oem 1 --psm 6"
    for image in images:
        candidates = _image_candidates_for_ocr(image)
        for candidate in candidates:
            try:
                text = pytesseract.image_to_string(candidate, lang="eng", config=config)
            except Exception:
                return []
            lines.extend(line.strip() for line in text.splitlines() if line.strip())
    return lines


def _extract_pdf_text_lines(file_bytes: bytes) -> list[str]:
    try:
        from pdfminer.high_level import extract_text as pdfminer_extract_text

        text = pdfminer_extract_text(BytesIO(file_bytes))
    except Exception:
        return []
    return [line.strip() for line in text.splitlines() if line.strip()]


def _merge_multisource_lines(lines_by_source: dict[str, list[str]]) -> list[str]:
    merged: list[str] = []
    for lines in lines_by_source.values():
        merged.extend(lines)
    return _deduplicate_lines(merged)


def _image_candidates_for_ocr(image: np.ndarray) -> list[np.ndarray]:
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    resized = cv2.resize(gray, None, fx=2.0, fy=2.0, interpolation=cv2.INTER_CUBIC)
    _, thresholded = cv2.threshold(resized, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    rgb_original = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
    rgb_thresholded = cv2.cvtColor(thresholded, cv2.COLOR_GRAY2RGB)
    return [rgb_original, rgb_thresholded]


def _run_rapidocr(image: np.ndarray) -> list[str]:
    result, _ = _get_ocr_engine()(image)
    if not result:
        return []
    lines: list[str] = []
    for _, text, confidence in result:
        confidence_value = float(confidence)
        if confidence_value >= 0.35 and text.strip():
            lines.append(text.strip())
    return lines


def _is_tesseract_available() -> bool:
    global _TESSERACT_AVAILABLE
    if _TESSERACT_AVAILABLE is None:
        _TESSERACT_AVAILABLE = which("tesseract") is not None
    return _TESSERACT_AVAILABLE


def _get_ocr_engine() -> RapidOCR:
    global _OCR_ENGINE
    if _OCR_ENGINE is None:
        _OCR_ENGINE = RapidOCR()
    return _OCR_ENGINE


def _deduplicate_lines(lines: list[str]) -> list[str]:
    seen: set[str] = set()
    deduped: list[str] = []
    for line in lines:
        norm = re.sub(r"\s+", " ", line).strip().upper()
        if norm and norm not in seen:
            seen.add(norm)
            deduped.append(line)
    return deduped


def _extract_mrz_lines(lines: list[str]) -> list[str]:
    candidates = [_normalize_mrz_text(line) for line in lines]
    candidates = [line for line in candidates if line.count("<") >= 2 and len(line) >= 30]
    candidates.sort(key=lambda value: (value.count("<"), len(value)), reverse=True)
    return candidates[:2]


def _normalize_mrz_text(text: str) -> str:
    normalized = text.upper().replace(" ", "").replace("«", "<")
    return re.sub(r"[^A-Z0-9<]", "", normalized)


def _build_fields(lines_by_source: dict[str, list[str]], mrz_lines: list[str]) -> dict[str, str]:
    lines = _merge_multisource_lines(lines_by_source)
    fields = _fields_from_mrz(mrz_lines)
    if not fields.get("numero_passaporte"):
        passport_number = _extract_passport_number(lines)
        if passport_number:
            fields["numero_passaporte"] = passport_number
    if not fields.get("nome") and not fields.get("sobrenome"):
        fallback_name = _extract_name_with_consensus(lines_by_source)
        if fallback_name:
            parts = fallback_name.split(None, 1)
            fields["nome"] = parts[0]
            if len(parts) > 1:
                fields["sobrenome"] = parts[1]
    return {key: value for key, value in fields.items() if value}


def _fields_from_mrz(mrz_lines: list[str]) -> dict[str, str]:
    if len(mrz_lines) < 2:
        return {}
    line1, line2 = mrz_lines[0], mrz_lines[1]
    if len(line1) < 30 or len(line2) < 30:
        return {}

    surname, given_names = _split_mrz_name(line1[5:44])
    fields = {
        "nome": given_names,
        "sobrenome": surname,
        "tipo_passaporte": "comum" if line1.startswith("P<") else "",
        "numero_passaporte": line2[0:9].replace("<", ""),
        "pais_emissor_passaporte": line1[2:5].replace("<", ""),
        "nacionalidade": line2[10:13].replace("<", ""),
        "data_nascimento": _parse_mrz_date(line2[13:19], past=True),
        "valido_ate_passaporte": _parse_mrz_date(line2[21:27], past=False),
    }
    return fields


def _split_mrz_name(name_block: str) -> tuple[str, str]:
    parts = name_block.split("<<", 1)
    surname = parts[0].replace("<", " ").strip()
    given = parts[1].replace("<", " ").strip() if len(parts) > 1 else ""
    return _format_name(surname), _format_name(given)


def _format_name(value: str) -> str:
    return " ".join(token.capitalize() for token in value.split() if token)


def _parse_mrz_date(value: str, past: bool) -> str:
    cleaned = re.sub(r"\D", "", value or "")
    if len(cleaned) != 6:
        return ""
    yy, mm, dd = int(cleaned[:2]), int(cleaned[2:4]), int(cleaned[4:6])
    century = _resolve_century(yy, past)
    try:
        return date(century + yy, mm, dd).isoformat()
    except ValueError:
        return ""


def _resolve_century(year_two_digits: int, past: bool) -> int:
    current_year = date.today().year % 100
    if past:
        return 2000 if year_two_digits <= current_year else 1900
    return 2000 if year_two_digits <= current_year + 20 else 1900


def _extract_passport_number(lines: list[str]) -> str:
    merged = "\n".join(lines)
    patterns = [
        r"PASSPORT\s*NO\.?\s*[:#-]?\s*([A-Z0-9]{6,10})",
        r"N[ÚU]MERO\s*DO\s*PASSAPORTE\s*[:#-]?\s*([A-Z0-9]{6,10})",
        r"\b([A-Z]{1,2}[0-9]{6,8})\b",
    ]
    for pattern in patterns:
        if match := re.search(pattern, merged, flags=re.IGNORECASE):
            return match.group(1).upper()
    return ""


def _extract_name_with_consensus(lines_by_source: dict[str, list[str]]) -> str:
    candidates: list[str] = []
    for lines in lines_by_source.values():
        if name_candidate := _extract_name_labeled(lines):
            candidates.append(name_candidate)
    return _pick_consensus(candidates, min_votes=2)


def _extract_name_labeled(lines: list[str]) -> str:
    label_patterns = [
        r"^(?:NOME|NAME)\s*[:\-]\s*(.+)$",
        r"^(?:SOBRENOME|SURNAME)\s*[:\-]\s*(.+)$",
        r"^(?:GIVEN\s+NAMES?|PRENOM|PRENOMS)\s*[:\-]\s*(.+)$",
    ]

    for line in lines:
        upper_line = line.upper().strip()
        for pattern in label_patterns:
            if match := re.match(pattern, upper_line):
                candidate = _format_name(match.group(1))
                if _is_valid_name_candidate(candidate):
                    return candidate
    return ""


def _is_valid_name_candidate(candidate: str) -> bool:
    cleaned = candidate.strip()
    if not cleaned or len(cleaned.split()) < 2:
        return False
    blocked = {
        "PASSPORT",
        "ASSINATURA",
        "SIGNATURE",
        "TITULAR",
        "TITULAIRE",
        "DOCUMENT",
    }
    upper = cleaned.upper()
    return all(token not in upper for token in blocked)


def _pick_consensus(candidates: list[str], min_votes: int) -> str:
    normalized_map: dict[str, tuple[str, int]] = {}
    for candidate in candidates:
        key = re.sub(r"\s+", " ", candidate).strip().upper()
        display = _format_name(candidate)
        count = normalized_map.get(key, (display, 0))[1] + 1
        normalized_map[key] = (display, count)
    if not normalized_map:
        return ""
    best_display, best_votes = max(normalized_map.values(), key=lambda item: item[1])
    if best_votes >= min_votes and _is_valid_name_candidate(best_display):
        return best_display
    return ""


def _build_warnings(
    fields: dict[str, str],
    mrz_lines: list[str],
    lines_by_source: dict[str, list[str]],
) -> list[str]:
    warnings: list[str] = []
    if len(mrz_lines) < 2:
        warnings.append("MRZ não identificada com confiança alta.")
    if len(lines_by_source) < 2:
        warnings.append("Apenas um motor de análise disponível neste ambiente.")
    if "pytesseract" not in lines_by_source:
        warnings.append("Tesseract OCR indisponível localmente; extração baseada em motores alternativos.")
    if not fields:
        warnings.append("Nenhum campo confiável foi extraído do documento.")
    elif len(fields) < 3:
        warnings.append("Extração parcial. Revise cuidadosamente os dados antes de salvar.")
    return warnings
