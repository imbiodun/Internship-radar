#!/usr/bin/env bash

set -euo pipefail

HOST="${HOST:-http://127.0.0.1:8000}"
OUTPUT_DIR="${1:-benchmarks/run_$(date +%Y%m%d_%H%M%S)}"

mkdir -p "$OUTPUT_DIR"

run_benchmark() {
    local users="$1"
    local spawn_rate="$2"
    local duration="$3"

    echo "Running benchmark with $users virtual users"

    locust -f performance_tests/locustfile.py \
        --host "$HOST" \
        --headless \
        --users "$users" \
        --spawn-rate "$spawn_rate" \
        --run-time "$duration" \
        --csv "$OUTPUT_DIR/users_$users" \
        --html "$OUTPUT_DIR/users_$users.html"

    echo "Completed benchmark with $users virtual users"
}

run_benchmark 10 5 60s
run_benchmark 50 10 60s
run_benchmark 100 20 60s
run_benchmark 250 25 120s
run_benchmark 500 50 120s
run_benchmark 1000 100 120s

echo "All benchmarks completed."
echo "Results saved to: $OUTPUT_DIR"