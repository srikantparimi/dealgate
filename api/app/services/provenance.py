"""Per-field provenance helpers (Sprint 9 Wave 1, CLAUDE.md rule 10).

Every field the SOW pipeline persists carries a provenance envelope::

    {
        "value": <the actual value>,
        "provenance": "extracted" | "looked_up" | "calculated" | "defaulted" | "manual",
        "page_ref": <int or null>,
        "source_id": <uuid or null>,
        "confidence": <float 0..1 or null>,
        "warning": <string or null>,
        "status": "unconfirmed" | "confirmed" | "disputed",
    }

Backward compat: existing rows that are plain scalars or the legacy
``{value, page_ref, status}`` shape read back as ``manual`` (for the
scalar case) or preserve their provenance if already present. The
``status`` key is retained because the confirm workflow depends on it.
"""

from __future__ import annotations

from typing import Any


PROVENANCE_VALUES: frozenset[str] = frozenset(
    {"extracted", "looked_up", "calculated", "defaulted", "manual"}
)


def wrap(
    value: Any,
    *,
    provenance: str,
    page_ref: int | None = None,
    source_id: str | None = None,
    confidence: float | None = None,
    warning: str | None = None,
    status: str = "unconfirmed",
) -> dict[str, Any]:
    """Return a well-formed provenance envelope.

    ``provenance`` is validated so a typo never lands in the JSONB.
    """

    if provenance not in PROVENANCE_VALUES:
        raise ValueError(
            f"provenance must be one of {sorted(PROVENANCE_VALUES)}; got {provenance!r}"
        )
    return {
        "value": value,
        "provenance": provenance,
        "page_ref": page_ref,
        "source_id": source_id,
        "confidence": confidence,
        "warning": warning,
        "status": status,
    }


def read(entry: Any) -> dict[str, Any]:
    """Normalise any stored representation into the current envelope.

    - ``None`` becomes an empty ``manual`` envelope with ``value=None``.
    - A plain scalar / list / string is treated as ``manual``.
    - A legacy ``{value, page_ref, status}`` dict is upgraded to add
      ``provenance="extracted"`` (the historical write path was the
      Bedrock extractor).
    - A modern envelope is returned as-is with any missing keys
      filled in with defaults.
    """

    if entry is None:
        return wrap(None, provenance="manual")

    if not isinstance(entry, dict):
        return wrap(entry, provenance="manual")

    prov = entry.get("provenance")
    if prov is None:
        # Legacy row — infer "extracted" when we have a page_ref, else "manual".
        prov = "extracted" if entry.get("page_ref") else "manual"

    return {
        "value": entry.get("value"),
        "provenance": prov if prov in PROVENANCE_VALUES else "manual",
        "page_ref": entry.get("page_ref"),
        "source_id": entry.get("source_id"),
        "confidence": entry.get("confidence"),
        "warning": entry.get("warning"),
        "status": entry.get("status", "unconfirmed"),
    }


def value_of(entry: Any) -> Any:
    """Convenience: pull ``.value`` from whatever shape the row currently is."""

    return read(entry)["value"]


__all__ = ["PROVENANCE_VALUES", "read", "value_of", "wrap"]
