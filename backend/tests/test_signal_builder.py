"""Tests for services.signal_builder — Step 17 classification signal assembly."""
import pytest


# ---------------------------------------------------------------------------
# No-signal gate (4 cases)
# ---------------------------------------------------------------------------

def test_raises_when_all_none():
    from services.signal_builder import build_classification_signal, NoSignalError
    with pytest.raises(NoSignalError):
        build_classification_signal(transcript=None, caption=None, hashtags=[])


def test_raises_when_all_empty_strings():
    from services.signal_builder import build_classification_signal, NoSignalError
    with pytest.raises(NoSignalError):
        build_classification_signal(transcript="", caption="", hashtags=[])


def test_raises_when_all_whitespace():
    from services.signal_builder import build_classification_signal, NoSignalError
    with pytest.raises(NoSignalError):
        build_classification_signal(transcript="   ", caption="\t\n", hashtags=["", "  "])


def test_raises_when_hashtags_all_empty_strings():
    from services.signal_builder import build_classification_signal, NoSignalError
    with pytest.raises(NoSignalError):
        build_classification_signal(transcript=None, caption=None, hashtags=["", "  ", "\t"])


# ---------------------------------------------------------------------------
# Happy paths — single signal
# ---------------------------------------------------------------------------

def test_transcript_only():
    from services.signal_builder import build_classification_signal
    result = build_classification_signal(
        transcript="A 5-minute HIIT workout.",
        caption=None,
        hashtags=[],
    )
    assert result.has_transcript is True
    assert result.has_caption is False
    assert result.has_hashtags is False
    assert "[Transcript]\nA 5-minute HIIT workout." in result.text
    assert "[Caption]" not in result.text
    assert "[Hashtags]" not in result.text
    assert result.source_summary == "transcript"


def test_caption_only():
    from services.signal_builder import build_classification_signal
    result = build_classification_signal(
        transcript=None,
        caption="Full body burn in 15 min!",
        hashtags=[],
    )
    assert result.has_transcript is False
    assert result.has_caption is True
    assert result.has_hashtags is False
    assert "[Caption]\nFull body burn in 15 min!" in result.text
    assert "[Transcript]" not in result.text
    assert result.source_summary == "caption"


def test_hashtags_only():
    from services.signal_builder import build_classification_signal
    result = build_classification_signal(
        transcript=None,
        caption=None,
        hashtags=["fitness", "gym", "workout"],
    )
    assert result.has_transcript is False
    assert result.has_caption is False
    assert result.has_hashtags is True
    assert "[Hashtags]\n#fitness #gym #workout" in result.text
    assert "[Transcript]" not in result.text
    assert result.source_summary == "hashtags"


# ---------------------------------------------------------------------------
# Happy paths — combined signals
# ---------------------------------------------------------------------------

def test_full_signal():
    from services.signal_builder import build_classification_signal
    result = build_classification_signal(
        transcript="The creator shows a workout.",
        caption="Full body burn!",
        hashtags=["fitness", "gym"],
    )
    assert result.has_transcript is True
    assert result.has_caption is True
    assert result.has_hashtags is True
    assert "[Transcript]" in result.text
    assert "[Caption]" in result.text
    assert "[Hashtags]" in result.text
    assert result.source_summary == "transcript+caption+hashtags"


def test_transcript_and_hashtags_no_caption():
    from services.signal_builder import build_classification_signal
    result = build_classification_signal(
        transcript="A cooking tutorial.",
        caption=None,
        hashtags=["food", "recipe"],
    )
    assert result.has_transcript is True
    assert result.has_caption is False
    assert result.has_hashtags is True
    assert "[Transcript]" in result.text
    assert "[Caption]" not in result.text
    assert "[Hashtags]" in result.text
    assert result.source_summary == "transcript+hashtags"


def test_caption_and_hashtags_no_transcript():
    from services.signal_builder import build_classification_signal
    result = build_classification_signal(
        transcript=None,
        caption="Check out this recipe!",
        hashtags=["food", "cooking"],
    )
    assert result.has_transcript is False
    assert result.has_caption is True
    assert result.has_hashtags is True
    assert "[Transcript]" not in result.text
    assert "[Caption]" in result.text
    assert "[Hashtags]" in result.text
    assert result.source_summary == "caption+hashtags"


# ---------------------------------------------------------------------------
# Normalization edge cases
# ---------------------------------------------------------------------------

def test_whitespace_transcript_treated_as_absent():
    from services.signal_builder import build_classification_signal
    result = build_classification_signal(
        transcript="   ",
        caption="Short caption.",
        hashtags=[],
    )
    assert result.has_transcript is False
    assert result.has_caption is True
    assert "[Transcript]" not in result.text
    assert result.source_summary == "caption"


def test_empty_hashtag_strings_filtered():
    from services.signal_builder import build_classification_signal
    result = build_classification_signal(
        transcript=None,
        caption=None,
        hashtags=["", "fitness", "  ", "gym"],
    )
    assert result.has_hashtags is True
    assert "#fitness" in result.text
    assert "#gym" in result.text
    assert result.text.count("#") == 2


def test_source_summary_reflects_actual_sources():
    from services.signal_builder import build_classification_signal
    result = build_classification_signal(
        transcript=None,
        caption="A caption.",
        hashtags=["tag1"],
    )
    assert result.source_summary == "caption+hashtags"
