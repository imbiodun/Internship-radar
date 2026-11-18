# Internship Radar

Internship Radar finds current software internships, checks them against a candidate profile, ranks the matches, and drafts an application opening for user approval.

The app is built for the Junction 2026 Exa challenge. It uses live APIs when keys are configured and SQLite caching to limit API costs.

## Requirements

- Python 3.12 or newer
- Exa API key
- At least one LLM provider key

Supported providers:

- Anthropic
- Gemini-compatible OpenAI endpoint
- Verda-compatible OpenAI endpoint

## Setup

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -e .
cp .env.example .env
```

Fill in the keys and provider settings in `.env`.

Providers without a key are skipped. `LLM_CHAIN` controls provider fallback order:

```text
LLM_CHAIN=anthropic,gemini,verda
```

To practice without API calls, set:

```text
CACHE_ONLY=true
```

## Run

```bash
.venv/bin/python -m uvicorn app.main:app --reload
```

Open:

- UI: `http://127.0.0.1:8000/static/`
- API docs: `http://127.0.0.1:8000/docs`
- Stats: `http://127.0.0.1:8000/api/stats`

## Demo

Use a generic example profile:

```text
Role: Software Engineering Intern
Location: Finland
Skills: Python, FastAPI
Languages: English
Work authorization: Eligible to work in Finland
```

Run the profile once before the demo to warm the cache. Repeat with `CACHE_ONLY=true` to prove cached results do not call external APIs.

## API

Find and rank internships:

```bash
curl -X POST http://127.0.0.1:8000/api/radar \
  -H "Content-Type: application/json" \
  -d '{
    "role": "Software Engineering Intern",
    "skills": ["Python", "FastAPI"],
    "location": "Finland",
    "languages": ["English"],
    "work_authorization": "Eligible to work in Finland",
    "extra_notes": ""
  }'
```

Inspect cache and provider counters:

```bash
curl http://127.0.0.1:8000/api/stats
```

## Tests

```bash
.venv/bin/python -m unittest discover -s tests -v
```

## Safety and cost controls

- Exa and LLM results are cached in `radar.db`.
- Exa search calls are limited to five queries and ten results per query.
- Page extraction is capped per run.
- Ranking is batched into one LLM call.
- Cached data is labelled as cached.
- AI-generated drafts are shown for approval and are never sent automatically.
