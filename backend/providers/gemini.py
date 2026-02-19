# backend/providers/gemini.py
import os
import json
import re
from dotenv import load_dotenv
from google import genai
from google.genai import types

load_dotenv()

API_KEY = os.getenv("GEMINI_API_KEY")
if not API_KEY:
    raise RuntimeError("GEMINI_API_KEY not set in backend/.env")

client = genai.Client(api_key=API_KEY)

# Keep your existing "search" tool config for the old function (optional)
grounding_tool = types.Tool(
    google_search=types.GoogleSearch()
)

config_with_search = types.GenerateContentConfig(
    tools=[grounding_tool]
)

# Try to force JSON output (supported on newer google-genai SDKs)
# If your installed SDK doesn't support response_schema/response_mime_type,
# we'll still fall back safely.
def _json_config(schema=None):
    try:
        kwargs = {"response_mime_type": "application/json"}
        if schema is not None:
            kwargs["response_schema"] = schema
        return types.GenerateContentConfig(**kwargs)
    except Exception:
        # Older SDK fallback (no strict JSON mode)
        return types.GenerateContentConfig()


def _clean_code_fence(text: str) -> str:
    text = (text or "").strip()
    if text.startswith("```"):
        parts = text.split("```", 2)
        if len(parts) >= 2:
            text = parts[1]
        text = text.replace("json", "").strip()
    return text


def _extract_first_json_object(text: str) -> str:
    """
    Pull out the first {...} JSON object if Gemini wraps it with extra text.
    """
    text = _clean_code_fence(text)
    # Fast path
    if text.startswith("{") and text.endswith("}"):
        return text

    # Try to find a JSON object substring
    m = re.search(r"\{.*\}", text, re.DOTALL)
    if m:
        return m.group(0).strip()

    # Try to find a JSON array substring
    m = re.search(r"\[.*\]", text, re.DOTALL)
    if m:
        return m.group(0).strip()

    return text.strip()


def get_headlines_for_day(ticker: str, day: str) -> list[str]:
    """
    (Not used by your app now; kept for compatibility.)
    Uses Gemini + GoogleSearch tool to find headlines on the web.
    """
    prompt = f"""
You are a financial news assistant.
Find the news headlines relevant to the stock ticker {ticker} for the date {day}.
Return only valid JSON as an array of objects with keys:
- title
- source
- url
with no extra text.
If there are no results, return [].
""".strip()

    response = client.models.generate_content(
        model="gemini-3-flash-preview",
        contents=prompt,
        config=config_with_search,
    )

    raw = response.text or "[]"
    raw = _extract_first_json_object(raw)

    try:
        return json.loads(raw)
    except Exception:
        return []


def summarize_headlines_from_gdelt(
    ticker: str,
    day: str,
    headlines: list[dict],
    max_items: int = 18,
) -> dict:
    """
    Summarize already-fetched GDELT headlines into JSON:
      {
        "summary_bullets": [...],
        "overall_tone": "positive|neutral|negative|mixed"
      }
    Never throws; always returns a dict.
    """
    items = []
    for h in (headlines or [])[:max_items]:
        title = (h.get("title") or "").strip()
        source = (h.get("source") or h.get("domain") or "").strip()
        if title:
            items.append(f"- {title} ({source})" if source else f"- {title}")

    if not items:
        return {"summary_bullets": [], "overall_tone": "neutral"}

    # Define an optional schema (works only if your SDK supports it)
    schema = None
    try:
        schema = types.Schema(
            type="object",
            properties={
                "summary_bullets": types.Schema(type="array", items=types.Schema(type="string")),
                "overall_tone": types.Schema(type="string"),
            },
            required=["summary_bullets", "overall_tone"],
        )
    except Exception:
        schema = None

    config_json = _json_config(schema=schema)

    prompt = f"""
You are a financial news summarizer.

Ticker: {ticker}
Date: {day}

Headlines:
{chr(10).join(items)}

Task:
1) Write 3–5 short bullet points summarizing the main themes.
2) Give an overall tone: one of ["positive","neutral","negative","mixed"].

Return ONLY valid JSON:
{{
  "summary_bullets": ["..."],
  "overall_tone": "neutral"
}}
""".strip()

    try:
        response = client.models.generate_content(
            model="gemini-3-flash-preview",
            contents=prompt,
            config=config_json,
        )
        raw = response.text or "{}"
        raw = _extract_first_json_object(raw)

        data = json.loads(raw)

        bullets = data.get("summary_bullets") or []
        tone = (data.get("overall_tone") or "neutral").strip().lower()

        bullets = [str(b).strip() for b in bullets if str(b).strip()]
        if tone not in {"positive", "neutral", "negative", "mixed"}:
            tone = "neutral"

        return {"summary_bullets": bullets[:6], "overall_tone": tone}

    except Exception as e:
        # IMPORTANT: return something safe so frontend doesn't break
        return {
            "summary_bullets": [],
            "overall_tone": "neutral",
            "error": f"{type(e).__name__}: {e}",
        }
