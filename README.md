# ai201-project4-provenance-guard

Provenance Guard classifies text as AI or human written, returns a result based on confidence scoring logic, with a transparency label, and lets creators appeal if they think the system has misclassified the text.

## Detection Signals

2 signals: one statistical (form), one model-based (meaning).

**Signal 1 — LLM -Groq (llama-3.3-70b-versatile).**
Sends the text to a Groq LLM with a structured prompt asking how AI generated it reads,
catching semantic cues stats miss (generic content, even hedging, no specific detail).
**Output:** `ai_probability` between 0 and 1, plus a one line providing rationale.

**Signal 2 — Stylometric heuristics (local, deterministic).**
Measures sentence length variance, unique words / total
words, and the count of AI boilerplate phrases ("delve," "it's important to note,"
"moreover,"etc.). AI text tends to be evenly paced with safe vocabulary while
human text is more diverse.
**Output:** `ai_probability` between 0 and 1.

---
## Confidence Scoring
- `fused = (p_llm + p_stylometric) / 2` — the single AI probability.
- `agreement = 1 − |p_llm − p_stylometric|` — how much the two signals agree.
- `confidence = agreement` (capped at 0.5 if the text is shorter than ~40 words, since the
  stylometric signal is unreliable on short text).

When both signals agree, confidence is high.

**Example submissions**:

**High-confidence case** — a human written passage:

> "ok so i finally tried that new ramen place downtown and honestly? underwhelming. the
> broth was fine but they put WAY too much sodium in it and i was thirsty for like three
> hours after. my friend got the spicy version and said it was better. probably won't go
> back unless someone drags me there"

| p_llm | p_stylometric | fused | **confidence** | label |
|-------|---------------|-------|----------------|-------|
| 0.20  | 0.2631        | 0.2316| **0.9369**     | `likely_human` |

Both signals independently read it as human and agree closely, so confidence is
high (0.94) and the system labels it as `likely_human`.

**Lower-confidence case** — formal, evenly paced human writing (anticipated
hard case):

> "The relationship between monetary policy and asset price inflation has been extensively
> studied in the literature. Central banks face a fundamental tension between their mandate
> for price stability and the unintended consequences of prolonged low interest rates on
> equity and real estate valuations."

| p_llm | p_stylometric | fused | **confidence** | label |
|-------|---------------|-------|----------------|-------|
| 0.80  | 0.4154        | 0.6077| **0.6154**     | `uncertain` |

Rhe LLM leans AI (0.80) while the stylometric signal stays uncertain (0.42),
so the signals disagree, confidence drops to 0.62, and the system labels it `uncertain`.

The confidence gap between these two cases (0.94 vs 0.62) is exactly the
meaningful variation the score is meant to produce.

## Architecture

**Submission flow:** a creator sends raw text to `POST /submit`; the text is scored
independently by Signal 1 (Groq LLM) and Signal 2 (stylometric heuristics), the 2
scores are fused into one AI probability plus a confidence value, that result is mapped
to a transparency label, written to the audit log, and returned to the creator. 
**Appeal flow:** the creator sends a `content_id` plus their reasoning to `POST /appeal`; the system
looks up the original decision, flips its status to `under_review`, appends the appeal to
the audit log, and returns confirmation — no automatic re-classification.


### (1) Submission flow

```
                raw text {text, creator_id}
  creator ───────────────────────────────────▶  POST /submit  (Flask route)
                                                      │  raw text
                          ┌───────────────────────────┴───────────────────────────┐
                          │ raw text                                       raw text │
                          ▼                                                         ▼
              Signal 1: LLM judge (Groq)                          Signal 2: Stylometric
              llama-3.3-70b-versatile                             heuristics (local)
                          │  p_llm (0–1) + rationale                  p_stylometric (0–1) │
                          └───────────────────────────┬───────────────────────────┘
                                                       ▼  (p_llm, p_stylometric)
                                            Confidence scoring
                                            fused = avg ; confidence = agreement
                                                       │  fused prob + confidence
                                                       ▼
                                            Transparency label
                                            (AI / human / uncertain)
                                                       │  label text
                                                       ▼
                                            Audit log  ──▶ stores {id, scores, label, status}
                                                       │  full record
                                                       ▼
  creator ◀───────────────  JSON: attribution + confidence + signal scores + label text
```

### (2) Appeal flow

```
  creator ──{content_id, creator_reasoning}──▶  POST /appeal  (Flask route)
                                                     │  content_id + reasoning
                                                     ▼
                                       look up original decision by content_id
                                                     │  original record
                                                     ▼
                                       status update  →  "under_review"
                                                     │  updated status + appeal
                                                     ▼
                                       Audit log  (append appeal {reason, logged_at})
                                                     │  confirmation
                                                     ▼
  creator ◀──────────  JSON: {appeal_id, content_id, status: "under_review", logged_at}
```

---
## Transparency Label

**High-confidence AI:**
> **Likely to be AI-generated.** There are strong signals that this was written by AI (confidence: high).

**High-confidence human:**
> **Likely to be created by a human.** There are strong signals that a human wrote this (confidence: high).

**Uncertain:**
> **Uncertain.** Our analysis couldn't confidently tell whether this text was written by a human or by AI.


## Rate Limiting

`POST /submit` is rate-limited with Flask-Limiter, keyed by client IP
(`get_remote_address`), in-memory storage:

```
@limiter.limit("10 per minute;100 per day")
```

**Why these numbers.** Every `/submit` triggers a Groq LLM call (Signal 1), so a
request costs latency and API quota. The limits are set to avoid flooding the system.


**Evidence.** Sending 12 rapid `POST /submit` requests (the per-minute limit is 10):

```
request  1: HTTP 200
request  2: HTTP 200
request  3: HTTP 200
request  4: HTTP 200
request  5: HTTP 200
request  6: HTTP 200
request  7: HTTP 200
request  8: HTTP 200
request  9: HTTP 200
request 10: HTTP 200
request 11: HTTP 429
request 12: HTTP 429
```

The first 10 succeed but the 11th and 12th are rejected with `429`. The 429 body:

```json
{
  "error": "Rate limit exceeded. Please slow down and try again later.",
  "detail": "10 per 1 minute"
}
```

## Audit Log

Every submission is appended as a structured JSON record to `audit_log.json`. 

| Requirement                     | Field                                   |
|---------------------------------|-----------------------------------------|
| Timestamp                       | `timestamp` (UTC, ISO 8601)             |
| Content ID                      | `content_id`                            |
| Attribution result             | `attribution` (`likely_ai` / `likely_human` / `uncertain`) |
| Confidence score                | `confidence`                            |
| Signal 1 (LLM) score            | `signals.llm_score` (+ `llm_rationale`) |
| Signal 2 (stylometric) score    | `signals.stylometric_score`             |
| Fused AI probability            | `ai_probability`                        |
| Whether an appeal has been filed| `status` (`classified` → none; `under_review` → appealed) and `appeals[]` (empty = none) |

An appeal appends `{appeal_id, reason, logged_at}` to the record's `appeals`
list and flips `status` to `under_review`.

**Example — a classified entry with no appeal:**

```json
{
  "content_id": "c_b13723608528",
  "creator_id": "u_human",
  "timestamp": "2026-07-01T01:09:57.773Z",
  "attribution": "likely_human",
  "ai_probability": 0.2316,
  "confidence": 0.9369,
  "signals": {
    "llm_score": 0.2,
    "llm_rationale": "The passage contains specific, personal details and opinions, which is less typical of AI-generated content.",
    "stylometric_score": 0.2631
  },
  "status": "classified",
  "appeals": []
}
```

**Example — the same schema after an appeal is filed** (`status` flipped,
`appeals` populated):

```json
{
  "content_id": "c_f25883975a80",
  "creator_id": "u_ai",
  "timestamp": "2026-07-01T01:09:57.451Z",
  "attribution": "likely_ai",
  "ai_probability": 0.8,
  "confidence": 0.8,
  "signals": {
    "llm_score": 0.9,
    "llm_rationale": "The passage lacks specific lived detail and features uniformly generic content.",
    "stylometric_score": 0.7
  },
  "status": "under_review",
  "appeals": [
    {
      "appeal_id": "a_65a136b566fb",
      "reason": "I wrote this myself; please re-review.",
      "logged_at": "2026-07-01T01:10:06.509Z"
    }
  ]
}
```

## Known Limitations

**Lightly-edited AI text**
Both signals look at surface style, which is easy to change with a few edits.
Changing up a few sentences and deleting obvious phrases that AI would use is enough to fool both signals, so AI text that a person has lightly edited gets labeled `uncertain` or `likely_human`.

## Spec Reflection

The spec helped guide my implementation primarily because, I came up with the architecture diagrams in the spec before building anything so it guided the AI tools more precisely. One way my implementation diverged from the spec was when I chose to add a boilerplate "floor" to Signal 2 that the planning doc doesn't mention. The spec describes Signal 2 as a combination of 3 metrics (sentence length variance, type token ratio, and boilerplate count), but during Milestone 4 testing the sample that was clearly AI sample landed on `uncertain` instead of `likely_ai`. So I added a rule that when text contains 2+ distinct AI cliches, Signal 2 is floored at 0.70 so it agrees with a confident LLM instead of being diluted by the other two metrics.

## AI Usage Section

1. I asked AI to come up with the first signal function, second signal function, and a system prompt. It produced the first signal and second signal functions correctly, but the system prompt was pretty vague. I modified it, and included the format I expected it to produce to make it more precise. 

2. I asked AI to come up with the confidence scoring logic that fuses the two signals, and I gave it the thresholds from my planning doc so the output would match my spec. It generated the scoring correctly, but when tested it with a sample that was clearly AI, it would keep assigning the `uncertain` label instead of `likely_ai`. I chose to add a boilerplate floor to Signal 2 so heavily cliched AI text, scores high enough for the 2 signals to agree.

## Demo Link
https://www.loom.com/share/78c5ba619f474e09919f81713efd6d1e