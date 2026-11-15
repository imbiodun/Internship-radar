# AGENTS.md — Internship Radar

## Goal
A personal agent that finds current software internships (Finland / Nordics first, but any country works), checks whether the user can actually apply, ranks them against the user's profile, and drafts a tailored application opener. The user approves before anything is sent. Every fact shown must link to the page it came from.

Built for the Junction 2026 Exa challenge. Must work on live queries that a judge types in, so nothing is hard-wired to one person.

## Stack
- Python 3.12
- FastAPI + uvicorn (backend)
- `exa-py` (Exa Python SDK) for search and contents
- Pydantic v2 for all data models
- An LLM for ranking and drafting (Anthropic SDK, `claude-sonnet-4-5` or newer, key in env)
- Frontend: single static page (`static/index.html`) with vanilla JS, served by FastAPI. No build step.
- Storage: SQLite (`radar.db`) for saved postings and monitor state. No ORM, plain `sqlite3`.
- Config via `.env` (`EXA_API_KEY`, `ANTHROPIC_API_KEY`). Never commit `.env`.

## Repo layout
```
internship-radar/
  AGENTS.md
  README.md
  .env.example
  pyproject.toml
  app/
    main.py          # FastAPI app, routes
    models.py        # Profile, Posting, MatchResult, Draft
    search.py        # Exa search + contents calls
    extract.py       # page text -> structured Posting JSON
    rank.py          # score postings against profile, flag blockers
    draft.py         # tailored opening paragraph
    store.py         # SQLite helpers
    monitor.py       # weekly re-run (stretch)
  static/
    index.html
  tests/
```

## Data models (keep these stable)
- `Profile`: role, skills[], location, languages[], work_authorization (free text), extra_notes
- `Posting`: company, title, location, deadline (nullable), requirements[], language_requirement, eligibility_notes, apply_url, source_url, source_snippet
- `MatchResult`: posting, score 0-100, reasons[], blockers[]
- `Draft`: posting_id, text, sources_used[]

## Pipeline
1. **Input**: user submits a `Profile` via the page or `POST /api/radar`.
2. **Search**: build 3-5 natural-language queries from the profile (e.g. "summer 2027 software engineering internship Finland English"). Call Exa search with `use_autoprompt`/neural mode, `num_results` ~10 each, `start_published_date` set to the last ~6 months, and `include_text` or contents with highlights. Deduplicate by domain + title.
3. **Extract**: for each result, fetch contents and turn the page text into a `Posting` using the LLM with a strict JSON schema. If a field is not on the page, return null. Never guess a deadline or a language requirement.
4. **Rank**: score each `Posting` against the `Profile`. Add `blockers` for things like Finnish required, citizenship or work-permit limits, or a deadline that has already passed. Sort by score.
5. **Show**: return cards with company, title, deadline, score, reasons, blockers, and a visible source link for every field.
6. **Draft**: `POST /api/draft` for a chosen posting returns a short tailored opener. Only use facts from the profile and the posting. Show the draft for approval and copy-to-clipboard. Do not send anything automatically.
7. **Monitor (stretch)**: Exa Monitor or a scheduled job re-runs saved profiles weekly and flags new postings.

## Rules for the agent (Copilot) when writing code
- Never commit or push changes. The user handles all commits and pushes.
- Build in small steps. After each step, make sure the app runs before moving on.
- Keep functions small and typed. Use Pydantic models at every boundary.
- Never fabricate data. If extraction fails, return null and keep the `source_url` so the UI still links to the page.
- Every `Posting` must keep its `source_url`. Every claim in the UI links back to a source.
- Handle Exa and LLM errors with clear messages and timeouts. Cache Exa results in SQLite during development to save credits (the budget is $50).
- No secrets in code or logs.
- Don't hard-code any personal profile. Use a sample profile only in `tests/` and as the form's placeholder.
- Don't add dependencies that aren't listed in the Stack without asking.

## Build order
1. Repo, venv, `pyproject.toml`, `.env.example`, FastAPI hello-world route.
2. `models.py`.
3. `search.py`: one function that takes a `Profile` and returns raw Exa results. Test it from a script.
4. `extract.py`: raw page -> `Posting`. Test on 5 real URLs.
5. `rank.py` with blockers.
6. `POST /api/radar` that runs steps 3-5 end to end.
7. `static/index.html`: form + result cards with source links.
8. `draft.py` + `POST /api/draft` + approval UI.
9. README with run instructions and a short demo script.
10. Stretch: `monitor.py`, SQLite persistence of saved results.

## Demo plan
1. Run it live on a real profile for a Nordics summer 2027 software internship.
2. Show one card in detail: click each source link to prove the data is real and current.
3. Let a judge type their own role and country and run it live.
4. Show the draft and the approve step.

## Definition of done
- A judge can enter any role + country and get ranked results with working source links in under ~60 seconds.
- No hard-coded personal data anywhere.
- README lets someone else run it in 5 minutes.