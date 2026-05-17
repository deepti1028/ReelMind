"""Classification signal builder — Step 17 of the ingestion pipeline.

Assembles a normalized, prompt-ready text signal from all available reel
data (transcript, caption, hashtags) for the Llama classifier in Step 18.

Public surface:
    build_classification_signal(transcript, caption, hashtags) -> ClassificationSignal
    ClassificationSignal, NoSignalError
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class ClassificationSignal:
    text: str            # assembled, prompt-ready text for the Llama classifier
    has_transcript: bool
    has_caption: bool
    has_hashtags: bool
    source_summary: str  # e.g. "transcript+caption+hashtags" — for log lines


class NoSignalError(Exception):
    """Raised when all signals are empty after normalization.

    Not retryable — no amount of retrying will produce new data without
    a fresh download.
    """


def build_classification_signal(
    transcript: str | None,
    caption: str | None,
    hashtags: list[str],
) -> ClassificationSignal:
    """Assemble a normalized classification signal from available reel data.

    Normalizes each field (strips whitespace, filters empty hashtags),
    checks that at least one field has content, then builds a labeled
    prompt-ready text string for Step 18.

    Args:
        transcript: Raw transcript text from Step 16, or None.
        caption:    Caption text from Step 15, or None.
        hashtags:   List of hashtag strings from Step 15 (may be empty).

    Returns:
        ClassificationSignal with assembled text and source metadata.

    Raises:
        NoSignalError: All three signals are empty after normalization.
    """
    t = (transcript or "").strip()
    c = (caption or "").strip()
    h = [tag.strip() for tag in (hashtags or []) if tag.strip()]

    if not t and not c and not h:
        raise NoSignalError(
            "no usable signal: transcript, caption, and hashtags are all "
            "empty after normalization"
        )

    sections: list[str] = []
    sources: list[str] = []

    if t:
        sections.append(f"[Transcript]\n{t}")
        sources.append("transcript")

    if c:
        sections.append(f"[Caption]\n{c}")
        sources.append("caption")

    if h:
        hashtag_line = " ".join(f"#{tag}" for tag in h)
        sections.append(f"[Hashtags]\n{hashtag_line}")
        sources.append("hashtags")

    return ClassificationSignal(
        text="\n\n".join(sections),
        has_transcript=bool(t),
        has_caption=bool(c),
        has_hashtags=bool(h),
        source_summary="+".join(sources),
    )
