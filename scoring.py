"""Confidence scoring + transparency label for Provenance Guard.

Implements the fusion spec from planning.md exactly:
    fused      = (p_llm + p_stylometric) / 2
    agreement  = 1 - |p_llm - p_stylometric|
    confidence = agreement, capped at 0.5 if the text is < 40 words

And the threshold table:
    likely_ai     : fused >= 0.70 AND confidence >= 0.70
    likely_human  : fused <= 0.30 AND confidence >= 0.70
    uncertain     : everything else
"""

# --- spec constants (single source of truth for the thresholds) ----------
SHORT_TEXT_WORD_THRESHOLD = 40   # below this, the stylometric signal is shaky
SHORT_TEXT_CONFIDENCE_CAP = 0.5
AI_PROB_THRESHOLD = 0.70         # fused >= this -> AI side
HUMAN_PROB_THRESHOLD = 0.30      # fused <= this -> human side
CONFIDENCE_THRESHOLD = 0.70      # need at least this much confidence to commit

_LABEL_TEXT = {
    "likely_ai": {
        "variant": "high_confidence_ai",
        "text": "Likely to be AI-generated. There are strong signals that "
                "this was written by AI (confidence: high).",
    },
    "likely_human": {
        "variant": "high_confidence_human",
        "text": "Likely to be created by a human. There are strong signals "
                "that a human wrote this (confidence: high).",
    },
    "uncertain": {
        "variant": "uncertain",
        "text": "Uncertain. Our analysis couldn't confidently tell whether "
                "this text was written by a human or by AI.",
    },
}


def score_content(p_llm, p_stylometric, text):
    """Fuse the two signal scores into a single attribution result.

    Returns:
        dict: {"ai_probability": float, "confidence": float, "label": str}
    """
    fused = (p_llm + p_stylometric) / 2
    agreement = 1.0 - abs(p_llm - p_stylometric)

    confidence = agreement
    if len(text.split()) < SHORT_TEXT_WORD_THRESHOLD:
        confidence = min(confidence, SHORT_TEXT_CONFIDENCE_CAP)

    if fused >= AI_PROB_THRESHOLD and confidence >= CONFIDENCE_THRESHOLD:
        label = "likely_ai"
    elif fused <= HUMAN_PROB_THRESHOLD and confidence >= CONFIDENCE_THRESHOLD:
        label = "likely_human"
    else:
        label = "uncertain"

    return {
        "ai_probability": round(fused, 4),
        "confidence": round(confidence, 4),
        "label": label,
    }


def build_transparency_label(label):
    """Map an attribution label to its reader-facing transparency label."""
    return _LABEL_TEXT[label]
