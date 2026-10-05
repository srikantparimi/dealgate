"""Human decisions over source-bound re-extraction candidates."""
import copy
import hashlib
import json
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.audit import append_audit
from app.services.sow_extract import SowReplayConflict, _mutable_source


class ConflictReview(BaseModel):
    model_config = ConfigDict(extra="forbid")
    review_token: str = Field(pattern=r"^[0-9a-f]{64}$")
    decision: Literal["keep_confirmed", "accept_candidate"]
    reason: str = Field(min_length=1, max_length=2000)

    @field_validator("reason")
    @classmethod
    def normalized_reason(cls, value):
        if not value.strip() or value != value.strip():
            raise ValueError("A normalized review reason is required")
        return value


def conflict_items(version):
    fields = version.extracted_fields or {}
    conflicts = (fields.get("metadata") or {}).get("reextract_conflicts") or {}
    items = []
    for name, candidate in sorted(conflicts.items()):
        current = fields.get(name)
        identity = {"version": str(version.id), "document_hash": version.file_hash,
            "model": version.extract_model, "prompt": version.extract_prompt_version,
            "field": name, "current": current, "candidate": candidate}
        token = hashlib.sha256(json.dumps(identity, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()
        items.append({"field": name, "current": copy.deepcopy(current),
            "candidate": copy.deepcopy(candidate), "review_token": token})
    return {"items": items}


async def resolve_conflict(session, *, actor_id, version_id, field, body: ConflictReview):
    version, _ = await _mutable_source(session, version_id)
    item = next((row for row in conflict_items(version)["items"] if row["field"] == field), None)
    if item is None or item["review_token"] != body.review_token:
        raise SowReplayConflict("Extraction review changed; reload the source conflict")
    fields = copy.deepcopy(version.extracted_fields)
    if body.decision == "accept_candidate":
        fields[field] = {**item["candidate"], "status": "confirmed"}
        if field == "engagement_type_suggested":
            value = fields[field].get("value")
            version.engagement_type_confirmed = str(value) if value is not None else None
    conflicts = fields["metadata"]["reextract_conflicts"]
    del conflicts[field]
    version.extracted_fields = fields
    if (version.extract_error or "").startswith("Re-extraction conflicts with confirmed fields:"):
        if conflicts:
            version.extract_error = "Re-extraction conflicts with confirmed fields: " + ", ".join(sorted(conflicts))
        else:
            version.extract_status, version.extract_error = "complete", None
    await append_audit(session, actor_id=actor_id, action="sow.extraction_conflict_resolved",
        entity="sow_version", entity_id=str(version.id),
        before={"field": field, "confirmed": item["current"], "candidate": item["candidate"]},
        after={"field": field, "decision": body.decision, "reason": body.reason,
            "review_token": body.review_token, "document_hash": version.file_hash,
            "confirmed": fields[field], "remaining_conflicts": sorted(conflicts)})
    return conflict_items(version)
