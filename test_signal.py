"""Standalone test for Signal 1 (signal_llm) — run directly, inspect output.

    python test_signal.py

Calls the Groq LLM signal on a few hand-picked inputs and prints the result.
This is a manual sanity check, NOT a pytest suite — the point is to eyeball the
scores and rationales before wiring the signal into the /submit endpoint.
"""

from dotenv import load_dotenv

load_dotenv()  # must run before importing signals (Groq client reads the key)

from signals import signal_llm  # noqa: E402

SAMPLES = [
    (
        "obviously-AI / generic essay",
        "In today's fast-paced world, it is important to note that technology "
        "plays a crucial role in our daily lives. Moreover, by leveraging "
        "innovative solutions, we can navigate the complexities of the modern "
        "era and unlock a tapestry of new opportunities for everyone involved.",
    ),
    (
        "human / specific & messy",
        "my grandma kept her bus tickets in a cookie tin. the orange one. she "
        "never threw anything out and honestly half of it was junk but i found "
        "a photo of my mom at like six, scowling, holding a fish bigger than her arm.",
    ),
    (
        "short / ambiguous",
        "The cat sat on the mat. It was warm. Nobody knew why.",
    ),
]


def main():
    for label, text in SAMPLES:
        result = signal_llm(text)
        print(f"\n=== {label} ===")
        print(f"  ai_probability: {result['ai_probability']}")
        print(f"  rationale:      {result['rationale']}")


if __name__ == "__main__":
    main()
