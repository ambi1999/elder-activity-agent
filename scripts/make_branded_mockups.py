"""Draw branded mockups of every family-app screen from a brand file (docs/design.md).

The mockups show what the plain wireframes will look like with the company's
name, logo text and colours applied, so the look can be reviewed before the
real pages are built (step D). Change the brand file, run this, then re-render
the images (commands in docs/wireframes/README.md):

  uv run python scripts/make_branded_mockups.py
  uv run python scripts/make_branded_mockups.py --brand config/brand.toml

Writes docs/wireframes/branded-phone.html and branded-desktop.html. Only the
standard library is used; names in the mockups are neutral examples.
"""

import argparse
import html
import random
import tomllib
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs" / "wireframes"
DEFAULT_BRAND = OUT / "brand.example.toml"
HOURS_AWAKE = range(7, 21)  # hours with activity in the example data


def _css(c: dict[str, str]) -> str:
    """Stylesheet built from the brand colours; status colours stay fixed (design.md)."""
    return f"""
:root {{ --primary:{c["primary"]}; --accent:{c["accent"]}; --ok:{c["ok"]};
         --warn-text:{c["warn_text"]}; --warn-bg:{c["warn_bg"]}; --text:#1b2430; --muted:#5a6573;
         --surface:#f6f8fb; --line:#dde3ea; }}
body {{ margin:0; background:#fff; font-family:system-ui,-apple-system,'Segoe UI',Roboto,Arial,sans-serif;
       color:var(--text); white-space:nowrap; }}
.ph {{ display:inline-block; vertical-align:top; margin:8px; width:360px; height:690px; border:2px solid #444;
      border-radius:24px; position:relative; overflow:hidden; white-space:normal; font-size:14px;
      background:var(--surface); }}
.hd {{ background:var(--primary); color:#fff; height:56px; display:flex; align-items:center; padding:0 18px;
      font-weight:600; font-size:17px; }}
.hd span {{ margin-left:auto; }}
.c {{ padding:14px 16px; }}
.card {{ background:#fff; border:1px solid var(--line); border-radius:14px; padding:12px 14px; margin-bottom:10px; }}
.g {{ display:grid; grid-template-columns:1fr 1fr; gap:10px; }}
.l {{ color:var(--muted); font-size:12px; }}
.n {{ font-size:26px; font-weight:700; color:var(--primary); }}
.ok {{ color:var(--ok); font-weight:700; }}
.btn {{ display:block; text-align:center; background:var(--primary); color:#fff; border-radius:12px; padding:14px;
       font-weight:600; margin:12px 0; }}
.btn2 {{ display:block; text-align:center; border:2px solid var(--primary); color:var(--primary);
        border-radius:12px; padding:12px; font-weight:600; margin:8px 0; }}
.warn {{ background:var(--warn-bg); border-color:#f0c27a; }}
.wt {{ color:var(--warn-text); font-weight:700; }}
.row {{ display:flex; justify-content:space-between; padding:7px 0; border-bottom:1px solid var(--line); }}
.in {{ border:1px solid #b8c2cf; border-radius:10px; padding:10px; background:#fff; color:#8a94a1; margin:4px 0 10px; }}
.bars {{ display:flex; align-items:flex-end; gap:3px; border-bottom:1px solid #c8d0da; }}
.bars i {{ display:block; width:10px; border-radius:2px 2px 0 0; background:var(--accent); opacity:.85; }}
.qr {{ width:150px; height:150px; margin:6px auto; border:8px solid #fff; outline:1px solid var(--line);
      background:repeating-conic-gradient(#1b2430 0 25%,#fff 0 50%) 0 0/18px 18px; }}
.nav {{ position:absolute; bottom:34px; left:0; right:0; display:flex; background:#fff; border-top:1px solid var(--line); }}
.nav div {{ flex:1; text-align:center; padding:10px 0; font-size:12px; color:var(--muted); }}
.nav .on {{ color:var(--accent); font-weight:700; border-top:3px solid var(--accent); }}
.ft {{ position:absolute; bottom:8px; width:100%; text-align:center; font-size:11px; color:var(--muted);
      letter-spacing:.06em; }}
a {{ color:var(--accent); }}
.dt {{ display:inline-block; margin:8px; width:1100px; height:560px; border:2px solid #444; border-radius:10px;
      position:relative; overflow:hidden; white-space:normal; font-size:14px; background:var(--surface); }}
.side {{ position:absolute; top:56px; left:0; bottom:0; width:190px; background:#fff; border-right:1px solid var(--line);
        padding:12px; }}
.side div {{ padding:10px 8px; color:var(--muted); }}
.side .on {{ color:var(--accent); font-weight:700; background:var(--surface); border-radius:8px; }}
.main {{ position:absolute; top:56px; left:205px; right:0; padding:14px 18px; }}
"""


def _bars(rng: random.Random, height: int = 70, width: int = 10) -> str:
    bars = "".join(
        f'<i style="width:{width}px;height:{rng.randint(8, height - 4) if hour in HOURS_AWAKE else 2}px"></i>'
        for hour in range(24)
    )
    return f'<div class="bars" style="height:{height}px">{bars}</div>'


def _axis() -> str:
    labels = "".join(f"<span>{t}</span>" for t in ("12am", "6am", "12pm", "6pm", "12am"))
    return f'<div class="l" style="display:flex;justify-content:space-between">{labels}</div>'


def _nav(selected: int) -> str:
    tabs = ("Today", "Days", "Alerts", "Settings")
    items = "".join(f'<div class="{"on" if i == selected else ""}">{t}</div>' for i, t in enumerate(tabs))
    return f'<div class="nav">{items}</div>'


def _phone(title: str, body: str, footer: str, nav: int | None = None, menu: bool = True) -> str:
    right = "<span>☰</span>" if menu else ""
    tabs = _nav(nav) if nav is not None else ""
    return f'<div class="ph"><div class="hd">{title}{right}</div><div class="c">{body}</div>{tabs}{footer}</div>'


def phone_screens(brand: dict[str, Any], rng: random.Random) -> list[str]:
    """The six phone-width screens, in the order of the plain wireframes."""
    company = html.escape(brand["company"]["name"])
    product = html.escape(brand["product"]["name"])
    footer = f'<div class="ft">{html.escape(brand["company"]["logo_text"])}</div>'
    days = "".join(
        f'<div class="card"><div class="row" style="border:0;padding:0 0 6px"><b>{day}</b>'
        f'<span class="l">{steps} steps · {note}</span></div>{_bars(rng, 40, 9)}</div>'
        for day, steps, note in [
            ("Today", "3,412", "normal"),
            ("Sat 21", "4,980", "normal"),
            ("Fri 20", "5,210", "normal"),
            ("Thu 19", "1,104", "1 alert"),
        ]
    )
    return [
        _phone(
            product,
            f"""<div style="height:24px"></div>
<div style="font-size:22px;font-weight:700;color:var(--primary)">Sign in</div>
<p>Enter your email and we'll send you a link. No password needed.</p>
<div class="l">Email</div><div class="in">daughter@example.com</div>
<a class="btn">Email me a sign-in link</a>
<p class="l">The link works once, for 15 minutes.</p><p class="l">Made by <a>{company}</a></p>""",
            footer,
            menu=False,
        ),
        _phone(
            "Mum · Today",
            f"""<div class="card"><span class="ok">● All looks normal</span><div class="l">Last active 7:42 pm (18 min ago)</div></div>
<div class="g"><div class="card"><div class="l">Steps today</div><div class="n">3,412</div></div>
<div class="card"><div class="l">Active hours</div><div class="n">6.5</div></div>
<div class="card"><div class="l">Phone battery</div><div class="n">64%</div></div>
<div class="card"><div class="l">Phone last sent</div><div class="n" style="font-size:20px">7:45 pm</div></div></div>
<div class="card"><b>Activity by hour</b>{_bars(rng)}{_axis()}</div>""",
            footer,
            nav=0,
        ),
        _phone(
            "Mum · Past days",
            days + '<div class="l">Each chart has a text version for screen readers.</div>',
            footer,
            nav=1,
        ),
        _phone(
            "Mum · Add phone",
            """<div class="card"><b>1.</b> On Mum's phone, open the logger app › Settings › Connection.<br>
<b>2.</b> Tap <b>Scan setup QR code</b> and point it here.<br><b>3.</b> Mum agrees on her phone.</div>
<div class="qr"></div>
<div class="card"><b>This code works for 30 minutes</b> and is shown only once.
<div class="l" style="margin-top:6px">Can't scan? Type these instead:</div>
<div style="font-size:12px">Endpoint: https://example.com/v1/readings<br>Token: XXXX-XXXX-… <a>Copy</a></div></div>
<div class="l">⏳ Waiting for the phone… (updates by itself)</div>""",
            footer,
        ),
        _phone(
            "Alert",
            """<div class="card warn"><div class="wt">⚠ No activity for 4 hours</div>Mum · since 9:05 am · during waking hours</div>
<div class="card">Mum's phone is still sending data (battery 58%), but there have been no steps or screen use
since 9:05 am. On most days she is active by 9:30.<div class="l" style="margin-top:6px">Written by the agent
from activity summaries.</div></div>
<div class="card"><div class="l">Sent to</div>Daughter (Telegram), Son (email)</div>
<a class="btn">I'm checking on her</a>""",
            footer,
            nav=2,
        ),
        _phone(
            "Settings",
            """<b>Alert contacts</b>
<div class="card" style="padding:4px 14px"><div class="row"><span>✈ Daughter · Telegram</span><span class="ok">linked</span></div>
<div class="row" style="border:0"><span>✉ son@example.com</span><span class="wt">confirm email</span></div></div>
<a class="btn2">+ Add contact</a>
<b>When to alert</b>
<div class="l" style="margin-top:6px">Waking hours</div><div class="in">08:00 – 21:00</div>
<div class="l">No activity for (hours, 1–12)</div><div class="in">4</div>
<div class="l">Phone silent for (hours, 1–48)</div><div class="in">6</div>""",
            footer,
            nav=3,
        ),
    ]


def desktop_screen(brand: dict[str, Any], rng: random.Random) -> str:
    """The Today page at computer width: sidebar, four tiles, the last four days."""
    product = html.escape(brand["product"]["name"])
    logo = html.escape(brand["company"]["logo_text"])
    rows = "".join(
        f'<div style="display:flex;align-items:flex-end;gap:12px;margin:8px 0"><span style="width:60px">{day}</span>'
        f'{_bars(rng, 46, 14)}<span style="width:90px;text-align:right">{steps} steps</span>'
        f'<span class="l" style="width:110px">{note}</span></div>'
        for day, steps, note in [
            ("Today", "3,412", "normal"),
            ("Sat 21", "4,980", "normal"),
            ("Fri 20", "5,210", "normal"),
            ("Thu 19", "1,104", "1 alert (ack'd)"),
        ]
    )
    tiles = (
        '<div class="card"><span class="ok">● All looks normal</span><div class="l">Last active 7:42 pm</div></div>'
        '<div class="card"><div class="l">Steps today</div><div class="n">3,412</div></div>'
        '<div class="card"><div class="l">Active hours</div><div class="n">6.5</div></div>'
        '<div class="card"><div class="l">Phone</div><div class="n" style="font-size:18px">64% · sent 7:45 pm</div></div>'
    )
    menu = "".join(
        f'<div class="{"on" if i == 0 else ""}">{t}</div>'
        for i, t in enumerate(("Today", "Past days", "Alerts", "Phones", "Settings"))
    )
    return f"""<div class="dt"><div class="hd">{product} · Mum<span style="font-size:13px;font-weight:400">Daughter ▾</span></div>
<div class="side">{menu}</div>
<div class="main"><div style="display:grid;grid-template-columns:repeat(4,1fr);gap:12px">{tiles}</div>
<div class="card" style="margin-top:8px"><b>Last 4 days, activity by hour</b>{rows}</div></div>
<div class="ft">{logo}</div></div>"""


def _page(title: str, css: str, body: str) -> str:
    return (
        f'<!doctype html>\n<html lang="en"><head><meta charset="utf-8"><title>{title}</title>'
        f"<style>{css}</style></head><body>{body}</body></html>\n"
    )


def main() -> None:
    """Read the brand file and write the two mockup pages."""
    parser = argparse.ArgumentParser(description="Draw branded mockups of the family app.")
    parser.add_argument("--brand", type=Path, default=DEFAULT_BRAND, help="brand TOML file")
    args = parser.parse_args()
    brand = tomllib.loads(args.brand.read_text(encoding="utf-8"))
    css = _css(brand["colours"])
    rng = random.Random(3)  # noqa: S311 - example chart data, not security; fixed seed: the same example data every time, so diffs show real changes
    (OUT / "branded-phone.html").write_text(
        _page("Branded mockup: phone", css, "".join(phone_screens(brand, rng))), encoding="utf-8"
    )
    (OUT / "branded-desktop.html").write_text(
        _page("Branded mockup: computer", css, desktop_screen(brand, rng)), encoding="utf-8"
    )
    print(f"Wrote branded-phone.html and branded-desktop.html in {OUT.relative_to(ROOT)} from {args.brand.name}")


if __name__ == "__main__":
    main()
