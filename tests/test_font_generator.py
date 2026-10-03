import pytest
from utils.font_generator import transform_text, AVAILABLE_STYLES

def test_font_generator_styles():
    text = "The Raivora 123"
    for style_key, label, _ in AVAILABLE_STYLES:
        converted = transform_text(text, style_key)
        assert converted, f"Style {style_key} returned empty string"
        assert len(converted) >= len(text), f"Style {style_key} shortened text unexpectedly"

def test_small_caps():
    assert transform_text("welcome", "small_caps") == "ᴡᴇʟᴄᴏᴍᴇ"

def test_gothic():
    res = transform_text("RAI", "bold_gothic")
    assert res == "𝕽𝕬𝕴"

def test_bubbles():
    assert "ⓐ" in transform_text("abc", "bubbles")

def test_double_struck():
    assert "𝟙" in transform_text("123", "double_struck")
