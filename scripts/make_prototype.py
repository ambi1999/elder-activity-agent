"""Build the clickable prototype of the family and care web app (docs/prototype/index.html).

A working mock of the app in one self-contained HTML file: every link, tab,
back arrow and the account menu work as they will in the real app (ADR 0025,
ADR 0028), each page has its own address (#people, #alert-a1 ...), actions
change the made-up data until the page is reloaded, and a guided tour steps
through the story for presentations. The layout is responsive: at 900 px and
wider the bottom tabs become a side menu, as in the real app.

The sources are in scripts/prototype/ (agent.html, agent.css, agent.js); this
script fills in the brand (docs/design.md) and joins them into one file.

  uv run python scripts/make_prototype.py                       # brand.example.toml
  uv run python scripts/make_prototype.py --brand config/brand.toml
  uv run python scripts/make_prototype.py --fragment out.html   # also a version without <html>/<head>, for publishing

Only the standard library is used. Names and data are fictional.
"""

import argparse
import html
import json
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCES = Path(__file__).resolve().parent / "prototype"
OUT = ROOT / "docs" / "prototype" / "index.html"
DEFAULT_BRAND = ROOT / "docs" / "wireframes" / "brand.example.toml"


def fill(text: str, brand: dict[str, dict[str, str]]) -> str:
    """Replace the {{placeholders}} in a source file with the brand's values (HTML-escaped)."""
    values = {
        "product": brand["product"]["name"],
        "company": brand["company"]["name"],
        "logo_text": brand["company"]["logo_text"],
        "primary": brand["colours"]["primary"],
        "accent": brand["colours"]["accent"],
    }
    for key, value in values.items():
        text = text.replace("{{" + key + "}}", html.escape(value))
    return text


def fragment(brand: dict[str, dict[str, str]]) -> str:
    """The page without <html>/<head>/<body>: title, style, markup and script."""
    title = html.escape(brand["product"]["name"]) + " Prototype"
    css = fill((SOURCES / "agent.css").read_text(encoding="utf-8"), brand)
    body = fill((SOURCES / "agent.html").read_text(encoding="utf-8"), brand)
    script = fill((SOURCES / "agent.js").read_text(encoding="utf-8"), brand)
    return (
        f'<title>{title}</title>\n<meta name="claude:viewport-fit-sides" content="cover">\n'
        f"<style>\n{css}</style>\n{body}<script>\n{script}</script>\n"
    )


def manifest(brand: dict[str, dict[str, str]]) -> str:
    """Web App Manifest, so the hosted prototype can be added to a phone's home screen and open full screen."""
    product = brand["product"]["name"]
    return json.dumps(
        {
            "name": f"{product} (prototype)",
            "short_name": product,
            "start_url": "./index.html",
            "display": "standalone",
            "background_color": "#f6f8fb",
            "theme_color": brand["colours"]["primary"],
            "icons": [
                {"src": "icon-192.png", "sizes": "192x192", "type": "image/png", "purpose": "any maskable"},
                {"src": "icon-512.png", "sizes": "512x512", "type": "image/png", "purpose": "any maskable"},
            ],
        },
        indent=2,
    )


def document(brand: dict[str, dict[str, str]]) -> str:
    """The complete standalone page, with what a phone needs to add it to the home screen."""
    primary = html.escape(brand["colours"]["primary"])
    install = (
        '<link rel="manifest" href="manifest.webmanifest">\n<link rel="apple-touch-icon" href="icon-192.png">\n'
        f'<meta name="theme-color" content="{primary}">\n<meta name="mobile-web-app-capable" content="yes">\n'
        '<meta name="apple-mobile-web-app-capable" content="yes">\n'
    )
    page = (
        '<!doctype html>\n<html lang="en"><head><meta charset="utf-8">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">\n'
        f"{install}{fragment(brand)}</head>\n</html>\n"
    )
    return page.replace("</style>\n", "</style>\n</head><body>\n", 1).replace(
        "</head>\n</html>\n", "</body></html>\n", 1
    )


def main() -> None:
    """Write docs/prototype/index.html (and, with --fragment, a publishable fragment)."""
    parser = argparse.ArgumentParser(description="Build the clickable prototype.")
    parser.add_argument("--brand", type=Path, default=DEFAULT_BRAND, help="brand TOML file")
    parser.add_argument("--fragment", type=Path, help="also write the page without <html>/<head> here")
    args = parser.parse_args()
    brand = tomllib.loads(args.brand.read_text(encoding="utf-8"))
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(document(brand), encoding="utf-8")
    (OUT.parent / "manifest.webmanifest").write_text(manifest(brand) + "\n", encoding="utf-8")
    print(f"Wrote {OUT.relative_to(ROOT)}")
    if args.fragment:
        args.fragment.write_text(fragment(brand), encoding="utf-8")
        print(f"Wrote {args.fragment}")


if __name__ == "__main__":
    main()
