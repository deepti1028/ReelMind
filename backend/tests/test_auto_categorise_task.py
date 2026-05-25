"""Tests for auto_categorise behaviour in schema and Celery task."""
from schemas.reel import ReelCreate


def test_reel_create_auto_categorise_defaults_true():
    r = ReelCreate(url="https://www.instagram.com/reel/ABC123/")
    assert r.auto_categorise is True


def test_reel_create_auto_categorise_can_be_false():
    r = ReelCreate(url="https://www.instagram.com/reel/ABC123/", auto_categorise=False)
    assert r.auto_categorise is False
