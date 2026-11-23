# 0025. Build the family interface as a server-rendered, accessible web app that works well on phones

- **Status:** Accepted
- **Date:** 2026-11-22

## Context

Family members need to sign in, add a phone, see how their person's day is going, manage alert contacts, and acknowledge alerts. Most will do this on their own phones, some on a computer, and many will be older themselves. The developer works in Python, and a working version is wanted soon.

## Decision

- **A web app served by the same FastAPI service**: server-rendered pages with **Jinja2** templates and **HTMX** for small updates (acknowledging an alert, refreshing today's activity), plain CSS, no JavaScript build step. It is installable as a **progressive web app** (a Web App Manifest and a small service worker that caches only the app's shell, never household data).
- **Sign-in by email magic link**: no passwords. A link is single-use, valid for 15 minutes, stored only as a hash, and rate-limited per address and per IP. A session is a random id in a cookie (`Secure`, `HttpOnly`, `SameSite=Lax`, `__Host-` prefix), stored server-side so it can be revoked. Forms and HTMX requests carry a CSRF token.
- **Standards it must meet** (checked in CI where a tool can):
  - **WCAG 2.2 level AA**, in particular: Reflow at 320 CSS pixels with no horizontal scrolling (1.4.10); text resizable to 200% (1.4.4); any orientation (1.3.4); targets at least 24 px, and 48 px used by design (2.5.8); contrast 4.5:1 for text and 3:1 for controls (1.4.3, 1.4.11); focus never hidden (2.4.11); sign-in without memory tests (3.3.8); names, roles and status messages announced, with HTMX updates in `aria-live` regions (4.1.2, 4.1.3).
  - **Responsive, mobile-first design**: `<meta name="viewport" content="width=device-width, initial-scale=1">` and never disabling zoom; layouts with CSS Grid and Flexbox; sizes in `rem`; respect `prefers-reduced-motion` and `prefers-color-scheme`.
  - **WAI-ARIA Authoring Practices** for any widget beyond native HTML (native elements first).
  - **Core Web Vitals** on a mid-range phone: LCP under 2.5 s, INP under 200 ms, CLS under 0.1.
  - **OWASP ASVS** level 1 for authentication, sessions and access control, with a Content Security Policy that allows only the app's own scripts.
- **Testing**: Playwright tests with axe-core at 320, 375 and 412 px widths and at 200% text; Lighthouse CI for performance and accessibility; a manual check with TalkBack (Android) and VoiceOver (iPhone) before each release.
- **Branding is configuration.** The company name, logo, product name and colours come from `config/brand.toml` and generated design tokens, never from templates or CSS, and colour contrast is tested in CI ([design.md](../design.md)). A rebrand or a white-label deployment is a configuration change.
- **Never shows location**, and shows activity only as daily and hourly summaries (ADR 0022).

## Alternatives considered

| Option | Pros | Cons |
|---|---|---|
| Server-rendered with HTMX, as a PWA (chosen) | One language and service; fast on slow phones; accessible by default with native HTML | Less suited to rich offline use |
| Single-page app (React, Vue) | Rich interactions | A second language, build and deployment; accessibility and performance need more care |
| Native family app (Android and iOS) | Push notifications, app store presence | Two more apps to build and publish before anything works |
| Telegram bot only | No web app at all | Setup, contacts and history are awkward in chat; not everyone uses Telegram |

## Consequences

The service gains templates, static files, sessions and an email sender. Accessibility and household isolation become CI checks. Push notifications in the browser are possible later through the same PWA.

## When to revisit

If families need offline access or rich charts that HTMX makes awkward, or if a native app is needed for notifications.

## Update (2026-11-24, step D1)

- **No HTMX yet.** Plain forms (post, then redirect) and one small script (`app/static/app.js`: the account menu, and refreshing the care overview) were enough, and keep the Content Security Policy strict with no third-party script. HTMX can still be added if a page needs partial updates the script can't do simply.
- **No service worker yet.** The app is installable (manifest and icons); a service worker that caches only the app's shell follows when offline use is needed.
- **Automated accessibility checks later.** CI runs unit and isolation tests; axe-core and Lighthouse are added before real users. Until then, layouts are checked by hand at 320, 375 and 412 px and at 200% text.
