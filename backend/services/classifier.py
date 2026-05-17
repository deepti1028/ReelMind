"""Reel content classifier — Step 18 of the ingestion pipeline.

Calls Groq Llama 3.3 70B to classify a reel's content signal into one of
the user's categories. Returns a ClassificationResult with the chosen
category name, confidence score, and up to 2 alternative categories.

Public surface:
    classify_reel(transcript, caption, hashtags, categories) -> ClassificationResult
    ClassificationResult, ClassificationError
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field

from groq import APIStatusError, Groq, RateLimitError

from config import get_config

logger = logging.getLogger(__name__)

_MODEL = "llama-3.3-70b-versatile"
_MAX_FIELD_CHARS = 4000


@dataclass
class ClassificationResult:
    category: str           # exact name from the list given to Llama
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
    """Classify reel content into one of the provided categories via Groq Llama.

    Args:
        transcript: Raw transcript text from Step 16, or None.
        caption:    Caption text from Step 15, or None.
        hashtags:   List of hashtag strings from Step 15 (may be empty).
        categories: Exact category names from the DB for this user.

    Returns:
        ClassificationResult with category name, confidence, and alternatives.

    Raises:
        ClassificationError: On API failure, two consecutive JSON parse failures,
                            or schema validation failure. has .is_retryable flag.
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

Return ONLY valid JSON with exactly this schema:
{{
  "category_id": <integer from the list above>,
  "confidence": <float 0.0 to 1.0>,
  "alternative_ids": [<integer>, <integer>]
}}

Rules:
- category_id must be one of the integers listed
- confidence: 0.9-1.0 = very certain | 0.7-0.89 = strong match | 0.4-0.69 = weak/ambiguous | 0.0-0.39 = mostly guesswork
- alternative_ids: 0-2 other plausible category IDs, best first. Must not include category_id.
- Always return a single best guess — never refuse to classify, never invent IDs
- Never return markdown"""

    user_message = f"""Transcript:
{transcript_text}

Caption:
{caption_text}

Hashtags:
{hashtag_text}"""

    cfg = get_config()
    if not cfg.GROQ_API_KEY:
        raise ClassificationError("GROQ_API_KEY not configured", is_retryable=False)
    client = Groq(api_key=cfg.GROQ_API_KEY)

    parsed: dict | None = None
    for attempt in range(2):
        try:
            response = client.chat.completions.create(
                model=_MODEL,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_message},
                ],
                temperature=0,
                response_format={"type": "json_object"},
            )
            raw = response.choices[0].message.content
            parsed = json.loads(raw)
            break
        except RateLimitError as exc:
            raise ClassificationError(str(exc), is_retryable=True) from exc
        except APIStatusError as exc:
            retryable = exc.status_code >= 500
            raise ClassificationError(str(exc), is_retryable=retryable) from exc
        except json.JSONDecodeError:
            if attempt == 1:
                raise ClassificationError(
                    "JSON parse failed twice — persistent model formatting issue",
                    is_retryable=False,
                )
            logger.warning("classifier | JSON parse failed on attempt 1 — retrying")

    # Validate response schema
    try:
        category_id = int(parsed["category_id"])
        confidence = float(parsed["confidence"])
        alternative_ids = [int(a) for a in parsed.get("alternative_ids", [])]
    except (KeyError, TypeError, ValueError) as exc:
        raise ClassificationError(
            f"response missing required fields: {exc}", is_retryable=False
        ) from exc

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
