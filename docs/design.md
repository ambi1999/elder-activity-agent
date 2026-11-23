# Design: brand, tokens and tone

How the family web app looks and reads. Layouts and branded mockups of every screen are in [wireframes/](wireframes/README.md); accessibility and mobile standards are in [ADR 0025](adr/0025-family-web-app.md).

## Brand is configuration

The company name, logo, product name and colours live in **one file, `config/brand.toml`** (built in step D), never in templates or CSS. Changing the company or its look means editing that file only.

```toml
# config/brand.toml (example values; see wireframes/brand.example.toml)
[company]
name = "TechData Innovate"            # footer and sign-in page
website = "https://techdatainnovate.com.au/"
logo_file = "static/brand/logo.svg"   # empty: show logo_text instead
logo_text = "∎ TECHDATA INNOVATE"

[product]
name = "Elder Activity"               # the app's own name, in the header and the installed app

[colours]
primary = "#0B1F3A"                   # navy, from the company site; 16.5:1 on white
accent = "#0A6B74"                    # teal, assumed; 6.2:1 on white
```

- At startup the app loads it into typed settings, checks every value (colours are `#RRGGBB`, the logo file exists), and fails with the setting's name if one is wrong.
- Templates read `brand.company.name`, `brand.product.name` and the logo; the colours become CSS custom properties (`--color-primary`, `--color-accent`) in one generated `tokens.css`, which every stylesheet uses.
- The Web App Manifest (name, theme colour, icons) is generated from the same values.
- **Contrast is tested in CI:** each text and control colour pair must reach WCAG 2.2 AA (4.5:1 for text, 3:1 for controls and focus outlines), so a new brand colour that is too light fails the build.
- The colours above are a starting point: the navy is the site's theme colour; the accent and fonts could not be read from the site and should be replaced with the real ones when known.

## Tokens

| Token | Value | Use |
|---|---|---|
| `--color-primary` | brand primary | Header, primary buttons, headings |
| `--color-accent` | brand accent | Links, selected tab, charts |
| `--color-ok` | `#2E7D32` | "All looks normal" |
| `--color-warn-text`, `--color-warn-bg` | `#8A5300`, `#FFF4E0` | Alerts (darker than the usual amber, which fails contrast) |
| `--color-surface`, `--color-text` | `#F6F8FB`, `#1B2430` | Page background and body text |
| `--font-body` | the phone's system font | Readable, fast, no download |
| `--radius`, `--tap-target` | `12px`, `48px` | Cards and buttons; every control at least 48 px |

Status colours are fixed and separate from the brand, so an alert never looks like decoration and a rebrand can't weaken it. A dark theme is derived from the same tokens (`prefers-color-scheme`).

## Tone

- **Plain and warm**, for families who may be worried: "All looks normal", "No activity for 4 hours", "I'm checking on her".
- **Facts before interpretation**: what the data shows and when, then the agent's explanation, labelled as written by the agent.
- **Phone problems are worded as phone problems** ("the phone has stopped sending"), never as a concern about the person.
- No jargon, no medical claims ([ADR 0002](adr/0002-wellness-not-medical-device.md)), no location ever.
- The company appears quietly ("Made by …" on sign-in, the logo in the footer); the app's own name leads.
