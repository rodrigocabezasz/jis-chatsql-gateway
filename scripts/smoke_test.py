#!/usr/bin/env python3
import json
import os
import requests

BASE_URL = os.getenv("BASE_URL", "http://127.0.0.1:8093")


def main() -> int:
    health = requests.get(f"{BASE_URL}/health", timeout=10)
    print("/health", health.status_code)
    print(json.dumps(health.json(), indent=2, ensure_ascii=True))

    payload = {
        "request_id": "REQ-SMOKE-0001",
        "caller": "local-smoke",
        "sql": "SELECT 1 AS ok, DATABASE() AS db",
    }
    q = requests.post(f"{BASE_URL}/query", json=payload, timeout=20)
    print("/query", q.status_code)
    print(json.dumps(q.json(), indent=2, ensure_ascii=True))

    return 0 if q.status_code == 200 else 1


if __name__ == "__main__":
    raise SystemExit(main())
