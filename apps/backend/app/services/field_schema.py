"""Transform raw extractor output into the canonical field schema.

This module is intentionally thin — just a reshape with stable IDs.
The expensive work (PyMuPDF parsing, pdfplumber label search) lives in
pdf_extractor.py and runs once at upload time.  Every subsequent consumer
(session routes, AI agent) reads the stored schema from the pdfs table.
"""

import uuid
from typing import Any


def build_field_schema(raw_fields: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Convert extractor dicts into the canonical field schema.

    Input (one item from ``extract_fields``):
    ::

        {
          name, type, label, required, options,   # field metadata
          page,                                   # 0-indexed page number
          x, y, width, height,                   # PDF-point coordinates
        }

    Output (stored in ``pdfs.fields`` JSONB and returned to clients):
    ::

        {
          id:         str,         # stable UUID — assigned once at upload time
          name:       str,         # AcroForm internal key (/T)
          label:      str,         # resolved human label
          type:       str,         # text | checkbox | radiobutton | dropdown | signature
          required:   bool,
          options:    list[str],   # non-empty for dropdown fields only
          pageNumber: int,         # 1-indexed (human-facing page numbers)
          coords: {
            x:      float,         # left edge in PDF points (72 pt = 1 inch)
            y:      float,         # top edge in PDF points
            width:  float,
            height: float,
          },
        }

    ``pageNumber`` is 1-indexed so callers can display "page 1" without +1
    arithmetic everywhere.  The extractor stores 0-indexed ``page``; the
    conversion happens here and nowhere else.
    """
    schema: list[dict[str, Any]] = []
    for field in raw_fields:
        schema.append({
            "id":         str(uuid.uuid4()),
            "name":       field["name"],
            "label":      field["label"],
            "type":       field["type"],
            "required":   field["required"],
            "options":    field.get("options", []),
            "pageNumber": (field.get("page") or 0) + 1,
            "coords": {
                "x":      field.get("x"),
                "y":      field.get("y"),
                "width":  field.get("width"),
                "height": field.get("height"),
            },
        })
    return schema
