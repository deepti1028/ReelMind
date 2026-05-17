"""Tests for services.classifier — Step 18 Groq Llama classification."""
from unittest.mock import MagicMock, patch
import json
import pytest

CATEGORIES = ["Skincare", "Haircare", "Fitness", "Nutrition"]


def _make_groq_response(category_id: int, confidence: float, alternative_ids: list[int]):
    """Build a mock Groq chat completion response."""
    content = json.dumps({
        "category_id": category_id,
        "confidence": confidence,
        "alternative_ids": alternative_ids,
    })
    msg = MagicMock()
    msg.content = content
    choice = MagicMock()
    choice.message = msg
    resp = MagicMock()
    resp.choices = [choice]
    return resp


def _make_bad_json_response():
    msg = MagicMock()
    msg.content = "not valid json {{{"
    choice = MagicMock()
    choice.message = msg
    resp = MagicMock()
    resp.choices = [choice]
    return resp


# ---------------------------------------------------------------------------
# Happy paths
# ---------------------------------------------------------------------------

@patch("services.classifier.Groq")
def test_happy_path_high_confidence(mock_groq_cls):
    mock_groq_cls.return_value.chat.completions.create.return_value = (
        _make_groq_response(3, 0.92, [4])
    )
    from services.classifier import classify_reel
    result = classify_reel("Great workout!", "Gym time!", ["fitness"], CATEGORIES)
    assert result.category == "Fitness"
    assert result.confidence == 0.92
    assert result.alternatives == ["Nutrition"]


@patch("services.classifier.Groq")
def test_category_id_mapped_to_name(mock_groq_cls):
    mock_groq_cls.return_value.chat.completions.create.return_value = (
        _make_groq_response(1, 0.85, [])
    )
    from services.classifier import classify_reel
    result = classify_reel(None, "Moisturiser review", [], CATEGORIES)
    assert result.category == "Skincare"
    assert result.alternatives == []


@patch("services.classifier.Groq")
def test_alternatives_mapped_to_names(mock_groq_cls):
    mock_groq_cls.return_value.chat.completions.create.return_value = (
        _make_groq_response(1, 0.75, [3, 4])
    )
    from services.classifier import classify_reel
    result = classify_reel("skin routine", None, [], CATEGORIES)
    assert result.alternatives == ["Fitness", "Nutrition"]


# ---------------------------------------------------------------------------
# JSON parse retry
# ---------------------------------------------------------------------------

@patch("services.classifier.Groq")
def test_json_parse_failure_retried_once(mock_groq_cls):
    good_resp = _make_groq_response(1, 0.9, [])
    mock_groq_cls.return_value.chat.completions.create.side_effect = [
        _make_bad_json_response(),
        good_resp,
    ]
    from services.classifier import classify_reel
    result = classify_reel(None, "Skincare routine", [], CATEGORIES)
    assert result.category == "Skincare"
    assert mock_groq_cls.return_value.chat.completions.create.call_count == 2


@patch("services.classifier.Groq")
def test_json_parse_failure_twice_raises_non_retryable(mock_groq_cls):
    mock_groq_cls.return_value.chat.completions.create.return_value = (
        _make_bad_json_response()
    )
    from services.classifier import classify_reel, ClassificationError
    with pytest.raises(ClassificationError) as exc_info:
        classify_reel(None, "caption", [], CATEGORIES)
    assert exc_info.value.is_retryable is False


# ---------------------------------------------------------------------------
# Validation failures
# ---------------------------------------------------------------------------

@patch("services.classifier.Groq")
def test_invalid_category_id_raises_non_retryable(mock_groq_cls):
    mock_groq_cls.return_value.chat.completions.create.return_value = (
        _make_groq_response(99, 0.9, [])
    )
    from services.classifier import classify_reel, ClassificationError
    with pytest.raises(ClassificationError) as exc_info:
        classify_reel(None, "caption", [], CATEGORIES)
    assert exc_info.value.is_retryable is False


@patch("services.classifier.Groq")
def test_confidence_out_of_range_raises_non_retryable(mock_groq_cls):
    mock_groq_cls.return_value.chat.completions.create.return_value = (
        _make_groq_response(1, 1.5, [])
    )
    from services.classifier import classify_reel, ClassificationError
    with pytest.raises(ClassificationError) as exc_info:
        classify_reel(None, "caption", [], CATEGORIES)
    assert exc_info.value.is_retryable is False


@patch("services.classifier.Groq")
def test_category_in_alternatives_raises_non_retryable(mock_groq_cls):
    mock_groq_cls.return_value.chat.completions.create.return_value = (
        _make_groq_response(1, 0.9, [1])  # category_id == alternative_id
    )
    from services.classifier import classify_reel, ClassificationError
    with pytest.raises(ClassificationError) as exc_info:
        classify_reel(None, "caption", [], CATEGORIES)
    assert exc_info.value.is_retryable is False


# ---------------------------------------------------------------------------
# Groq API errors
# ---------------------------------------------------------------------------

@patch("services.classifier.Groq")
def test_groq_429_is_retryable(mock_groq_cls):
    from groq import RateLimitError
    mock_response = MagicMock()
    mock_response.status_code = 429
    mock_groq_cls.return_value.chat.completions.create.side_effect = RateLimitError(
        message="rate limit exceeded",
        response=mock_response,
        body={},
    )
    from services.classifier import classify_reel, ClassificationError
    with pytest.raises(ClassificationError) as exc_info:
        classify_reel(None, "caption", [], CATEGORIES)
    assert exc_info.value.is_retryable is True


@patch("services.classifier.Groq")
def test_groq_400_not_retryable(mock_groq_cls):
    from groq import APIStatusError
    mock_response = MagicMock()
    mock_response.status_code = 400
    mock_groq_cls.return_value.chat.completions.create.side_effect = APIStatusError(
        message="bad request",
        response=mock_response,
        body={},
    )
    from services.classifier import classify_reel, ClassificationError
    with pytest.raises(ClassificationError) as exc_info:
        classify_reel(None, "caption", [], CATEGORIES)
    assert exc_info.value.is_retryable is False


@patch("services.classifier.Groq")
def test_temperature_is_zero(mock_groq_cls):
    mock_groq_cls.return_value.chat.completions.create.return_value = (
        _make_groq_response(1, 0.9, [])
    )
    from services.classifier import classify_reel
    classify_reel(None, "caption", [], CATEGORIES)
    kwargs = mock_groq_cls.return_value.chat.completions.create.call_args.kwargs
    assert kwargs["temperature"] == 0
