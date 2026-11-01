#!/usr/bin/env python3
"""Evaluate retrieval against manually labelled fact IDs using only the local PLAMA API."""
import argparse
import json
import statistics
import time
import urllib.request
from pathlib import Path

def search(base: str, query: str, k: int):
    body = json.dumps({"query": query, "n_results": k}).encode("utf-8")
    req = urllib.request.Request(
        base.rstrip("/") + "/api/memory/search",
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=30) as response:
        return json.load(response)["facts"]

def evaluate(cases, base: str, k: int):
    recalls = []
    reciprocal_ranks = []
    abstention_hits = []
    timings = []
    failures = []
    for i, case in enumerate(cases):
        start = time.perf_counter()
        facts = search(base, case["query"], k)
        timings.append((time.perf_counter() - start) * 1000)
        actual = [fact["id"] for fact in facts]
        expected = set(case.get("expected_fact_ids", []))
        if case.get("unanswerable"):
            abstention_hits.append(not actual)
            continue
        if not expected:
            raise ValueError(f"Case {i} requires expected_fact_ids or unanswerable=true")
        hits = expected & set(actual)
        recalls.append(len(hits) / len(expected))
        first = min((actual.index(hit) + 1 for hit in hits), default=None)
        reciprocal_ranks.append(1 / first if first else 0.0)
        if not hits:
            failures.append({"case": i, "query": case["query"], "expected": sorted(expected), "retrieved": actual})
    result = {
        "cases": len(cases),
        "recall_at_k": (statistics.mean(recalls) if recalls else None),
        "mrr_at_k": (statistics.mean(reciprocal_ranks) if reciprocal_ranks else None),
        "unanswerable_empty_rate": (statistics.mean(abstention_hits) if abstention_hits else None),
        "latency_ms_median": (statistics.median(timings) if timings else None),
        "failures": failures,
    }
    return result

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cases", type=Path, help="JSON list of labelled retrieval questions")
    ap.add_argument("--api", default="http://127.0.0.1:8000")
    ap.add_argument("-k", type=int, default=5)
    args = ap.parse_args()
    cases = json.loads(args.cases.read_text(encoding="utf-8"))
    if not isinstance(cases, list) or args.k < 1:
        ap.error("expected a JSON array of cases and -k >= 1")
    print(json.dumps(evaluate(cases, args.api, args.k), ensure_ascii=False, indent=2))

if __name__ == "__main__":
    main()
