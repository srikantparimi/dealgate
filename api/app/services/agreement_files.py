"""S24-AG1 B5 — the file rules every agreement upload enforces.

Standard copies, client copies and the existing ``POST /agreements`` and
``/replace`` all call :func:`check_upload`. The browser's content type is not
trusted: the extension decides the type and the first bytes must match it
(``%PDF-`` for PDF, ``PK 03 04`` for DOCX). The stored object name is
sanitised to letters, digits, dot, dash, underscore and space, with at most
80 characters before exactly one extension; the original name is kept for
display only (and always rendered escaped).
"""

from __future__ import annotations

import hashlib
import re
import unicodedata
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from fastapi import HTTPException, UploadFile

MAX_BYTES = 25 * 1024 * 1024  # 25 MiB, the same cap as SOW uploads
MAX_STORED_BASE = 80
MAX_DISPLAY_NAME = 255
CONTENT_TYPES: dict[str, str] = {
    "pdf": "application/pdf",
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
}
_MAGIC: dict[str, bytes] = {"pdf": b"%PDF-", "docx": b"PK\x03\x04"}
_EXT = re.compile(r"\.([A-Za-z0-9]+)$")
_KNOWN_TAIL = re.compile(r"(\.(pdf|docx))+$", re.IGNORECASE)
_UNSAFE = re.compile(r"[^A-Za-z0-9._\- ]+")
_SPACES = re.compile(r"\s+")
_TRAILING_GAP = re.compile(r"[\s.]+$")
# Invisible characters can disguise a name on screen (AG0): every control (Cc, C0 and C1), format character
# (Cf: bidi marks and overrides including U+061C, zero-width characters, the BOM) and line or paragraph
# separator (Zl, Zp) is removed from the display name.
_HIDDEN_CATEGORIES = frozenset({"Cc", "Cf", "Zl", "Zp"})


def _visible(text: str) -> str:
    """Drop invisible characters; line and paragraph separators become a space, whitespace controls stay
    whitespace (the callers collapse or replace them)."""
    out = []
    for ch in text:
        category = unicodedata.category(ch)
        if category in ("Zl", "Zp"):
            out.append(" ")
        elif category == "Cc" and ch.isspace():
            out.append(ch)
        elif category not in _HIDDEN_CATEGORIES:
            out.append(ch)
    return "".join(out)

# The wording matches the prototype's upload dialog.
MSG_TYPE = "Only PDF and Word (.docx) files can be uploaded."
MSG_TOO_LARGE = "This file is larger than 25 MB."
MSG_EMPTY = "This file is empty."
MSG_NOT_PDF = "This file is named .pdf but its contents are not a PDF."
MSG_NOT_DOCX = "This file is named .docx but its contents are not a Word document."


@dataclass(frozen=True)
class CheckedFile:
    """An upload that passed every rule."""

    content: bytes
    ext: str
    content_type: str
    display_name: str
    stored_name: str
    sha256: str

    @property
    def size(self) -> int:
        return len(self.content)


def _last_segment(name: str) -> str:
    return re.split(r"[\\/]", name or "")[-1]


def display_name(original: str | None) -> str:
    """The original file name for display: no path, trimmed, at most 255 characters (extension kept)."""
    name = _SPACES.sub(" ", _visible(_last_segment(original or ""))).strip() or "file"
    if len(name) <= MAX_DISPLAY_NAME:
        return name
    match = _EXT.search(name)
    tail = match.group(0) if match and len(match.group(0)) <= 10 else ""
    return name[: MAX_DISPLAY_NAME - len(tail)] + tail


def stored_name(original: str | None, ext: str) -> str:
    """Sanitised object name: safe characters, at most 80 before the dot, exactly one extension."""
    name = _visible(_last_segment(original or ""))
    match = _EXT.search(name)
    base = name[: -len(match.group(0))] if match else name
    # Strip every trailing known extension, also when a space or a dot separates them ("x.pdf .pdf",
    # "x.pdf..pdf", "Acme.docx .pdf"), so exactly one extension remains.
    while True:
        previous = base
        base = _KNOWN_TAIL.sub("", _TRAILING_GAP.sub("", base))
        if base == previous:
            break
    base = _UNSAFE.sub("_", base)
    base = _SPACES.sub(" ", base).strip(" .")
    base = base[:MAX_STORED_BASE].strip(" .") or "file"
    return f"{base}.{ext}"


def object_key(prefix: str, name: str, *, now: datetime | None = None) -> str:
    """``{prefix}/{UTC stamp}-{8 hex}-{name}``; the nonce keeps two uploads in one second apart."""
    stamp = (now or datetime.now(UTC)).strftime("%Y%m%dT%H%M%SZ")
    return f"{prefix.rstrip('/')}/{stamp}-{uuid.uuid4().hex[:8]}-{name}"


def client_copy_key(agreement_id: uuid.UUID, name: str) -> str:
    return object_key(f"agreements/{agreement_id}", name)


def standard_key(kind: str, name: str) -> str:
    return object_key(f"agreements/standard/{kind}", name)


def check_bytes(original_name: str | None, content: bytes) -> CheckedFile:
    """Apply every rule to bytes already read. Raises HTTPException 413, 415 or 422."""
    name = _last_segment(original_name or "")
    match = _EXT.search(name)
    ext = match.group(1).lower() if match else ""
    if ext not in CONTENT_TYPES:
        raise HTTPException(415, MSG_TYPE)
    if not content:
        raise HTTPException(422, MSG_EMPTY)
    if len(content) > MAX_BYTES:
        raise HTTPException(413, MSG_TOO_LARGE)
    if not content.startswith(_MAGIC[ext]):
        raise HTTPException(415, MSG_NOT_PDF if ext == "pdf" else MSG_NOT_DOCX)
    return CheckedFile(
        content=content,
        ext=ext,
        content_type=CONTENT_TYPES[ext],
        display_name=display_name(original_name),
        stored_name=stored_name(original_name, ext),
        sha256=hashlib.sha256(content).hexdigest(),
    )


async def check_upload(file: UploadFile) -> CheckedFile:
    """Read at most 25 MiB + 1 byte and apply every rule."""
    content = await file.read(MAX_BYTES + 1)
    return check_bytes(file.filename, content)


__all__ = [
    "CONTENT_TYPES", "CheckedFile", "MAX_BYTES", "MAX_STORED_BASE", "MSG_EMPTY", "MSG_NOT_DOCX", "MSG_NOT_PDF",
    "MSG_TOO_LARGE", "MSG_TYPE", "check_bytes", "check_upload", "client_copy_key", "display_name", "object_key",
    "standard_key", "stored_name",
]
