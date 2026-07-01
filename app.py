

import uuid

from dotenv import load_dotenv
from flask import Flask, jsonify, request
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

from audit_log import log_decision, read_log, record_appeal
from scoring import build_transparency_label, score_content
from signals import signal_llm, signal_stylometric

load_dotenv()  # load GROQ_API_KEY from .env

app = Flask(__name__)

# Rate limiting, keyed by client IP. Limits are applied per-route below; see the
# README ("Rate Limiting") for the chosen numbers and reasoning. In-memory
# storage is fine for local/dev; a shared store (e.g. Redis) is needed if the
# app ever runs behind more than one worker/process.
limiter = Limiter(
    get_remote_address,
    app=app,
    default_limits=[],
    storage_uri="memory://",
)


@app.errorhandler(429)
def ratelimit_exceeded(exc):
    """Return a JSON 429 (not Flask's default HTML) when a limit is hit."""
    return (
        jsonify({
            "error": "Rate limit exceeded. Please slow down and try again later.",
            "detail": str(exc.description),
        }),
        429,
    )


@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok"})


@app.route("/log", methods=["GET"])
def get_log():
    """Return the audit log entries as JSON, most recent first.

    Optional ?limit=N caps how many recent entries are returned.
    No auth here — this is for documentation and grading visibility; a real
    system would require authentication.
    """
    entries = list(reversed(read_log()))  # newest first
    limit = request.args.get("limit", type=int)
    if limit is not None and limit >= 0:
        entries = entries[:limit]
    return jsonify({"entries": entries})


@app.route("/submit", methods=["POST"])
@limiter.limit("10 per minute;100 per day")
def submit():
    """Accept text + creator_id and return an attribution result.

    Accepts JSON: {"text": str, "creator_id": str, "title"?: str}
    Returns JSON: content_id + attribution (Signal 1) + signal scores +
    placeholder confidence + placeholder transparency label.
    """
    body = request.get_json(silent=True) or {}
    text = (body.get("text") or "").strip()
    creator_id = (body.get("creator_id") or "").strip()

    # --- input validation -------------------------------------------------
    if not text:
        return jsonify({"error": "Field 'text' is required and cannot be empty."}), 400
    if not creator_id:
        return jsonify({"error": "Field 'creator_id' is required and cannot be empty."}), 400

    # --- unique id for this submission (needed by audit log + appeals) ----
    content_id = f"c_{uuid.uuid4().hex[:12]}"

    # --- Signal 1: LLM judge ----------------------------------------------
    s1 = signal_llm(text)
    p_llm = s1["ai_probability"]

    # --- Signal 2: stylometric heuristics ---------------------------------
    s2 = signal_stylometric(text)
    p_stylometric = s2["ai_probability"]

    # --- confidence fusion + label (per planning.md spec) -----------------
    result = score_content(p_llm, p_stylometric, text)
    label = result["label"]
    transparency_label = build_transparency_label(label)

    # --- audit log: write a structured entry for every submission ---------
    log_decision(
        content_id=content_id,
        creator_id=creator_id,
        attribution=label,
        confidence=result["confidence"],
        llm_score=p_llm,
        stylometric_score=p_stylometric,
        ai_probability=result["ai_probability"],
        llm_rationale=s1["rationale"],
    )

    return jsonify(
        {
            "content_id": content_id,
            "creator_id": creator_id,
            "attribution": {
                "label": label,
                "ai_probability": result["ai_probability"],
                "confidence": result["confidence"],
            },
            "signals": {
                "llm_judge": s1,
                "stylometric": s2,
            },
            "transparency_label": transparency_label,
            "status": "classified",
        }
    )


@app.route("/appeal", methods=["POST"])
def appeal():
    """Contest a classification.

    Accepts JSON: {"content_id": str, "creator_reasoning": str}
    On receipt: looks up the original decision, appends the appeal to its
    audit-log record, flips its status to "under_review", and returns a
    confirmation. No automatic re-classification — a human reviewer decides.
    """
    body = request.get_json(silent=True) or {}
    content_id = (body.get("content_id") or "").strip()
    creator_reasoning = (body.get("creator_reasoning") or "").strip()

    # --- input validation -------------------------------------------------
    if not content_id:
        return jsonify({"error": "Field 'content_id' is required and cannot be empty."}), 400
    if not creator_reasoning:
        return jsonify({"error": "Field 'creator_reasoning' is required and cannot be empty."}), 400

    # --- record the appeal against the original decision -------------------
    confirmation = record_appeal(content_id, creator_reasoning)
    if confirmation is None:
        return jsonify({"error": f"No decision found for content_id '{content_id}'."}), 404

    return jsonify(confirmation), 201


if __name__ == "__main__":
    app.run(debug=True, port=5000)
