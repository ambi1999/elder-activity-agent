# Elder Activity Agent

An AI agent that watches phone sensor data (movement, light, charging) for signs that an older person has had a normal, active day, and sends a daily summary plus urgent alerts to family.

**Current stage: Phase 0, a "hello world" agent** with two tools (time and calculator), served by FastAPI and deployed to Google Cloud Run through GitHub Actions.

## Stack

Python 3.12 · uv · FastAPI · Gemini API (free tier) · Docker · Google Cloud Run · GitHub Actions · Google Secret Manager

## How the agent works

`app/agent.py` runs the core agent loop: send the message and the tool list to Gemini; if Gemini asks for a tool, run it and send the result back; repeat until it gives a final answer. Automatic function calling is switched off so the loop is explicit.

## 1. Run it locally

Install [uv](https://docs.astral.sh/uv/), then from the project folder:

```bash
uv sync                            # installs Python 3.12 if needed, creates .venv, writes uv.lock
uv run pytest                      # runs without an API key (Gemini is mocked)

export GEMINI_API_KEY=your-key     # Windows PowerShell: $env:GEMINI_API_KEY="your-key"
uv run python -m app.agent "what is 17 times 23?"

uv run uvicorn app.main:app --reload   # then open http://localhost:8000/docs
```

Commit `uv.lock`: CI and Docker install from it, so every environment gets identical package versions.
Add a package with `uv add <name>` (or `uv add --dev <name>` for dev-only tools).

Get a Gemini key at Google AI Studio. Check there which Flash models your free tier includes; set `GEMINI_MODEL` if the default alias doesn't work.

## 2. One-time Google Cloud setup

Install the gcloud CLI, then run these once. Replace the values in the first three lines.

```bash
PROJECT_ID=your-project-id
GH_REPO=your-github-username/elder-activity-agent
GEMINI_KEY=your-gemini-key

gcloud config set project $PROJECT_ID
PROJECT_NUMBER=$(gcloud projects describe $PROJECT_ID --format='value(projectNumber)')

# Turn on the services we use
gcloud services enable run.googleapis.com cloudbuild.googleapis.com \
  artifactregistry.googleapis.com secretmanager.googleapis.com iamcredentials.googleapis.com

# Store secrets in Secret Manager (never in the repo)
printf "%s" "$GEMINI_KEY" | gcloud secrets create gemini-api-key --data-file=-
printf "%s" "$(openssl rand -hex 24)" | gcloud secrets create app-api-key --data-file=-

# Let the running app read those secrets
for s in gemini-api-key app-api-key; do
  gcloud secrets add-iam-policy-binding $s \
    --member=serviceAccount:$PROJECT_NUMBER-compute@developer.gserviceaccount.com \
    --role=roles/secretmanager.secretAccessor
done

# A service account that GitHub Actions deploys as
gcloud iam service-accounts create github-deployer
SA=github-deployer@$PROJECT_ID.iam.gserviceaccount.com
for role in roles/run.admin roles/cloudbuild.builds.editor roles/artifactregistry.admin \
            roles/iam.serviceAccountUser roles/storage.admin roles/serviceusage.serviceUsageConsumer; do
  gcloud projects add-iam-policy-binding $PROJECT_ID --member=serviceAccount:$SA --role=$role
done

# Workload Identity Federation: GitHub proves who it is, no long-lived keys stored anywhere
gcloud iam workload-identity-pools create github --location=global
gcloud iam workload-identity-pools providers create-oidc github-provider \
  --location=global --workload-identity-pool=github \
  --issuer-uri=https://token.actions.githubusercontent.com \
  --attribute-mapping="google.subject=assertion.sub,attribute.repository=assertion.repository" \
  --attribute-condition="assertion.repository=='$GH_REPO'"
gcloud iam service-accounts add-iam-policy-binding $SA \
  --role=roles/iam.workloadIdentityUser \
  --member="principalSet://iam.googleapis.com/projects/$PROJECT_NUMBER/locations/global/workloadIdentityPools/github/attribute.repository/$GH_REPO"

# Print the values for GitHub
echo "GCP_PROJECT_ID=$PROJECT_ID"
echo "GCP_SERVICE_ACCOUNT=$SA"
echo "GCP_WIF_PROVIDER=projects/$PROJECT_NUMBER/locations/global/workloadIdentityPools/github/providers/github-provider"
```

Also set a **budget alert** (Billing → Budgets & alerts, e.g. $1) so you're emailed long before any charge matters.

## 3. GitHub setup

In your repo: Settings → Secrets and variables → Actions → add the three values printed above as repository secrets: `GCP_PROJECT_ID`, `GCP_SERVICE_ACCOUNT`, `GCP_WIF_PROVIDER`.

Push to `main`. The workflow runs the tests, deploys to Cloud Run, and smoke-tests `/health`.

## 4. Try the live agent

```bash
URL=$(gcloud run services describe elder-activity-agent --region us-central1 --format='value(status.url)')
KEY=$(gcloud secrets versions access latest --secret=app-api-key)

curl -X POST "$URL/chat" -H "Content-Type: application/json" -H "X-API-Key: $KEY" \
  -d '{"message": "what is 17 times 23, and what time is it in Tokyo?"}'
```

The response includes `tool_calls`, showing which tools the agent used.

## Design notes

- **Safe calculator:** parses arithmetic with Python's `ast` module instead of `eval()`, so input can't run code.
- **API key on `/chat`:** the Cloud Run URL is public; the key stops strangers using up the Gemini quota.
- **Graceful failure:** if Gemini is down or rate-limited, the API returns a clear 502 instead of crashing.
- **Cost guardrails:** `--max-instances 1` caps scaling; Cloud Run scales to zero when idle.
- **Privacy (for later phases):** on Gemini's free tier, prompts may be used by Google to improve its products, so only anonymised activity summaries will ever be sent, never raw sensor data, names or locations.

## Roadmap

1. Phone streams sensor data to the API; store in Neon Postgres
2. Hourly activity features and charts
3. Personal baseline and rule-based triggers
4. Agent decisions, check-ins, daily summaries and urgent alerts via Telegram
5. Simulated scenarios to measure accuracy; uptime monitoring
