# Provenance Guard — Planning

## Detection Signals

2 signals: one statistical (form), one model-based (meaning).

**Signal 1 — LLM -Groq (llama-3.3-70b-versatile).**
Sends the text to a Groq LLM with a structured prompt asking how AI-generated it reads,
catching semantic cues stats miss (generic content, even hedging, no specific detail).
**Output:** `ai_probability` between 0 and 1, plus a one line providing rationale.

**Signal 2 — Stylometric heuristics (local, deterministic).**
Measures sentence-length variance, unique words / total
words, and the count of AI-boilerplate phrases ("delve," "it's important to note,"
"moreover,"etc.). AI text tends to be evenly paced with safe vocabulary;
human text is more diverse.
**Output:** `ai_probability` between 0 and 1.



**Combining them into one confidence score:**
- `fused = (p_llm + p_stylometric) / 2` — the single AI probability.
- `agreement = 1 − |p_llm − p_stylometric|` — how much the two signals agree.
- `confidence = agreement` (capped at 0.5 if the text is shorter than ~40 words, since the
  stylometric signal is unreliable on short text).

When both signals agree, confidence is high.

---

## Uncertainty Representation

- **What a 0.6 confidence means:** the two signals only partly agree. The system is *not*
  sure. The result is labeled **uncertain**, never given a hard AI/human verdict.
- **Mapping raw outputs to a calibrated score:** each signal returns 0–1; we average them
  for the AI probability and use signal *agreement* for confidence. Short text
  caps confidence at 0.5. We tune the thresholds against a small hand-labeled sample (clear
  AI, clear human, hybrid) and confirm obvious cases land in the right band.
- **Thresholds (use both `fused` AI probability AND `confidence`):**

| Result        | Condition                                   |
|---------------|---------------------------------------------|
| likely AI     | `fused ≥ 0.70` **and** `confidence ≥ 0.70`  |
| likely human  | `fused ≤ 0.30` **and** `confidence ≥ 0.70`  |
| uncertain     | everything else                             |

The wide middle is deliberate: borderline or disputed cases fall to "uncertain" rather
than a confident wrong answer.

---

## Transparency Label

**High-confidence AI:**
>  **Likely to be AI-generated.** There are strong signals that this was written by AI (confidence: high).

**High-confidence human:**
> **Likely to be created by a human.** There are strong signals that a human wrote this (confidence: high).

**Uncertain:**
>  **Uncertain.** Our analysis couldn't confidently tell whether this text was written by a human or by AI.

---

## Appeals Workflow

- **Who can appeal:** the creator
- **What they provide:** the `content_id` and their written reasoning
  (`creator_reasoning`).
- **What the system does on receipt:**
  1. Looks up the original decision by `content_id`
  2. Appends the appeal `{reason, logged_at}` to that item's audit-log record.
  3. Changes the content's status to **`under_review`**.
  4. Returns `{appeal_id, content_id, status: "under_review", logged_at}`.

  No automatic re-classification — a human decides.
- **What a reviewer sees in the appeal queue:** for each `under_review` item — the original
  text, both signal scores + the LLM rationale, the fused probability and confidence, the
  label that was shown, and the creator's reasoning. Enough to judge the appeal without
  re-running anything.

---

## Anticipated Edge Cases (handled poorly)

1. **Formal, evenly-paced human writing** (academic, legal).
   Low burstiness + safe vocabulary makes Signal 1 lean AI, and Signal 2 is also biased
   toward flagging polished prose — so both can agree on a confident *false positive*. 

2. **A short poem with heavy repetition and simple vocabulary.** Simple vocabulary and
   repeated lines look "AI-like" to the stylometric signal. We cap confidence at 0.5 for short text so these land in "uncertain"
   instead of a wrong verdict.

3. **Lightly edited AI text.** A few human edits to sentence length and word choice defeat
   Signal 1; Signal 2 can be fooled too. The system will likely call this "uncertain" or
   "human" — a false negative we accept.

---

## Architecture

**Submission flow:** a creator sends raw text to `POST /submit`; the text is scored
independently by Signal 1 (Groq LLM) and Signal 2 (stylometric heuristics), the two
0–1 scores are fused into one AI probability plus a confidence value, that result is mapped
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

## AI Tool Plan

**M3 (submission endpoint + first signal):** I will provide Claude with the detection signals section and the diagram in the architecture section and ask it to generate a Flask app skeleton and a first signal function. I'll verify the output by testing with a couple of inputs before wiring into the endpoint. 

**M4 (second signal + confidence scoring):** I will provide Claude with the detection signals section, the diagram in the architecture section, and the uncertainty representation section ask it to create the second signal function and the confidence scoring logic based on the rules I included in that section. I'll verify the output by testing if scores distinctly vary when labeled as written by AI and written by a human.

**M5 (production layer):** I will provide Claude with the labels, appeals workflow, and the diagram in the architecture section, and ask it to come up with the appeal endpoint and create the logic for determining labels. I'll verify the output by testing that an appeal causes the status to update accordingly and if all labels are reachable.



