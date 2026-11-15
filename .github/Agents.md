# AGENTS.md — Internship Radar

## Goal
A personal agent that finds current software internships (Finland / Nordics first, but any country works), checks whether the user can actually apply, ranks them against the user's profile, and drafts a tailored application opener. The user approves before anything is sent. Every fact shown must link to the page it came from.

Built for the Junction 2026 Exa challenge. Must work on live queries that a judge types in, so nothing is hard-wired to one person.

## Stack
- Python 3.12
- FastAPI + uvicorn (backend)
- `exa-py` (Exa Python SDK) for search and contents
- Pydantic v2 for all data models
- LLM layer with a provider fallback chain (see "LLM layer"): `anthropic` SDK first, then the `openai` SDK pointed at Gemini and Verda via their OpenAI-compatible endpoints
- Frontend: single static page (`static/index.html`) with vanilla JS, served by FastAPI. No build step.
- Storage: SQLite (`radar.db`) for the cache, saved postings and monitor state. Plain `sqlite3`, no ORM.
- Config via `.env` (see "Environment"). Never commit `.env`.

## Repo layout
```
internship-radar/
  AGENTS.md
  README.md
  .env.example
  pyproject.toml
  app/
    main.py          # FastAPI app, routes
    config.py        # env loading, model names, TTLs, limits
    models.py        # Profile, Posting, MatchResult, Draft
    cache.py         # SQLite cache (get/set with TTL), call counters
    llm.py           # provider chain, complete_json, complete_text
    search.py        # Exa search + contents (cached)
    extract.py       # page text -> structured Posting JSON (cached)
    rank.py          # batch-score postings against profile, flag blockers
    draft.py         # tailored opening paragraph
    store.py         # saved postings, monitor state
    monitor.py       # weekly re-run (stretch)
  static/
    index.html
  tests/
```

## Environment (.env.example)
```
EXA_API_KEY=
ANTHROPIC_API_KEY=
GEMINI_API_KEY=
GEMINI_BASE_URL=
GEMINI_MODEL=
VERDA_API_KEY=
VERDA_BASE_URL=
VERDA_MODEL=
LLM_CHAIN=anthropic,gemini,verda
ANTHROPIC_CHEAP_MODEL=claude-haiku-5-5
ANTHROPIC_STRONG_MODEL=claude-sonnet-5-5
CACHE_ONLY=false
```
Providers with no key set are skipped. Check each provider's current docs for the right base URL and model names.

## Data models (keep these stable)
- `Profile`: role, skills[], location, languages[], work_authorization (free text), extra_notes
- `Posting`: company, title, location, deadline (nullable), requirements[], language_requirement, eligibility_notes, apply_url, source_url, source_snippet
- `MatchResult`: posting, score 0-100, reasons[], blockers[]
- `Draft`: posting_id, text, sources_used[]

## Pipeline
1. **Input**: user submits a `Profile` via the page or `POST /api/radar`.
2. **Search**: build 3-5 natural-language queries from the profile (e.g. "summer 2027 software engineering internship Finland English"). Call Exa search with `num_results` ~10 each, `start_published_date` set to the last ~6 months, and contents with highlights. Deduplicate by domain + title. All Exa calls go through the cache.
3. **Extract**: for each result, turn the page text (highlights or truncated body, not the whole page) into a `Posting` using the cheap model with a strict JSON schema. If a field is not on the page, return null. Never guess a deadline or a language requirement. Cached per URL + content hash.
4. **Rank**: score all `Posting`s against the `Profile` in ONE batched call using the strong model. Add `blockers` for things like Finnish required, citizenship or work-permit limits, or a deadline that has already passed. Sort by score.
5. **Show**: return cards with company, title, deadline, score, reasons, blockers, and a visible source link for every field.
6. **Draft**: `POST /api/draft` for a chosen posting returns a short tailored opener (strong model). Only use facts from the profile and the posting. Show the draft for approval and copy-to-clipboard. Do not send anything automatically.
7. **Monitor (stretch)**: Exa Monitor or a scheduled job re-runs saved profiles weekly and flags new postings.

## Caching (app/cache.py)
- One SQLite table: `cache(key TEXT PRIMARY KEY, kind TEXT, value TEXT, created_at REAL)`. Values are JSON.
- Keys are a SHA-256 of the call's full inputs (query + all Exa parameters, or task + model + prompt input + schema version). Change the schema version when a prompt or schema changes so stale results aren't reused.
- TTLs (in `config.py`): Exa search results 24h, Exa page contents 7 days, LLM extraction 7 days (keyed by URL + content hash), rank and draft 24h.
- Postings go stale (deadlines pass). Always re-check `deadline` against today's date at read time, even for cached results.
- Counters: log every Exa call, LLM call, cache hit and cache miss, with the provider used. Expose them at `GET /api/stats`.
- `CACHE_ONLY=true`: never call Exa or an LLM. Serve cached data or a clear "not cached" message. Use it for offline practice and as a safety net.
- Always show "cached N hours ago" on a result when it came from the cache. Never present cached data as live.

## LLM layer (app/llm.py)
- All LLM calls go through `complete_json(prompt, schema, tier)` and `complete_text(prompt, tier)`, where `tier` is `cheap` or `strong`. No other file imports an LLM SDK.
- Tier use: `cheap` for extraction (most frequent call); `strong` for ranking and drafting.
- Providers are tried in order from `LLM_CHAIN`. Two client classes: `AnthropicClient` (anthropic SDK) and `OpenAICompatClient` (openai SDK with base_url, api_key and model from env). Gemini and Verda both use `OpenAICompatClient`. Fallback providers use their single configured model for both tiers.
- Fall through to the next provider on: credit exhausted, 429, 5xx, timeout, or invalid JSON after one retry (retry once with the validation error in the prompt).
- After a credit-exhausted error, mark that provider "down" for 10 minutes so it isn't retried on every call.
- Validate every JSON response with Pydantic.
- Set a timeout on every call.
- Log which provider answered, and show it in the UI footer.
- If every provider fails, return unranked Exa results with their source links and an "AI ranking unavailable" message. The app must never crash on an LLM failure.

## Cost control
- Budgets: Exa $50 credits, Anthropic ~$20 credits. Treat both as limited.
- Cache first, then call. Never call an API inside a loop without checking the cache.
- Limit queries per run (max 5) and results per query (max ~10). Cap the number of pages extracted per run (e.g. 25).
- Send only highlights or truncated text to the LLM, never full pages.
- Batch ranking into one call.
- Add a simple per-session rate limit on `POST /api/radar` so a judge's repeated clicks can't drain credits.

## Rules for the agent (Copilot) when writing code
- Never commit or push changes. The user handles all commits and pushes.
- Build in small steps. After each step, make sure the app runs before moving on.
- Keep functions small and typed. Use Pydantic models at every boundary.
- Never fabricate data. If extraction fails, return null and keep the `source_url` so the UI still links to the page.
- Every `Posting` must keep its `source_url`. Every claim in the UI links back to a source.
- Handle Exa and LLM errors with clear messages and timeouts.
- No secrets in code or logs.
- Don't hard-code any personal profile. Use a sample profile only in `tests/` and as the form's placeholder.
- Don't add dependencies that aren't listed in the Stack without asking.
- Never call Exa or an LLM SDK directly outside `search.py` and `llm.py`.

## Build order
1. Repo, venv, `pyproject.toml`, `.env.example`, `config.py`, FastAPI hello-world route.
2. `models.py`.
3. `cache.py` (SQLite cache with TTL and counters) + tests.
4. `llm.py` with the provider chain. Test the fallback on purpose by setting a wrong `ANTHROPIC_API_KEY`.
5. `search.py`: takes a `Profile`, returns Exa results through the cache. Test from a script.
6. `extract.py`: raw page -> `Posting`. Test on 5 real URLs.
7. `rank.py` (batched) with blockers.
8. `POST /api/radar` that runs steps 5-7 end to end, plus `GET /api/stats`.
9. `static/index.html`: form + result cards with source links, "cached" labels and provider footer.
10. `draft.py` + `POST /api/draft` + approval UI.
11. README with run instructions and a short demo script.
12. Stretch: `monitor.py`, saved profiles.

## Demo plan
1. Warm the cache: run the demo profile once beforehand (and on each LLM provider once).
2. Run it live on a real profile for a Nordics summer 2027 software internship.
3. Show one card in detail: click each source link to prove the data is real and current.
4. Let a judge type their own role and country and run it live (this hits the APIs, keep a credit buffer).
5. Show the draft and the approve step.
6. Optional: show `/api/stats` (cache hits, provider used) and the fallback working.

## Definition of done
- A judge can enter any role + country and get ranked results with working source links in under ~60 seconds.
- Cached results are labelled as cached; deadlines are re-checked at read time.
- If Anthropic fails, the app falls back to the next provider; if all fail, it still returns Exa results with sources.
- No hard-coded personal data anywhere.
- README lets someone else run it in 5 minutes.