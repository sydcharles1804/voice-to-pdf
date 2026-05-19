"""PDF validation and AcroForm field extraction.

Kept separate from the route so it can be unit-tested without FastAPI.
"""

import io
from typing import Any

from pypdf import PdfReader

_PDF_MAGIC = b"%PDF"
MAX_BYTES = 25 * 1024 * 1024  # 25 MB


def validate_size(data: bytes) -> None:
    """Raise ValueError if the file exceeds the 25 MB cap."""
    if len(data) > MAX_BYTES:
        mb = len(data) / 1_048_576
        raise ValueError(f"File is {mb:.1f} MB — maximum allowed size is 25 MB")


def validate_magic(data: bytes) -> None:
    """Raise ValueError if the first 4 bytes are not the PDF magic sequence %PDF.

    Checking magic bytes (not just the file extension) catches renamed files and
    content-type spoofing before we do any further processing.
    """
    if data[:4] != _PDF_MAGIC:
        raise ValueError(
            "File is not a valid PDF — magic bytes check failed "
            f"(got {data[:4]!r}, expected {_PDF_MAGIC!r})"
        )


def extract_fields(data: bytes) -> tuple[int, list[dict[str, Any]]]:
    """Parse a PDF and return (page_count, field_schema).

    field_schema is a list of dicts:
        {
          "name":     str,           # internal AcroForm field key
          "type":     str,           # "text" | "checkbox" | "dropdown" | "signature"
          "label":    str,           # /TU tooltip if present, otherwise field name
          "required": bool,          # PDF /Ff Required bit
          "options":  list[str],     # non-empty only for "dropdown" type
        }

    Returns an empty list for PDFs with no fillable AcroForm fields.
    """
    reader = PdfReader(io.BytesIO(data))
    page_count = len(reader.pages)
    raw = reader.get_fields() or {}

    _type_map = {
        "/Tx":  "text",
        "/Btn": "checkbox",
        "/Ch":  "dropdown",
        "/Sig": "signature",
    }

    fields: list[dict[str, Any]] = []
    for name, field in raw.items():
        ft = str(field.get("/FT", "/Tx"))
        field_type = _type_map.get(ft, "text")

        # /Ff is a 32-bit flag integer; bit 1 (value 2) = Required in the PDF spec
        flags = int(field.get("/Ff", 0))
        required = bool(flags & 2)

        # /TU is the user-visible tooltip — the best label candidate in AcroForms
        label = str(field.get("/TU") or name)

        options: list[str] = []
        if field_type == "dropdown":
            for opt in field.get("/Opt", []):
                # /Opt entries can be strings or [export_value, display_value] pairs
                options.append(str(opt[1]) if isinstance(opt, (list, tuple)) else str(opt))

        fields.append({
            "name": name,
            "type": field_type,
            "label": label,
            "required": required,
            "options": options,
        })

    return page_count, fields
