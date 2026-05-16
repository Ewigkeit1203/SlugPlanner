"""
Enrich ucsc_courses.json with RateMyProfessors aggregates via their public GraphQL API.

Notes on blocking / ToS:
- Nobody can guarantee your IP will not be rate-limited or blocked; that is entirely up to RMP.
- This script uses conservative pacing (delay + jitter), caching, session reuse, and backoff on
  HTTP 403/429/503. That reduces risk but does not eliminate it.
- Automated access may conflict with RMP's terms; use at your own discretion (personal/educational).
"""

from __future__ import annotations

import argparse
import json
import os
import random
import re
import time
from typing import Any

import requests

DATA_FILE = "ucsc_courses.json"
RMP_CACHE_FILE = "rmp_cache.json"
GRAPHQL_URL = "https://www.ratemyprofessors.com/graphql"

# GraphQL school id for UC Santa Cruz (matches /search/professors/1078)
UCSC_GRAPHQL_ID = "U2Nob29sLTEwNzg="

# Browser-like headers — bare requests get 403 Forbidden from this endpoint.
HTTP_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json",
    "Content-Type": "application/json",
    "Origin": "https://www.ratemyprofessors.com",
    "Referer": "https://www.ratemyprofessors.com/search/professors/1078",
}

TEACHER_SEARCH_QUERY = """
query TeacherSearchQuery($query: TeacherSearchQuery!) {
  newSearch {
    teachers(query: $query) {
      edges {
        node {
          id
          firstName
          lastName
          avgRating
          avgDifficulty
          wouldTakeAgainPercent
          numRatings
        }
      }
    }
  }
}
"""


def load_json_list(filepath: str) -> list[Any]:
    if not os.path.exists(filepath):
        return []
    with open(filepath, "r", encoding="utf-8") as f:
        data = json.load(f)
    return data if isinstance(data, list) else []


def load_json_dict(filepath: str) -> dict[str, Any]:
    if not os.path.exists(filepath):
        return {}
    with open(filepath, "r", encoding="utf-8") as f:
        data = json.load(f)
    return data if isinstance(data, dict) else {}


def save_json(filepath: str, data: Any) -> None:
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4, ensure_ascii=False)


def extract_instructor_name(content_text: str) -> str | None:
    """
    PISA often formats instructors as:
      Instructor:\\n Dey,P.\\n
    not always on the same line as 'Instructor:'.
    """
    lines = [ln.strip() for ln in content_text.splitlines()]
    for i, line in enumerate(lines):
        if not line.startswith("Instructor"):
            continue
        rest = line.split(":", 1)[-1].strip()
        if rest and "staff" not in rest.lower():
            return rest
        # Name on following line
        if i + 1 < len(lines):
            nxt = lines[i + 1].strip()
            if nxt and not nxt.lower().startswith("location") and "staff" not in nxt.lower():
                return nxt
    return None


def parse_instructor_label(label: str) -> tuple[str, str] | None:
    """Return (last_name, first_initial) from labels like 'Dey,P.' or 'Brummell,N.H.'."""
    label = label.strip()
    if not label:
        return None
    parts = label.split(",", 1)
    last = parts[0].strip()
    tail = parts[1].strip() if len(parts) > 1 else ""
    initial = ""
    for ch in tail:
        if ch.isalpha():
            initial = ch.upper()
            break
    if not last:
        return None
    return last, initial


def score_teacher_match(last: str, initial: str, node: dict[str, Any]) -> int:
    fn = (node.get("firstName") or "").strip()
    ln = (node.get("lastName") or "").strip()
    full = f"{fn} {ln}".lower()
    ll = last.lower()

    s = 0
    ln_l = ln.lower()
    if ln_l == ll:
        s += 100
    elif ll in ln_l:
        s += 75
    elif ll in full:
        s += 55

    if initial and fn and fn[0].upper() == initial:
        s += 25

    return s


def pick_best_teacher(last: str, initial: str, edges: list[dict[str, Any]]) -> dict[str, Any] | None:
    best: dict[str, Any] | None = None
    best_score = -1
    best_ratings = -1

    for edge in edges:
        node = edge.get("node") or {}
        sc = score_teacher_match(last, initial, node)
        if sc < 50:
            continue
        ratings = int(node.get("numRatings") or 0)
        if sc > best_score or (sc == best_score and ratings > best_ratings):
            best = node
            best_score = sc
            best_ratings = ratings

    return best


def graphql_search(session: requests.Session, last_name: str) -> dict[str, Any]:
    payload = {
        "query": TEACHER_SEARCH_QUERY,
        "variables": {"query": {"text": last_name, "schoolID": UCSC_GRAPHQL_ID}},
    }
    delay = 1.5
    last_exc: Exception | None = None

    for attempt in range(5):
        try:
            r = session.post(GRAPHQL_URL, json=payload, headers=HTTP_HEADERS, timeout=25)
            if r.status_code == 200:
                return r.json()

            if r.status_code in (403, 429, 503):
                sleep_s = delay + random.uniform(0, delay * 0.35)
                print(f"   ⚠️ HTTP {r.status_code} — backing off {sleep_s:.1f}s (attempt {attempt + 1}/5)")
                time.sleep(sleep_s)
                delay = min(delay * 2, 60)
                continue

            r.raise_for_status()
        except requests.RequestException as e:
            last_exc = e
            sleep_s = delay + random.uniform(0, delay * 0.35)
            print(f"   ⚠️ Request error — {e} — sleeping {sleep_s:.1f}s")
            time.sleep(sleep_s)
            delay = min(delay * 2, 60)

    raise RuntimeError(f"GraphQL failed after retries: {last_exc}")


def query_rmp_graphql(session: requests.Session, professor_label: str) -> dict[str, Any]:
    parsed = parse_instructor_label(professor_label)
    if not parsed:
        return {"status": "unparsed_name", "raw": professor_label}

    last_name, initial = parsed

    try:
        data = graphql_search(session, last_name)
    except RuntimeError as e:
        return {"status": "api_error", "error": str(e)}

    edges = (
        data.get("data", {}).get("newSearch", {}).get("teachers", {}).get("edges", [])
    )

    if data.get("errors"):
        return {"status": "graphql_errors", "errors": data["errors"]}

    node = pick_best_teacher(last_name, initial, edges)
    if not node:
        return {
            "status": "not_found",
            "searched_last": last_name,
            "initial": initial or None,
        }

    return {
        "status": "ok",
        "rmp_id": node.get("id"),
        "first_name": node.get("firstName"),
        "last_name": node.get("lastName"),
        "avg_rating": node.get("avgRating"),
        "avg_difficulty": node.get("avgDifficulty"),
        "would_take_again_percent": node.get("wouldTakeAgainPercent"),
        "num_ratings": node.get("numRatings"),
    }


def polite_sleep(delay_min: float, delay_max: float) -> None:
    time.sleep(random.uniform(delay_min, delay_max))


def enrich_courses_with_rmp(
    *,
    delay_min: float,
    delay_max: float,
    checkpoint_every: int,
    limit_courses: int | None = None,
) -> None:
    courses = load_json_list(DATA_FILE)
    rmp_cache: dict[str, Any] = load_json_dict(RMP_CACHE_FILE)

    if not courses:
        print(f"❌ {DATA_FILE} missing or empty — run my_ucsc_scanner.py first.")
        return

    total = len(courses)
    end_idx = total if limit_courses is None else min(limit_courses, total)
    if limit_courses is not None:
        print(f"⚠️ --limit: enriching indices 0..{end_idx - 1} only ({end_idx} rows); file still has {total} total.")

    session = requests.Session()

    print(f"🧬 {len(courses)} courses — unique instructor lookups are cached in {RMP_CACHE_FILE}")
    print(f"   Delay between live API calls: {delay_min:.1f}–{delay_max:.1f}s (jitter)")
    updated_count = 0

    for idx, course in enumerate(courses):
        if idx >= end_idx:
            break
        prof_label = extract_instructor_name(course.get("content", ""))

        if not prof_label:
            course["rmp_data"] = {"status": "staff_or_unknown"}
            continue

        if prof_label in rmp_cache:
            course["rmp_data"] = rmp_cache[prof_label]
            continue

        print(f"🔍 [{idx + 1}/{len(courses)}] RMP lookup: {prof_label}")
        metrics = query_rmp_graphql(session, prof_label)
        rmp_cache[prof_label] = metrics
        course["rmp_data"] = metrics
        updated_count += 1

        if updated_count % checkpoint_every == 0:
            save_json(DATA_FILE, courses)
            save_json(RMP_CACHE_FILE, rmp_cache)
            print(f"   💾 checkpoint ({updated_count} new lookups)")

        polite_sleep(delay_min, delay_max)

    save_json(DATA_FILE, courses)
    save_json(RMP_CACHE_FILE, rmp_cache)
    print(f"\n🎉 Finished — wrote RMP fields into {DATA_FILE} (and cache {RMP_CACHE_FILE}).")


def main() -> None:
    parser = argparse.ArgumentParser(description="Add RateMyProfessors stats to ucsc_courses.json")
    parser.add_argument(
        "--delay-min",
        type=float,
        default=1.25,
        help="Minimum seconds between uncached API calls (default: 1.25)",
    )
    parser.add_argument(
        "--delay-max",
        type=float,
        default=2.75,
        help="Maximum seconds between uncached API calls (default: 2.75)",
    )
    parser.add_argument(
        "--checkpoint-every",
        type=int,
        default=5,
        help="Save JSON after this many new lookups (default: 5)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        metavar="N",
        help="Only process the first N courses (useful for testing)",
    )
    args = parser.parse_args()

    if args.delay_min > args.delay_max:
        parser.error("--delay-min must be <= --delay-max")

    enrich_courses_with_rmp(
        delay_min=args.delay_min,
        delay_max=args.delay_max,
        checkpoint_every=max(1, args.checkpoint_every),
        limit_courses=args.limit,
    )


if __name__ == "__main__":
    main()
