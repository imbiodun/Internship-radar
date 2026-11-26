## REST API Performance Testing and Automation

To evaluate the reliability and scalability of the application, I developed an automated REST API performance-testing framework using Python, Locust, and Bash.

The investigation involved increasing concurrent user workloads, analysing backend failures, monitoring Linux system resources, implementing corrective changes, and benchmarking performance improvements while preserving existing functionality through regression testing.
## Objectives

- Validate REST API response correctness under concurrent workloads.
- Measure response latency, throughput and request failure rates.
- Investigate application behaviour under increasing load.
- Identify backend and operating system resource limitations.
- Evaluate performance improvements following targeted optimisations.
- Enable reproducible benchmark execution.

## Project structure

```text
performance_tests/
├── locustfile.py
├── seed_database.py
├── run_benchmarks.sh
└── README.md
```

| File | Description |
|---|---|
| locustfile.py | Virtual user behaviour and automated response validation |
| seed_database.py | Reproducible synthetic database generation |
| run_benchmarks.sh | Automated execution of benchmark scenarios |
| README.md | Testing methodology and execution instructions |

## Endpoints under test

| HTTP method | Endpoint | Functionality |
|---|---|---|
| GET | /api/progress | Retrieves application progress information |
| GET | /api/postings | Retrieves saved internship postings |
| GET | /api/stats | Retrieves application statistics and cache counters |

These endpoints were selected because they represent different processing workloads, including in-memory operations, database queries and JSON serialization.

External search and LLM endpoints are excluded from this benchmark suite to avoid API costs and external service variability.

## Response validation

The Locust implementation validates more than HTTP status codes.

Each endpoint is checked for:

- HTTP 200 responses.
- Valid JSON response bodies.
- Expected JSON object structure.
- Required response fields and their expected data types.

The statistics endpoint also verifies that cache-only mode is enabled.

A request is marked as failed when its response does not satisfy the configured validation requirements.

Negative testing was performed by deliberately introducing an incorrect expected field type and verifying that Locust detected the response validation failure despite receiving HTTP 200.

## Setup

From the project root, create and activate a Python virtual environment:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e .
python -m pip install locust
```

The original experiments were conducted on Ubuntu using Python 3.14.

## Generate synthetic test data

```bash
python -m performance_tests.seed_database --count 100
```

The data generation utility uses:

- Deterministic synthetic posting identifiers.
- Seeded random match scores.
- Generic candidate profiles.
- Synthetic company names and posting URLs.
- A separate performance.db database.

The generator uses a fixed random seed to support reproducibility.

Running the generator with the same record count does not create duplicate posting identifiers. However, generating a smaller dataset does not automatically remove previously generated records.

The application's primary radar.db database is not used for performance testing.

## Start the backend

For high-concurrency experiments, configure the server's soft file descriptor limit before launching Uvicorn:

```bash
ulimit -Sn 4096
```

This assumes the shell's hard limit permits the requested value.

Start the backend:

```bash
CACHE_ONLY=true CACHE_DB_PATH=performance.db \
python -m uvicorn app.main:app \
    --host 127.0.0.1 \
    --port 8000
```

Automatic reload is disabled during benchmarking to avoid introducing unnecessary process-management overhead.

## Smoke testing

Before executing larger workloads, verify that the server and test implementation are functioning correctly:

```bash
locust -f performance_tests/locustfile.py \
    --host http://127.0.0.1:8000 \
    --headless \
    --users 1 \
    --spawn-rate 1 \
    --run-time 30s
```

The smoke test checks connectivity, endpoint availability and response validation.

## Benchmark scenarios

| Virtual users | Spawn rate | Duration |
|---:|---:|---:|
| 10 | 5/s | 60 seconds |
| 50 | 10/s | 60 seconds |
| 100 | 20/s | 60 seconds |
| 250 | 25/s | 120 seconds |
| 500 | 50/s | 120 seconds |
| 1,000 | 100/s | 120 seconds |

Virtual users execute equally weighted endpoint tasks with a randomized wait time of one to three seconds between tasks.

Virtual users represent simulated active clients rather than an equivalent number of simultaneous HTTP requests.

## Run an individual benchmark

```bash
mkdir -p benchmarks/manual

locust -f performance_tests/locustfile.py \
    --host http://127.0.0.1:8000 \
    --headless \
    --users 500 \
    --spawn-rate 50 \
    --run-time 120s \
    --csv benchmarks/manual/users_500 \
    --html benchmarks/manual/users_500.html
```

Use unique output paths when repeating experiments to avoid overwriting previous benchmark results.

## Automated benchmark execution

The Bash runner automates the execution of all configured workload scenarios.

```bash
chmod +x performance_tests/run_benchmarks.sh
./performance_tests/run_benchmarks.sh
```

By default, benchmark reports are saved to a timestamped directory inside benchmarks/.

A custom output directory can also be specified:

```bash
./performance_tests/run_benchmarks.sh benchmarks/custom_run
```

The runner uses a fail-fast approach and stops if a benchmark command returns a non-zero exit status.

## Performance metrics

| Metric | Description |
|---|---|
| Request count | Total recorded HTTP requests |
| Failure rate | Percentage of requests marked as failed |
| Average latency | Mean recorded response time |
| P50 | Median response time |
| P95 | Response time at or below which approximately 95% of requests completed |
| P99 | Response time at or below which approximately 99% of requests completed |
| RPS | Recorded requests per second |

Locust generates CSV statistics, request failure reports, task exception reports, statistics history and HTML reports.

## Linux resource monitoring

Identify the running Uvicorn process:

```bash
pgrep -af uvicorn
```

Replace PID with the actual server process ID in the following commands.

Inspect the process's file descriptor limit:

```bash
grep "Max open files" /proc/PID/limits
```

Count open database descriptors:

```bash
ls -l /proc/PID/fd | grep 'performance.db' | wc -l
```

Monitor resource consumption during benchmark execution:

```bash
watch -n 0.5 '
echo "Total descriptors:"
ls /proc/PID/fd | wc -l

echo "Database descriptors:"
ls -l /proc/PID/fd | grep "performance.db" | wc -l

echo "Network sockets:"
ls -l /proc/PID/fd | grep "socket:" | wc -l
'
```

The process ID must be updated whenever the server is restarted.

Press Ctrl+C to stop monitoring.

## Functional regression testing

Run the existing application test suite after backend modifications:

```bash
python -m unittest discover -s tests -v
```

Regression testing helps ensure that performance optimisations do not break functionality covered by existing automated tests.

## Experimental limitations

- The backend and load generator operate on the same machine.
- The benchmark dataset contains 100 synthetic postings.
- Only three read-only REST API endpoints are included.
- External API performance is not evaluated.
- Benchmark results are based on individual experimental runs.
- Resource monitoring was performed using periodic process snapshots.
- Results should not be interpreted as production capacity guarantees.

See [Benchmark Results](../benchmarks/README.md) for the experimental findings and optimisation investigation.