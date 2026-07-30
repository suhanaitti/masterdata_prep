"""Shared helper for parsing an LLM's JSON response - strips a markdown code fence if
the model wrapped its answer in one, and raises rather than silently returning {}/[] so
a malformed response is never confused with a genuine empty/negative answer."""
import json
import re


def parse_ai_json(raw: str):
    text = raw.strip()
    if text.startswith("```"):
        text = re.sub(r"^```[a-zA-Z]*\n?", "", text)
        text = re.sub(r"\n?```\s*$", "", text)
    try:
        return json.loads(text)
    except json.JSONDecodeError as e:
        raise ValueError(f"AI response was not valid JSON: {e}\nRaw: {text[:500]}") from e
