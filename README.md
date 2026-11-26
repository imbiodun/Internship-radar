# Internship Radar

Internship Radar is an independently developed application that finds software internships, evaluates them against candidate profiles, ranks relevant opportunities, and generates tailored application drafts for user approval.

The project was initiated during Junction 2026, inspired by the Exa challenge, and developed independently beyond the hackathon.

The application combines REST API development, external API integration, LLM orchestration, SQLite caching, automated testing, and performance engineering.

The backend has been evaluated through automated load and stress testing with up to 1,000 concurrent virtual users, resulting in measurable improvements in reliability, resource management, response latency, and request throughput.

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

List, save, or delete postings:

```bash
curl http://127.0.0.1:8000/api/postings
curl -X DELETE http://127.0.0.1:8000/api/postings/<posting-id>
```

## Tests

```bash
.venv/bin/python -m unittest discover -s tests -v
```

## Performance Testing and Automation

As an extension, the application was evaluated and optimised through automated REST API load and stress testing using Python and Locust.

The project investigates application scalability, response correctness, resource management and performance bottlenecks under increasing concurrent user workloads.

### Technologies

- Python
- Locust
- FastAPI
- SQLite
- Bash scripting
- Linux process monitoring
- Python unittest
- Git

### Testing capabilities

- Automated HTTP response and JSON structure validation.
- Reproducible synthetic test data generation.
- Load and stress testing with up to 1,000 concurrent virtual users.
- Automated benchmark execution using Bash.
- CSV and HTML performance reporting.
- Functional regression testing following backend modifications.
- Linux file descriptor and network socket monitoring.

### Key results

| Metric | Before | After |
|---|---:|---:|
| Retained database file descriptors | 329 | 0 |
| Failed requests at 500 virtual users | 494 | 0 |
| Failed requests at 1,000 virtual users | 799 | 0 |
| Redundant MatchResult validation calls per posting | 4 | 1 |

Following database resource-management improvements and Linux resource-limit configuration, an additional JSON validation optimisation produced the following observed benchmark results:

| Performance metric | 500 users | 1,000 users |
|---|---:|---:|
| Average latency reduction | 24.04% | 46.29% |
| P95 latency reduction | 21.88% | 73.81% |
| Throughput increase | 14.36% | 65.36% |
| Post-optimisation failure rate | 0% | 0% |

All executed functional regression tests passed following the backend modifications.

These results represent individual local benchmark experiments using 100 synthetic internship postings. They do not establish production capacity or guarantee equivalent improvements in other environments.

### Documentation and reproducibility

- [Performance testing methodology and execution guide](performance_tests/README.md)
- [Benchmark results and technical investigation](benchmarks/README.md)
- [Locust test implementation](performance_tests/locustfile.py)
- [Synthetic data generator](performance_tests/seed_database.py)
- [Automated benchmark runner](performance_tests/run_benchmarks.sh)

## Safety and cost controls

- Exa and LLM results are cached in `radar.db`.
- Exa search calls are limited to five queries and ten results per query.
- Page extraction is capped per run.
- Ranking is batched into one LLM call.
- Cached data is labelled as cached.
- AI-generated drafts are shown for approval and are never sent automatically.
