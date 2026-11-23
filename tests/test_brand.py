"""The brand comes from config/brand.toml and its colours pass WCAG 2.2 AA contrast (story D-4)."""

from pathlib import Path

import pytest

from app.brand import DEFAULT_PATH, BrandError, Colours, contrast, contrast_problems, load_brand, tokens_css


def write(tmp_path: Path, text: str) -> Path:
    path = tmp_path / "brand.toml"
    path.write_text(text, encoding="utf-8")
    return path


def test_the_brand_file_loads():
    brand = load_brand()
    assert brand.product.name
    assert brand.company.name


def test_the_brand_colours_have_enough_contrast():
    # If this fails, a colour in config/brand.toml is too light or too dark; the message names the pair.
    assert contrast_problems(load_brand().colours) == []


def test_contrast_matches_known_values():
    assert contrast("#000000", "#FFFFFF") == pytest.approx(21.0)
    assert contrast("#FFFFFF", "#FFFFFF") == pytest.approx(1.0)


def test_a_too_light_accent_is_named():
    colours = Colours(primary="#0B1F3A", accent="#7FD3D9", primary_dark="#13294A", accent_dark="#5FC0C8")
    problems = contrast_problems(colours)
    assert problems and all("colours.accent" in p for p in problems)


def test_tokens_css_uses_the_brand_colours():
    css = tokens_css(load_brand())
    colours = load_brand().colours
    assert f"--primary: {colours.primary}" in css
    assert f"--accent: {colours.accent_dark}" in css


def test_a_wrong_colour_is_named(tmp_path: Path):
    text = DEFAULT_PATH.read_text(encoding="utf-8").replace('primary = "#0B1F3A"', 'primary = "navy"')
    with pytest.raises(BrandError, match=r"colours\.primary"):
        load_brand(write(tmp_path, text))


def test_a_missing_logo_file_is_named(tmp_path: Path):
    text = DEFAULT_PATH.read_text(encoding="utf-8").replace('logo_file = ""', 'logo_file = "brand/missing.svg"')
    with pytest.raises(BrandError, match=r"company\.logo_file"):
        load_brand(write(tmp_path, text))


def test_an_unknown_key_is_an_error(tmp_path: Path):
    text = DEFAULT_PATH.read_text(encoding="utf-8") + '\n[extra]\ncolour = "#000000"\n'
    with pytest.raises(BrandError, match="extra"):
        load_brand(write(tmp_path, text))
