"""Structured audit log for Provenance Guard.

Every attribution decision is appended as a structured JSON record. Stored as a
JSON array on disk (audit_log.json) so it's easy to read for GET /log and easy
to update by content_id when appeals are added in Milestone 5.

Not print() statements; not SQLite (overkill for this project) — a single
append-only JSON file is structured, inspectable, and good enough here.
"""

import json
import os
import uuid
from datetime import datetime, timezone

_LOG_PATH = os.path.join(os.path.dirname(__file__), "audit_log.json")


def _now_iso():
    """UTC timestamp, ISO 8601 with milliseconds and a trailing 'Z'."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.") + \
        f"{datetime.now(timezone.utc).microsecond // 1000:03d}Z"


def _load():
    """Return the full log as a list (empty if the file is missing/corrupt)."""
    if not os.path.exists(_LOG_PATH):
        return []
    try:
        with open(_LOG_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return []


def _save(entries):
    with open(_LOG_PATH, "w", encoding="utf-8") as f:
        json.dump(entries, f, indent=2, ensure_ascii=False)


def log_decision(content_id, creator_id, attribution, confidence,
                 llm_score, stylometric_score, ai_probability,
                 llm_rationale=None, status="classified"):
    """Append one structured decision record and return it.

    Args:
        content_id:        unique id for the submission.
        creator_id:        who submitted it.
        attribution:       the label string (e.g. "likely_ai" / "uncertain").
        confidence:        final combined confidence score (0-1), or None.
        llm_score:         Signal 1 (Groq) ai_probability (0-1).
        stylometric_score: Signal 2 (stylometric) ai_probability (0-1).
        ai_probability:    fused ai_probability (0-1) — average of both signals.
        llm_rationale:     Signal 1's one-line rationale, for the appeal queue.
        status:            lifecycle status; "classified" on submit.

    Returns:
        dict: the record that was written.
    """
    entry = {
        "content_id": content_id,
        "creator_id": creator_id,
        "timestamp": _now_iso(),
        "attribution": attribution,
        "ai_probability": ai_probability,
        "confidence": confidence,
        "signals": {
            "llm_score": llm_score,
            "llm_rationale": llm_rationale,
            "stylometric_score": stylometric_score,
        },
        "status": status,
        # Always present so every record explicitly shows whether an appeal has
        # been filed: [] = none yet; populated once record_appeal() runs.
        "appeals": [],
    }
    entries = _load()
    entries.append(entry)
    _save(entries)
    return entry


def read_log():
    """Return all log entries (newest last). Used by GET /log."""
    return _load()


def get_entry(content_id):
    """Return the record for a content_id, or None. Used by appeals (M5)."""
    for entry in _load():
        if entry.get("content_id") == content_id:
            return entry
    return None


def record_appeal(content_id, reason):
    """Attach a creator's appeal to the original decision record.

    Looks up the record by content_id, appends the appeal to an `appeals` list
    on that record, and flips its status to "under_review". Persists the change.
    No automatic re-classification — a human reviewer decides later.

    Args:
        content_id: the id of the decision being appealed.
        reason:     the creator's written reasoning.

    Returns:
        dict: {"appeal_id", "content_id", "status", "logged_at"} on success,
        or None if no record exists for content_id.
    """
    entries = _load()
    for entry in entries:
        if entry.get("content_id") == content_id:
            logged_at = _now_iso()
            appeal_id = f"a_{uuid.uuid4().hex[:12]}"
            appeal = {
                "appeal_id": appeal_id,
                "reason": reason,
                "logged_at": logged_at,
            }
            entry.setdefault("appeals", []).append(appeal)
            entry["status"] = "under_review"
            _save(entries)
            return {
                "appeal_id": appeal_id,
                "content_id": content_id,
                "status": "under_review",
                "logged_at": logged_at,
            }
    return None
