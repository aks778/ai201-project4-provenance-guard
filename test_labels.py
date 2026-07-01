"""Reachability test for the three transparency-label variants.

Deterministic — feeds synthetic signal scores straight into score_content +
build_transparency_label, so no Groq API call is needed. Proves that:
  1. all three variants (likely_ai / likely_human / uncertain) are reachable, and
  2. the label TEXT changes with the score (it is not constant).

    python test_labels.py
"""

import sys

# The label text contains emoji; force UTF-8 stdout so it prints on a Windows
# console (cp1252) without a UnicodeEncodeError.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from scoring import score_content, build_transparency_label  # noqa: E402

# A body of >= 40 words so the short-text confidence cap doesn't interfere with
# the high-confidence cases. Content is irrelevant here — we inject the scores.
LONG = " ".join(["word"] * 45)

# (name, p_llm, p_stylometric, text, expected_label)
CASES = [
    # both signals high + agree  -> high confidence AI
    ("high-confidence AI",    0.90, 0.90, LONG, "likely_ai"),
    # both signals low + agree   -> high confidence human
    ("high-confidence human",  0.10, 0.10, LONG, "likely_human"),
    # signals disagree strongly  -> low confidence -> uncertain
    ("uncertain (disagreement)", 0.90, 0.20, LONG, "uncertain"),
]


def main():
    seen_text = {}
    all_ok = True
    for name, p_llm, p_sty, text, expected in CASES:
        result = score_content(p_llm, p_sty, text)
        label = result["label"]
        transparency = build_transparency_label(label)
        ok = label == expected
        all_ok = all_ok and ok
        seen_text[label] = transparency["text"]
        print(f"\n=== {name} ===")
        print(f"  fused={result['ai_probability']} confidence={result['confidence']}")
        print(f"  label={label}  (expected {expected})  {'OK' if ok else 'MISMATCH'}")
        print(f"  variant={transparency['variant']}")
        print(f"  text={transparency['text']}")

    # All three variants reachable?
    reachable = set(seen_text)
    expected_variants = {"likely_ai", "likely_human", "uncertain"}
    print("\n--- summary ---")
    print(f"  variants reached: {sorted(reachable)}")
    assert reachable == expected_variants, f"missing variants: {expected_variants - reachable}"
    # Text actually differs across variants (not constant).
    assert len(set(seen_text.values())) == 3, "label text is not distinct per variant"
    assert all_ok, "at least one label did not match its expected value"
    print("  PASS: all three variants reachable and their text is distinct.")


if __name__ == "__main__":
    main()
