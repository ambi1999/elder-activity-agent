# Clickable prototype

`index.html` is a working mock of the family and care web app as planned ([ADR 0025](../adr/0025-family-web-app.md), [ADR 0028](../adr/0028-access-by-person-and-care-overview.md)), with fictional data. Download it and open it in any browser; no internet connection is needed.

- **It works like the app:** the bottom tabs (People, Alerts, Settings), the back arrow, the account button (top right), every list row, button and form. Each page has its own address, so the browser's back button and links to a page work.
- **Actions change things** until you reload: "I'm checking" marks the alert and the overview; added contacts, people and phones appear; sign out returns to sign in. Forms check their values (for example, alert hours must be 1 to 12).
- **Two people to sign in as:** a nurse looking after ten people (the care overview first) or a daughter looking after Mum (straight to Mum's day, with an alert today). Switch at any time with **Signed in as** in the prototype bar; in the app itself, Sign out is in the account menu (top right) and at the bottom of Settings.
- **Responsive:** at 900 px and wider, the bottom tabs become a side menu, as in the real app. Tick **Phone frame** to show a phone-sized screen on a large display.
- **Guided tour:** steps through the story for presentations. **Simulate…** makes someone active again (their alert closes) or opens a new alert. **Start again** resets the data.

`elder-activity-prototype.pdf` shows each tour step on its own page with its note.

## On a phone, like the real app

On a phone the prototype fills the screen like the app: the header stays at the top, the tabs at the bottom, and the prototype controls fold into a small round button at the right (the sliders icon).

To open it **full screen with its own icon**, exactly as the real app will be installed (it is a progressive web app, ADR 0025), it must come from a web address rather than a downloaded file. This repository is public, so GitHub Pages can host it for free:

1. On GitHub: **Settings → Pages → Build and deployment → Source: Deploy from a branch**, branch **main**, folder **/docs**, **Save**.
2. After a minute, open `https://ambi1999.github.io/elder-activity-agent/prototype/` on the phone.
3. In Chrome: **⋮ → Add to home screen → Install**. On an iPhone, in Safari: **Share → Add to Home Screen**.

It then opens from its icon without the browser's address bar. The `docs/.nojekyll` file tells GitHub Pages to publish the files as they are, without building a Jekyll site. Opening the downloaded file instead (for example from WhatsApp or Files) works too, but inside a file viewer with its address bar.

## Changing it

The sources are in `scripts/prototype/` (`agent.html`, `agent.css`, `agent.js`); the brand comes from `docs/wireframes/brand.example.toml`. After editing:

```bash
uv run python scripts/make_prototype.py
```

The PDF is made from the guided tour with Playwright (one screenshot per step); ask for it to be regenerated after changes, or take the screenshots by hand.

GitHub shows `.html` files as source code; to view the prototype, download it (**Download raw file**) and open it.
