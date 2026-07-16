"""Load testing script for DocTrace AI.

Run with: python scripts/load_test.py --host http://localhost:8000 --users 50 --duration 60

Requires: pip install k6  (or install k6 binary)
"""

import argparse
import json
import subprocess
import sys
from pathlib import Path


K6_SCRIPT = """
import http from 'k6/http';
import { check, sleep } from 'k6';
import { Rate } from 'k6/metrics';

const errorRate = new Rate('errors');

export const options = {
  stages: [
    { duration: '30s', target: __ENV.TARGET_USERS || 10 },
    { duration: '1m', target: __ENV.TARGET_USERS || 10 },
    { duration: '30s', target: 0 },
  ],
  thresholds: {
    http_req_duration: ['p(95)<500'],
    errors: ['rate<0.05'],
  },
};

const BASE_URL = __ENV.HOST || 'http://localhost:8000';
const API_PREFIX = '/api/v1';

function getHeaders() {
  return {
    'Content-Type': 'application/json',
    'X-Request-ID': `load-test-${Math.random().toString(36).substring(7)}`,
  };
}

export default function () {
  // Health checks
  const healthRes = http.get(`${BASE_URL}/health`, { headers: getHeaders() });
  check(healthRes, { 'health status 200': (r) => r.status === 200 }) || errorRate.add(1);

  const readyRes = http.get(`${BASE_URL}/health/ready`, { headers: getHeaders() });
  check(readyRes, { 'ready status 200': (r) => r.status === 200 }) || errorRate.add(1);

  // List documents
  const docsRes = http.get(`${BASE_URL}${API_PREFIX}/documents`, { headers: getHeaders() });
  check(docsRes, { 'list docs 200': (r) => r.status === 200 }) || errorRate.add(1);

  sleep(1);
}
"""


def generate_k6_script(output_path: Path, host: str, users: int, duration: int) -> None:
    """Generate k6 load test script."""
    script = K6_SCRIPT.replace(
        "__ENV.TARGET_USERS || 10",
        str(users),
    ).replace(
        "__ENV.HOST || 'http://localhost:8000'",
        f"'{host}'",
    )
    output_path.write_text(script)
    print(f"Generated k6 script at {output_path}")


def run_k6_test(script_path: Path, host: str, users: int, duration: int) -> int:
    """Run k6 load test."""
    env = {
        "HOST": host,
        "TARGET_USERS": str(users),
    }
    result = subprocess.run(
        ["k6", "run", "--vus", str(users), "--duration", f"{duration}s", str(script_path)],
        env=env,
        capture_output=True,
        text=True,
    )
    print(result.stdout)
    if result.stderr:
        print(result.stderr, file=sys.stderr)
    return result.returncode


def main() -> None:
    parser = argparse.ArgumentParser(description="Run load tests against DocTrace AI")
    parser.add_argument("--host", default="http://localhost:8000", help="Target host URL")
    parser.add_argument("--users", type=int, default=50, help="Number of virtual users")
    parser.add_argument("--duration", type=int, default=60, help="Test duration in seconds")
    parser.add_argument("--output", default="k6-load-test.js", help="Output script path")
    args = parser.parse_args()

    script_path = Path(args.output)
    generate_k6_script(script_path, args.host, args.users, args.duration)

    print(f"\nRunning load test: {args.users} users for {args.duration}s against {args.host}")
    return run_k6_test(script_path, args.host, args.users, args.duration)


if __name__ == "__main__":
    sys.exit(main())