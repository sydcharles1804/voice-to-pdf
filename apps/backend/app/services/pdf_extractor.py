"""PDF validation and AcroForm field extraction.

Uses PyMuPDF (fitz) for widget metadata and bounding-rect positions,
and pdfplumber to locate visible label text near each widget when
the field name is not human-readable (e.g. 'field_142').
"""

import io
from typing import Any

import fitz  # PyMuPDF
import pdfplumber

_PDF_MAGIC = b"%PDF"
MAX_BYTES = 25 * 1024 * 1024  # 25 MB

_FITZ_TYPE: dict[int, str] = {
    fitz.PDF_WIDGET_TYPE_TEXT:        "text",
    fitz.PDF_WIDGET_TYPE_CHECKBOX:    "checkbox",
    fitz.PDF_WIDGET_TYPE_RADIOBUTTON: "radiobutton",
    fitz.PDF_WIDGET_TYPE_LISTBOX:     "dropdown",
    fitz.PDF_WIDGET_TYPE_COMBOBOX:    "dropdown",
    fitz.PDF_WIDGET_TYPE_SIGNATURE:   "signature",
}

# Label search radii (PDF points; 72 pt = 1 inch)
_LEFT_REACH   = 200  # how far left to scan for a same-line label
_VERT_SLACK   =   6  # vertical half-band for "same line" alignment
_ABOVE_REACH  =  40  # how far above to scan for a stacked label
_HORIZ_SLACK  = 100  # horizontal tolerance for above-field search


def validate_size(data: bytes) -> None:
    if len(data) > MAX_BYTES:
        mb = len(data) / 1_048_576
        raise ValueError(f"File is {mb:.1f} MB — maximum allowed size is 25 MB")


def validate_magic(data: bytes) -> None:
    if data[:4] != _PDF_MAGIC:
        raise ValueError(
            "File is not a valid PDF — magic bytes check failed "
            f"(got {data[:4]!r}, expected {_PDF_MAGIC!r})"
        )


def _find_nearby_label(
    words: list[dict],
    fx0: float,
    fy0: float,
    fx1: float,
    fy1: float,
) -> str | None:
    """Return the most likely visible text label for a field at (fx0,fy0,fx1,fy1).

    Search order:
      1. Words on the same horizontal band immediately to the left  (inline label)
      2. Words in the line directly above the field                 (stacked label)

    Coordinates are in PDF points, top-left origin, y increasing downward —
    the same system used by both PyMuPDF rects and pdfplumber word dicts.
    """
    fc_y = (fy0 + fy1) / 2

    # ── inline label (to the left on the same line) ───────────────────────────
    left_words = sorted(
        [
            w for w in words
            if w["x1"] <= fx0 + 4                           # ends at or before field
            and w["x1"] >= fx0 - _LEFT_REACH               # within reach
            and abs((w["top"] + w["bottom"]) / 2 - fc_y) <= _VERT_SLACK
        ],
        key=lambda w: w["x0"],
    )
    if left_words:
        return " ".join(w["text"] for w in left_words)

    # ── stacked label (line above the field) ──────────────────────────────────
    above_words = sorted(
        [
            w for w in words
            if w["bottom"] <= fy0 + 4                       # ends at or before field top
            and w["bottom"] >= fy0 - _ABOVE_REACH          # within reach
            and w["x0"] >= fx0 - _HORIZ_SLACK
            and w["x0"] <= fx1 + _HORIZ_SLACK
        ],
        key=lambda w: w["x0"],
    )
    if above_words:
        return " ".join(w["text"] for w in above_words)

    return None


def extract_fields(data: bytes) -> tuple[int, list[dict[str, Any]]]:
    """Parse a PDF and return ``(page_count, field_schema)``.

    Each field dict:
    ::

        {
          "name":    str,       # internal AcroForm key (/T)
          "type":    str,       # text | checkbox | radiobutton | dropdown | signature
          "label":   str,       # /TU tooltip → nearby visible text → field name
          "required": bool,     # PDF /Ff Required bit (bit 1)
          "options": list[str], # non-empty for dropdown / listbox fields
          "page":    int,       # 0-indexed page number
          "x":       float,     # left edge in PDF points
          "y":       float,     # top edge in PDF points
          "width":   float,
          "height":  float,
        }

    Returns an empty list for PDFs with no fillable AcroForm fields.
    """
    doc = fitz.open(stream=data, filetype="pdf")
    page_count = doc.page_count

    # Extract words per page once with pdfplumber so label lookup is O(fields)
    # not O(fields × words).  If pdfplumber fails (e.g. encrypted PDF), we fall
    # back to an empty word list and rely on the /TU tooltip alone.
    words_per_page: list[list[dict]] = [[] for _ in range(page_count)]
    try:
        with pdfplumber.open(io.BytesIO(data)) as plumber_doc:
            for i, pl_page in enumerate(plumber_doc.pages):
                if i >= page_count:
                    break
                words_per_page[i] = pl_page.extract_words() or []
    except Exception:
        pass  # label search will fall back to field name

    fields: list[dict[str, Any]] = []

    for page_idx in range(page_count):
        page = doc[page_idx]
        page_words = words_per_page[page_idx]

        for widget in (page.widgets() or []):
            if widget.field_type not in _FITZ_TYPE:
                continue

            rect = widget.rect
            fx0, fy0, fx1, fy1 = rect.x0, rect.y0, rect.x1, rect.y1

            # Bit 1 (value 2) of /Ff = Required  (PDF 32000-1:2008 §12.7.3.1)
            required = bool((widget.field_flags or 0) & 2)

            # Label resolution: /TU tooltip → nearby text → field name
            tooltip = (widget.field_label or "").strip()
            if not tooltip:
                tooltip = (
                    _find_nearby_label(page_words, fx0, fy0, fx1, fy1)
                    or widget.field_name
                )

            options: list[str] = []
            if widget.field_type in (
                fitz.PDF_WIDGET_TYPE_LISTBOX,
                fitz.PDF_WIDGET_TYPE_COMBOBOX,
            ):
                options = list(widget.choice_values or [])

            fields.append({
                "name":     widget.field_name,
                "type":     _FITZ_TYPE[widget.field_type],
                "label":    tooltip,
                "required": required,
                "options":  options,
                "page":     page_idx,
                "x":        round(fx0, 2),
                "y":        round(fy0, 2),
                "width":    round(fx1 - fx0, 2),
                "height":   round(fy1 - fy0, 2),
            })

    doc.close()
    return page_count, fields
