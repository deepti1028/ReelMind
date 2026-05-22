"""Tests for services.classifier — Step 18 Gemini classification."""
from unittest.mock import MagicMock, patch
import json
import pytest

CATEGORIES = ["Skincare", "Haircare", "Fitness", "Nutrition"]


def _make_gemini_response(category_id: int, confidence: float, alternative_ids: list[int]):
    """Build a mock Gemini GenerateContentResponse."""
    content = json.dumps({
        "category_id": category_id,
        "confidence": confidence,
        "alternative_ids": alternative_ids,
    })
    resp = MagicMock()
    resp.text = content
    return resp


def _make_bad_json_response():
    resp = MagicMock()
    resp.text = "not valid json {{{"
    return resp


# ---------------------------------------------------------------------------
# Happy paths
# ---------------------------------------------------------------------------

@patch("services.classifier.genai.Client")
def test_happy_path_high_confidence(mock_client_cls):
    mock_client = MagicMock()
    mock_client_cls.return_value = mock_client
    mock_client.models.generate_content.return_value = (
        _make_gemini_response(3, 0.92, [4])
    )
    from services.classifier import classify_reel
    result = classify_reel("Great workout!", "Gym time!", ["fitness"], CATEGORIES)
    assert result.category == "Fitness"
    assert result.confidence == 0.92
    assert result.alternatives == ["Nutrition"]


@patch("services.classifier.genai.Client")
def test_category_id_mapped_to_name(mock_client_cls):
    mock_client = MagicMock()
    mock_client_cls.return_value = mock_client
    mock_client.models.generate_content.return_value = (
        _make_gemini_response(1, 0.85, [])
    )
    from services.classifier import classify_reel
    result = classify_reel(None, "Moisturiser review", [], CATEGORIES)
    assert result.category == "Skincare"
    assert result.alternatives == []


@patch("services.classifier.genai.Client")
def test_alternatives_mapped_to_names(mock_client_cls):
    mock_client = MagicMock()
    mock_client_cls.return_value = mock_client
    mock_client.models.generate_content.return_value = (
        _make_gemini_response(1, 0.75, [3, 4])
    )
    from services.classifier import classify_reel
    result = classify_reel("skin routine", None, [], CATEGORIES)
    assert result.alternatives == ["Fitness", "Nutrition"]


# ---------------------------------------------------------------------------
# JSON parse errors (edge case with Gemini schema validation)
# ---------------------------------------------------------------------------

@patch("services.classifier.genai.Client")
def test_bad_json_response_raises_error(mock_client_cls):
    mock_client = MagicMock()
    mock_client_cls.return_value = mock_client
    mock_client.models.generate_content.return_value = (
        _make_bad_json_response()
    )
    from services.classifier import classify_reel, ClassificationError
    with pytest.raises(ClassificationError) as exc_info:
        classify_reel(None, "caption", [], CATEGORIES)
    assert exc_info.value.is_retryable is True


# ---------------------------------------------------------------------------
# Validation failures
# ---------------------------------------------------------------------------

@patch("services.classifier.genai.Client")
def test_invalid_category_id_raises_non_retryable(mock_client_cls):
    mock_client = MagicMock()
    mock_client_cls.return_value = mock_client
    mock_client.models.generate_content.return_value = (
        _make_gemini_response(99, 0.9, [])
    )
    from services.classifier import classify_reel, ClassificationError
    with pytest.raises(ClassificationError) as exc_info:
        classify_reel(None, "caption", [], CATEGORIES)
    assert exc_info.value.is_retryable is False


@patch("services.classifier.genai.Client")
def test_confidence_out_of_range_raises_non_retryable(mock_client_cls):
    mock_client = MagicMock()
    mock_client_cls.return_value = mock_client
    mock_client.models.generate_content.return_value = (
        _make_gemini_response(1, 1.5, [])
    )
    from services.classifier import classify_reel, ClassificationError
    with pytest.raises(ClassificationError) as exc_info:
        classify_reel(None, "caption", [], CATEGORIES)
    assert exc_info.value.is_retryable is False


@patch("services.classifier.genai.Client")
def test_category_in_alternatives_raises_non_retryable(mock_client_cls):
    mock_client = MagicMock()
    mock_client_cls.return_value = mock_client
    mock_client.models.generate_content.return_value = (
        _make_gemini_response(1, 0.9, [1])  # category_id == alternative_id
    )
    from services.classifier import classify_reel, ClassificationError
    with pytest.raises(ClassificationError) as exc_info:
        classify_reel(None, "caption", [], CATEGORIES)
    assert exc_info.value.is_retryable is False


# ---------------------------------------------------------------------------
# Gemini API errors
# ---------------------------------------------------------------------------

@patch("services.classifier.genai.Client")
def test_rate_limit_error_is_retryable(mock_client_cls):
    mock_client = MagicMock()
    mock_client_cls.return_value = mock_client
    mock_client.models.generate_content.side_effect = Exception("rate limit exceeded")
    from services.classifier import classify_reel, ClassificationError
    with pytest.raises(ClassificationError) as exc_info:
        classify_reel(None, "caption", [], CATEGORIES)
    assert exc_info.value.is_retryable is True


@patch("services.classifier.genai.Client")
def test_auth_error_not_retryable(mock_client_cls):
    mock_client = MagicMock()
    mock_client_cls.return_value = mock_client
    mock_client.models.generate_content.side_effect = Exception("401 authentication failed")
    from services.classifier import classify_reel, ClassificationError
    with pytest.raises(ClassificationError) as exc_info:
        classify_reel(None, "caption", [], CATEGORIES)
    assert exc_info.value.is_retryable is False


@patch("services.classifier.genai.Client")
def test_gemini_call_uses_correct_model_and_params(mock_client_cls):
    """Locks in model and temperature on the Gemini call."""
    mock_client = MagicMock()
    mock_client_cls.return_value = mock_client
    mock_client.models.generate_content.return_value = (
        _make_gemini_response(1, 0.9, [])
    )
    from services.classifier import classify_reel
    classify_reel(None, "caption", [], CATEGORIES)

    # Check that generate_content was called with correct model
    call_kwargs = mock_client.models.generate_content.call_args.kwargs
    assert call_kwargs["model"] == "gemini-2.5-flash"

    # system_instruction must be inside config, NOT a top-level kwarg —
    # google-genai SDK v1.x rejects it at the top level with TypeError.
    assert "system_instruction" not in call_kwargs, (
        "system_instruction must be in GenerateContentConfig, not a top-level kwarg"
    )
    config = call_kwargs["config"]
    assert config.temperature == 0
    assert config.system_instruction is not None
