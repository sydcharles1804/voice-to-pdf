"""Fill AcroForm fields in a PDF template and flatten the result.

Uses PyMuPDF (fitz) throughout:
  - Widget value assignment via widget.field_value + widget.update()
  - doc.bake() to flatten: burns every widget's appearance into the page
    content stream so the filled values become permanent, non-editable text.

Kept separate from the Celery task so it can be tested without a broker.
"""

import io

import fitz  # PyMuPDF

_TRUTHY = {"yes", "true", "1", "on", "checked", "x"}


def _is_truthy(value: str) -> bool:
    return value.strip().lower() in _TRUTHY


def fill_pdf(template_bytes: bytes, answers: dict[str, str]) -> bytes:
    """Write answer values into a PDF template's AcroForm fields, then flatten.

    Args:
        template_bytes: Raw bytes of the original PDF template.
        answers:        Mapping of AcroForm field name → answer string.
                        Fields absent from ``answers`` are left at their
                        default (usually blank).

    Returns:
        Filled, flattened PDF as raw bytes ready to upload to storage.
        The returned PDF has no interactive form fields — every value is
        rendered as ordinary page content.

    Checkbox handling:
        ``widget.on_state()`` returns the PDF's own export value for the
        checked state (usually "Yes" or "On" but varies by producer).
        We prefer this over hard-coding "/Yes" so the PDF viewer's
        appearance stream matches what the spec expects.
    """
    doc = fitz.open(stream=template_bytes, filetype="pdf")

    for page in doc:
        for widget in (page.widgets() or []):
            name = widget.field_name
            if name not in answers:
                continue

            raw = answers[name]

            if widget.field_type == fitz.PDF_WIDGET_TYPE_CHECKBOX:
                if _is_truthy(raw):
                    # on_state() returns the PDF's own "checked" export value.
                    try:
                        widget.field_value = widget.on_state()
                    except (AttributeError, TypeError):
                        widget.field_value = "Yes"
                else:
                    widget.field_value = "Off"
            else:
                # Text, dropdown, radio button, and everything else:
                # set the value directly and let the PDF producer render it.
                widget.field_value = raw

            widget.update()

    # Flatten: convert all widget appearance streams into static page content.
    # After bake() the document contains no AcroForm widgets — values are
    # burned in as graphics and cannot be edited by a PDF viewer.
    doc.bake()

    buf = io.BytesIO()
    doc.save(buf, garbage=4, deflate=True)
    doc.close()
    return buf.getvalue()
