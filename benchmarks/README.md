# Performance Benchmarks and Technical Investigation

## Executive Summary

Internship Radar was evaluated through automated REST API load and stress testing with workloads of up to 1,000 concurrent virtual users.

The investigation identified database connection resource retention, Linux file descriptor exhaustion and redundant JSON validation.

Targeted application and operating system changes eliminated observed request failures at 500 and 1,000 virtual users. Subsequent JSON validation optimisation improved measured latency and throughput while preserving the functionality covered by existing regression tests.

## 1. Experimental Environment

| Parameter | Configuration |
|---|---|
| Operating system | Ubuntu Linux |
| Programming language | Python 3.14 |
| Backend | FastAPI/Uvicorn |
| Database | SQLite |
| Testing framework | Locust |
| Dataset | 100 synthetic postings |
| Database file | performance.db |
| External API calls | Disabled for benchmark workloads |
| Wait time | 1–3 seconds |
| Execution environment | Local machine |

Three REST API endpoints were tested:

- GET /api/progress
- GET /api/postings
- GET /api/stats

## 2. Initial Smoke Test and Troubleshooting

The initial Locust implementation encountered an InvalidURL exception because endpoint paths were missing their leading forward slash.

Incorrect:

```python
self.client.get("api/stats")
```

Correct:

```python
self.client.get("/api/stats")
```

The incorrect path produced a malformed URL when combined with the configured host.

Following the correction, the initial smoke test recorded 15 requests with zero request failures.

Additional response validation was introduced to detect invalid JSON structures and unexpected field types.

## 3. Initial Load Testing

The original backend implementation was tested under increasing concurrent user workloads.

| Virtual users | Requests | Failures | Average latency | P95 latency | RPS |
|---:|---:|---:|---:|---:|---:|
| 10 | 299 | 0 | 8.09 ms | 21 ms | 5.06 |
| 50 | 1,445 | 0 | 26.58 ms | 110 ms | 24.45 |
| 100 | 2,897 | 0 | 15.30 ms | 48 ms | 48.98 |
| 500 | 14,436 | 494 | 1,966.71 ms | 3,600 ms | 121.17 |

Throughput scaled approximately proportionally between 10 and 100 virtual users.

At 500 virtual users, latency increased substantially and request failures appeared.

The 50-user experiment recorded higher latency than the 100-user experiment, demonstrating measurement variability and the importance of repeated benchmarking.

## 4. Investigation: Database Connection Resource Retention

### Observed failures

The 500-user experiment recorded:

| Endpoint | HTTP 500 | Status 0 | Total failures |
|---|---:|---:|---:|
| /api/postings | 182 | 38 | 220 |
| /api/progress | 0 | 29 | 29 |
| /api/stats | 217 | 28 | 245 |
| Total | 399 | 95 | 494 |

The database-backed endpoints returned HTTP 500 responses, while the in-memory progress endpoint did not record HTTP 500 failures.

Status 0 represents a request for which Locust did not receive a valid HTTP status response. The original custom validator did not preserve the underlying transport error details.

### Server-side exception

FastAPI tracebacks identified the following exception:

```text
sqlite3.OperationalError: unable to open database file
```

The exception occurred during SQLite connection creation.

### Resource investigation

Linux process monitoring identified the following:

| Resource | Observed value |
|---|---:|
| Soft file descriptor limit | 1,024 |
| Previously observed total descriptors | 343 |
| Retained database descriptors | 329 |
| Network socket descriptors | 3 |

The large number of retained database descriptors suggested that connections were not being promptly released.

### Connection lifecycle problem

The original implementation returned a SQLite connection directly:

```python
def _connect(self) -> sqlite3.Connection:
    connection = sqlite3.connect(self.path)
    connection.row_factory = sqlite3.Row
    return connection
```

Although SQLite's connection context manager handles transaction commits and rollbacks, it does not explicitly close the connection upon exiting the context.

Connection cleanup was therefore dependent on the lifetime of the connection object.

### Corrective implementation

A custom context manager was introduced in store.py and cache.py:

```python
from contextlib import contextmanager
from collections.abc import Generator

@contextmanager
def _connect(self) -> Generator[sqlite3.Connection, None, None]:
    connection = sqlite3.connect(self.path)

    try:
        connection.row_factory = sqlite3.Row

        with connection:
            yield connection

    finally:
        connection.close()
```

This implementation preserves transaction handling while guaranteeing explicit connection closure when leaving the context.

### Verification at 500 virtual users

| Metric | Before | After |
|---|---:|---:|
| Total requests | 14,436 | 14,418 |
| Failed requests | 494 | 0 |
| Failure rate | 3.42% | 0% |
| Average latency | 1,966.71 ms | 1,975.82 ms |
| P95 latency | 3,600 ms | 3,000 ms |
| P99 latency | 4,200 ms | 3,400 ms |
| Throughput | 121.17 RPS | 120.77 RPS |
| Retained database descriptors | 329 | 0 |

The intervention improved observed resource management and reliability. Average latency and throughput remained approximately unchanged.

## 5. Investigation: Linux File Descriptor Exhaustion

After the connection-management correction, the 1,000-user workload continued to produce SQLite connection-opening failures.

Process monitoring confirmed that the server repeatedly reached its soft file descriptor limit.

An observed resource snapshot showed:

| Resource | Count |
|---|---:|
| Total descriptors | 1,024 |
| Network sockets | 973 |
| Database descriptors | 40 |

Network connections were the dominant contributor to descriptor consumption.

### Configuration troubleshooting

The initial attempt to increase the resource limit did not resolve the failures because the command was executed in a separate terminal from the server.

Linux resource limits are process-specific and inherited by child processes.

The corrected procedure was to configure the soft limit in the server's shell before launching Uvicorn:

```bash
ulimit -Sn 4096
```

The actual running process should be verified using:

```bash
grep "Max open files" /proc/PID/limits
```

After applying the configuration correctly, process monitoring recorded:

| Resource | Count |
|---|---:|
| Total descriptors | 1,054 |
| Network sockets | 1,003 |
| Database descriptors | 40 |

The server successfully exceeded its previous descriptor ceiling.

### Verification at 1,000 virtual users

| Metric | Original limit | Increased limit |
|---|---:|---:|
| Total requests | 11,484 | 8,491 |
| Failed requests | 799 | 0 |
| Failure rate | 6.96% | 0% |
| Average latency | 7,101 ms | 11,263 ms |
| P95 latency | 15,000 ms | 42,000 ms |
| P99 latency | 17,000 ms | 47,000 ms |
| Throughput | 95.48 RPS | 70.94 RPS |

The resource-limit adjustment eliminated observed request failures but did not improve response latency.

This demonstrates that resolving resource exhaustion does not necessarily resolve processing bottlenecks.

## 6. Optimisation: Redundant JSON Validation

Source code inspection identified repeated Pydantic JSON validation inside Store.list_saved().

The same MatchResult JSON object was validated separately to retrieve posting, score, reasons and blockers.

### Original approach

```python
posting = MatchResult.model_validate_json(row["match_json"]).posting
score = MatchResult.model_validate_json(row["match_json"]).score
reasons = MatchResult.model_validate_json(row["match_json"]).reasons
blockers = MatchResult.model_validate_json(row["match_json"]).blockers
```

### Optimised approach

```python
match = MatchResult.model_validate_json(row["match_json"])

posting = match.posting
score = match.score
reasons = match.reasons
blockers = match.blockers
```

The optimised implementation validates the MatchResult once per posting and reuses the resulting object.

For a dataset containing 100 postings, this reduces MatchResult validation calls from 400 to 100 per complete postings request.

This represents a 75% reduction in MatchResult validation calls. The asymptotic complexity of the model construction loop remains O(n), but unnecessary repeated processing is eliminated.

## 7. Optimisation Results

The following experiments were conducted after implementing explicit database connection cleanup and increasing the server's file descriptor limit.

### 500 virtual users

| Metric | Before | After | Improvement |
|---|---:|---:|---:|
| Requests | 13,880 | 15,853 | +14.21% |
| Failed requests | 0 | 0 | Maintained |
| Average latency | 2,130.77 ms | 1,618.44 ms | 24.04% |
| P95 latency | 3,200 ms | 2,500 ms | 21.88% |
| P99 latency | 3,700 ms | 3,000 ms | 18.92% |
| Throughput | 116.23 RPS | 132.92 RPS | 14.36% |

### 1,000 virtual users

| Metric | Before | After | Improvement |
|---|---:|---:|---:|
| Requests | 8,491 | 14,038 | +65.33% |
| Failed requests | 0 | 0 | Maintained |
| Average latency | 11,263 ms | 6,049 ms | 46.29% |
| P95 latency | 42,000 ms | 11,000 ms | 73.81% |
| P99 latency | 47,000 ms | 30,000 ms | 36.17% |
| Throughput | 70.94 RPS | 117.30 RPS | 65.36% |

### Endpoint-specific average latency

| Endpoint | 500-user improvement | 1,000-user improvement |
|---|---:|---:|
| /api/postings | 18.59% | 40.85% |
| /api/progress | 26.08% | 47.80% |
| /api/stats | 26.34% | 48.57% |

Although only the postings retrieval implementation was directly optimised, all three endpoints recorded improved average latency.

Reduced contention for shared processing resources is a possible explanation, but additional profiling would be required to verify the mechanism.

The postings endpoint's P99 latency increased from 27 to 29 seconds in the 1,000-user experiment, despite improvements in aggregate performance metrics.

## 8. Regression Testing

The existing automated functional test suite was executed following the backend modifications.

All executed tests passed.

This provides evidence that the optimisations preserved functionality covered by the existing test suite.

## 9. Benchmark Organisation

| Directory | Purpose |
|---|---|
| baseline/ | Original backend measurements |
| connection_fix/ | Measurements after explicit SQLite connection cleanup |
| fd_limit_4096/ | Measurements after server resource-limit adjustment |
| pre_json_optimisation/ | Reference measurements before JSON optimisation |
| json_optimisation/ | Final optimised backend measurements |

Available CSV and HTML reports provide supporting experimental evidence.

## 10. Key Engineering Outcomes

- Developed automated REST API load and stress testing.
- Implemented reproducible synthetic test data generation.
- Introduced automated response correctness validation.
- Diagnosed backend failures using Python tracebacks.
- Investigated Linux process resource consumption.
- Implemented deterministic SQLite connection management.
- Identified and resolved server file descriptor exhaustion.
- Eliminated redundant JSON validation.
- Automated benchmark execution using Bash.
- Verified existing functionality through regression testing.

## 11. Limitations and Future Work

The experiments were conducted locally, with the backend and load generator sharing computing resources.

The measurements represent individual experimental runs rather than statistically controlled repeated trials. The 1,000-user pre-optimisation reference was collected during an earlier experiment.

Some original generated reports may be unavailable because subsequent experiments reused output filenames.

Despite the observed improvements, absolute response latency remains high at larger workloads.

Potential future work includes:

- Repeated benchmark trials and statistical analysis.
- CPU and memory profiling.
- Testing larger database datasets.
- Pagination of saved postings.
- Database connection pooling.
- Distributed load generation.
- Automated performance regression thresholds.
- CI/CD integration.

## Conclusion

The investigation demonstrates how automated performance testing can identify application defects, operating system resource limitations and unnecessary backend processing.

By combining load testing, exception analysis, Linux resource monitoring, targeted code modifications and regression testing, the application achieved measurable improvements in observed reliability and performance.