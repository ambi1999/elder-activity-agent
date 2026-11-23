"""The brand: company, product name, logo and colours, from config/brand.toml (story D-4).

Nothing about the brand is written in templates or CSS. Templates read the
``Brand`` object, and the colours become CSS custom properties in a generated
``tokens.css`` (see ``tokens_css``), so a rebrand or a white-label deployment
is a change to config/brand.toml only (docs/design.md).

``contrast_problems`` checks each text and control colour pair against WCAG 2.2
AA; tests/test_brand.py runs it in CI so a colour that is too light fails the build.
"""

import tomllib
from functools import lru_cache
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PATH = ROOT / "config" / "brand.toml"
STATIC = Path(__file__).resolve().parent / "static"

COLOUR = r"^#[0-9A-Fa-f]{6}$"

# Fixed backgrounds from app/static/app.css that brand colours must stand out against.
WHITE, SURFACE = "#FFFFFF", "#F6F8FB"
DARK_CARD, DARK_SURFACE = "#172231", "#111A25"


class BrandError(RuntimeError):
    """config/brand.toml is missing or has a wrong value."""


class _Section(BaseModel):
    # Unknown keys are errors, so a misspelt setting is noticed instead of ignored.
    model_config = ConfigDict(extra="forbid", frozen=True)


class Company(_Section):
    """The company running the service."""

    name: str = Field(min_length=1, max_length=80)
    website: str = Field(pattern=r"^(https://\S+)?$")
    logo_text: str = Field(min_length=1, max_length=60)
    logo_file: str = ""

    @field_validator("logo_file")
    @classmethod
    def _logo_exists(cls, value: str) -> str:
        # A path inside app/static/, so it is served at /static/<logo_file>.
        if value and (".." in value or not (STATIC / value).is_file()):
            raise ValueError(f"no file app/static/{value}")
        return value


class Product(_Section):
    """The app's own name."""

    name: str = Field(min_length=1, max_length=40)


class Colours(_Section):
    """Brand colours, as #RRGGBB."""

    primary: str = Field(pattern=COLOUR)
    accent: str = Field(pattern=COLOUR)
    primary_dark: str = Field(pattern=COLOUR)
    accent_dark: str = Field(pattern=COLOUR)


class Brand(_Section):
    """Everything in config/brand.toml."""

    company: Company
    product: Product
    colours: Colours


def load_brand(path: Path = DEFAULT_PATH) -> Brand:
    """Read and check the brand file.

    Raises:
        BrandError: If the file can't be read or a value is wrong; the message
            names each wrong value as ``section.key``.
    """
    try:
        raw = tomllib.loads(path.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError) as err:
        raise BrandError(f"Cannot read brand file {path}: {err}") from err
    try:
        return Brand.model_validate(raw)
    except ValidationError as err:
        problems = "; ".join(f"{'.'.join(str(p) for p in e['loc'])}: {e['msg']}" for e in err.errors())
        raise BrandError(f"Invalid brand in {path.name}: {problems}") from err


@lru_cache(maxsize=1)
def get_brand() -> Brand:
    """The brand for this process, loaded on first use."""
    return load_brand()


# ---------------------------------------------------------------------------
# Contrast (WCAG 2.2: 1.4.3 text 4.5:1, 1.4.11 controls and focus 3:1)
# ---------------------------------------------------------------------------


def _luminance(colour: str) -> float:
    """Relative luminance of a #RRGGBB colour, as defined by WCAG."""
    channels = []
    for i in (1, 3, 5):
        c = int(colour[i : i + 2], 16) / 255
        channels.append(c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4)
    r, g, b = channels
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast(a: str, b: str) -> float:
    """The contrast ratio of two colours, from 1 (same) to 21 (black on white)."""
    la, lb = sorted((_luminance(a), _luminance(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


def contrast_problems(colours: Colours) -> list[str]:
    """Every brand colour pair that fails WCAG 2.2 AA, described in words; empty if all pass."""
    pairs = [
        # (foreground, background, minimum, what it is)
        ("#FFFFFF", colours.primary, 4.5, "white text on colours.primary (header, buttons)"),
        (colours.primary, WHITE, 4.5, "colours.primary text on white"),
        (colours.accent, WHITE, 4.5, "colours.accent links on white cards"),
        (colours.accent, SURFACE, 4.5, "colours.accent links on the page background"),
        ("#FFFFFF", colours.primary_dark, 4.5, "white text on colours.primary_dark"),
        (colours.accent_dark, DARK_CARD, 4.5, "colours.accent_dark links on dark cards"),
        (colours.accent_dark, DARK_SURFACE, 4.5, "colours.accent_dark links on the dark background"),
    ]
    return [
        f"{what}: {contrast(fg, bg):.2f}:1, needs {need}:1" for fg, bg, need, what in pairs if contrast(fg, bg) < need
    ]


def tokens_css(brand: Brand) -> str:
    """The brand colours as CSS custom properties; app/static/app.css uses only these names."""
    c = brand.colours
    return (
        "/* Generated from config/brand.toml by app/brand.py. Don't edit; change the brand file. */\n"
        f":root {{ --primary: {c.primary}; --accent: {c.accent}; --bar: {c.accent}; }}\n"
        "@media (prefers-color-scheme: dark) {\n"
        f"  :root {{ --primary: {c.primary_dark}; --accent: {c.accent_dark}; --bar: {c.accent_dark}; }}\n"
        "}\n"
    )
