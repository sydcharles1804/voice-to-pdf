"""Fill AcroForm fields in a PDF template with user-provided answers.

Kept separate from the Celery task so it can be tested without a broker.
"""

import io

from pypdf import PdfReader, PdfWriter
from pypdf.generic import BooleanObject, NameObject

# Values callers might provide for a checkbox field that means "checked".
_TRUTHY = {"yes", "true", "1", "on", "checked", "x"}


def _normalise_checkbox(value: str) -> str:
    """Map human answers ('yes', 'true', …) to the PDF spec value '/Yes'."""
    return "/Yes" if value.strip().lower() in _TRUTHY else "/Off"


def fill_pdf(template_bytes: bytes, answers: dict[str, str]) -> bytes:
    """Write answer values into a PDF template's AcroForm fields.

    Args:
        template_bytes: Raw bytes of the original PDF template.
        answers:        Mapping of AcroForm field name → answer string.
                        Checkbox fields are normalised automatically.

    Returns:
        Filled PDF as raw bytes, ready to upload to storage.

    Notes:
        - Fields absent from ``answers`` are left blank.
        - Checkboxes receive '/Yes' or '/Off' regardless of case/phrasing.
        - ``auto_regenerate=False`` tells pypdf not to create new field
          widgets; we only update existing ones.
        - We call set_need_appearances_writer() so the filled values render
          correctly in PDF viewers that rely on the /NeedAppearances flag.
    """
    reader = PdfReader(io.BytesIO(template_bytes))
    writer = PdfWriter()
    writer.append(reader)

    # Build the normalised field map once — field type lookup from the reader.
    raw_fields = reader.get_fields() or {}
    normalised: dict[str, str] = {}
    for name, answer in answers.items():
        field = raw_fields.get(name, {})
        ft = str(field.get("/FT", "/Tx"))
        if ft == "/Btn":
            normalised[name] = _normalise_checkbox(answer)
        else:
            normalised[name] = answer

    # update_page_form_field_values operates per-page; call it on every page so
    # multi-page PDFs have all their fields filled regardless of field location.
    for page in writer.pages:
        writer.update_page_form_field_values(
            page,
            normalised,
            auto_regenerate=False,
        )

    # Signal to PDF viewers that appearance streams need regenerating.
    writer.set_need_appearances_writer()

    output = io.BytesIO()
    writer.write(output)
    return output.getvalue()
