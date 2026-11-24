# 0030. Bill through billing accounts, and take payment on the website with Stripe

- **Status:** Accepted (planned for release B; provider billing in release L)
- **Date:** 2026-11-24

## Context

The service will charge for itself. The decision of 2026-11-24 is:

- **Families pay first.** The value they pay for is the alerts and the view of a person's day in the web app, not the phone app. The person carrying the phone shouldn't have to buy anything.
- **Care providers pay later.** This starts once families have written reviews, with care teams (release L). A provider pays for many households, and may take over paying for a household a family already pays for.
- **Australia first.** For reference, monitored personal alarms cost families about AU$50–70 a month. This service has no call centre, so it will be priced well below that. Prices are settings, to be tested.

Two choices are expensive to change later: **what a subscription belongs to**, and **where payment happens**.

## Decision

- **A subscription belongs to a billing account, not to a household.** Each household points to one billing account. A family's account pays for its own household (usually one). A provider's account (release L) pays for many, with the Stripe subscription quantity equal to the number of households. A provider taking over a household changes which account the household points to, and ends the family's subscription with a pro-rata credit.
- **Payment happens on the website, through Stripe's hosted pages.** Stripe Checkout starts a subscription, and the Stripe billing portal changes or cancels it. Card details go to Stripe only and never reach this service, which keeps card-security (PCI DSS) obligations at their lightest (SAQ A). The phone app offers nothing to buy, so Google Play's billing rules and fees don't apply.
- **Stripe's webhook is the only source of payment state.** Each event's signature and timestamp are checked, and its ID is stored so repeats are ignored. Returning from checkout shows "thanks, confirming your payment" until the webhook arrives.
- **One function decides what a household may use.** It works from the plan and state of the household's billing account, the way `app/access.py` decides access. Pages and jobs ask it and never read the plan themselves.
- **Safety first when payment lapses.** Alerts continue through a grace period, with warnings to owners. Afterwards, pages are read-only and data is kept. Nothing is deleted for not paying.
- **Paying is not access.** A provider's billing admins see the bill only. Seeing people still needs the household owner's grant to a care team (ADR 0028, EA-FR-TEAM-002).
- **Test mode first.** Stripe's test mode costs nothing. Live mode is a change of environment variables, made after the business setup: ABN, GST registration once required, terms, privacy and refund policies, and wording checked by a lawyer.

## Alternatives considered

| Option | Pros | Cons |
|---|---|---|
| Billing account between households and subscriptions, Stripe on the web (chosen) | Families now and providers later with the same model; no card data here; no app store fees | One more table and one indirection in the plan check |
| Subscription stored on the household | Slightly simpler for families | Providers paying for many households, and taking over a household, would need the model and billing pages rebuilt |
| Google Play in-app subscription in the logger | Familiar purchase flow on Android | Wrong payer (the phone is the older person's); Google's fees; the logger is a generic product that knows nothing about this service (ADR 0023) |
| Own card handling or another payment form on our pages | Full control | Card data in scope, with far heavier security obligations |

## Consequences

- Release B needs about two pull requests: first, billing accounts, plans, the trial and the plan check, still free; then Stripe checkout, the billing portal and the webhook, in test mode. Reviews (SRS 3.17) are a separate small pull request.
- New secrets, `STRIPE_SECRET_KEY` and `STRIPE_WEBHOOK_SECRET`, are kept in the environment only, as for every other secret.
- Prices and limits are settings, so trying different prices needs no code.
- The threat model gains the webhook endpoint and the billing pages.

## When to revisit

- When a care provider wants to pay, for invoices and per-household pricing (release L).
- When selling outside Australia (tax, currencies, app store rules).
- If Stripe's fees or terms change enough to matter.
