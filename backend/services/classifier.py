"""Reel content classifier — Step 18 of the ingestion pipeline.

Calls Google Gemini to classify a reel's content signal into one of
the user's categories. Returns a ClassificationResult with the chosen
category name, confidence score, and up to 2 alternative categories.

Public surface:
    classify_reel(transcript, caption, hashtags, categories) -> ClassificationResult
    ClassificationResult, ClassificationError
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from google import genai
from google.genai.types import GenerateContentConfig, Tool
from pydantic import BaseModel

from config import get_config

logger = logging.getLogger(__name__)

_MODEL = "gemini-3.5-flash"
_MAX_FIELD_CHARS = 4000


class ClassificationSchema(BaseModel):
    """Structured output schema for Gemini classification response."""
    category_id: int
    confidence: float
    alternative_ids: list[int] = field(default_factory=list)


@dataclass
class ClassificationResult:
    category: str           # exact name from the list given to Gemini
    confidence: float       # 0.0–1.0
    alternatives: list[str] = field(default_factory=list)  # up to 2, best first


class ClassificationError(Exception):
    def __init__(self, message: str, is_retryable: bool = True) -> None:
        super().__init__(message)
        self.is_retryable = is_retryable


def classify_reel(
    transcript: str | None,
    caption: str | None,
    hashtags: list[str],
    categories: list[str],
) -> ClassificationResult:
    """Classify reel content into one of the provided categories via Gemini.

    Args:
        transcript: Raw transcript text from Step 16, or None.
        caption:    Caption text from Step 15, or None.
        hashtags:   List of hashtag strings from Step 15 (may be empty).
        categories: Exact category names from the DB for this user.

    Returns:
        ClassificationResult with category name, confidence, and alternatives.

    Raises:
        ClassificationError: On API failure or schema validation failure.
                            has .is_retryable flag.
    """
    # Map sequential IDs to category names to avoid spelling/casing issues.
    id_to_name: dict[int, str] = {i + 1: name for i, name in enumerate(categories)}
    category_list_str = "\n".join(f"{cid}: {name}" for cid, name in id_to_name.items())

    # Cap caption/transcript at MAX_FIELD_CHARS each to bound prompt size and
    # limit prompt-injection surface from user-supplied content.
    transcript_text = (transcript or "(none)")[:_MAX_FIELD_CHARS]
    caption_text = (caption or "(none)")[:_MAX_FIELD_CHARS]
    hashtag_text = " ".join(f"#{t}" for t in hashtags) if hashtags else "(none)"

    system_prompt = f"""You are a content classifier for a personal content library app.
Classify the reel into EXACTLY ONE category from the provided list.

Use the overall semantic meaning of the content.
Do NOT classify based only on hashtags if the transcript/caption suggests otherwise.

Categories:
{category_list_str}

Return JSON with exactly this schema:
{{
  "category_id": <integer from the list above>,
  "confidence": <float 0.0 to 1.0>,
  "alternative_ids": [<integer>, <integer>]
}}

Rules:
- category_id must be one of the integers listed
- confidence: 0.9-1.0 = very certain | 0.7-0.89 = strong match | 0.4-0.69 = weak/ambiguous | 0.0-0.39 = mostly guesswork
- alternative_ids: 0-2 other plausible category IDs, best first. Must not include category_id.
- Always return a single best guess — never refuse to classify, never invent IDs"""

    user_message = f"""Transcript:
{transcript_text}

Caption:
{caption_text}

Hashtags:
{hashtag_text}"""

    cfg = get_config()
    if not cfg.GEMINI_API_KEY:
        raise ClassificationError("GEMINI_API_KEY not configured", is_retryable=False)

    try:
        client = genai.Client(api_key=cfg.GEMINI_API_KEY)
        response = client.models.generate_content(
            model=_MODEL,
            contents=[
                genai.types.Content(role="user", parts=[genai.types.Part(text=user_message)]),
            ],
            config=GenerateContentConfig(
                system_instruction=system_prompt,
                temperature=0,
                response_mime_type="application/json",
                response_schema=ClassificationSchema,
            ),
        )

        # Extract and validate the response
        if not response.text:
            raise ClassificationError("Empty response from Gemini", is_retryable=True)

        # Parse the JSON response
        import json
        parsed = json.loads(response.text)
        category_id = int(parsed["category_id"])
        confidence = float(parsed["confidence"])
        alternative_ids = [int(a) for a in parsed.get("alternative_ids", [])]

    except Exception as exc:
        # Check if it's a known error pattern
        exc_str = str(exc)
        if "rate" in exc_str.lower() or "quota" in exc_str.lower():
            raise ClassificationError(str(exc), is_retryable=True) from exc
        if "401" in exc_str or "authentication" in exc_str.lower():
            raise ClassificationError("Authentication failed", is_retryable=False) from exc
        # Unknown errors are retryable by default (transient network issues)
        raise ClassificationError(str(exc), is_retryable=True) from exc

    # Validate response schema
    try:
        if category_id not in id_to_name:
            raise ClassificationError(
                f"category_id {category_id} not in valid range 1–{len(id_to_name)}",
                is_retryable=False,
            )
        if not (0.0 <= confidence <= 1.0):
            raise ClassificationError(
                f"confidence {confidence} out of [0.0, 1.0]", is_retryable=False
            )
        if any(a not in id_to_name for a in alternative_ids):
            raise ClassificationError(
                "alternative_ids contains invalid category ID", is_retryable=False
            )
        if category_id in alternative_ids:
            raise ClassificationError(
                "category_id must not appear in alternative_ids", is_retryable=False
            )
    except (KeyError, TypeError, ValueError) as exc:
        raise ClassificationError(
            f"response missing required fields: {exc}", is_retryable=False
        ) from exc

    logger.info(
        "classifier | category=%s | confidence=%.2f | alternatives=%s",
        id_to_name[category_id],
        confidence,
        [id_to_name[a] for a in alternative_ids],
    )

    return ClassificationResult(
        category=id_to_name[category_id],
        confidence=confidence,
        alternatives=[id_to_name[a] for a in alternative_ids],
    )
