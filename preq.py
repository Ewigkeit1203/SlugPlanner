"""
Fetch Enrollment Requirements (prerequisites text) for each section in ucsc_courses.json.

Run after my_ucsc_scanner.py. Your JSON must include `detail_url` on each entry (current scanner).
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from playwright.sync_api import Browser, sync_playwright

INPUT_DEFAULT = "ucsc_courses.json"
OUTPUT_DEFAULT = "ucsc_courses_with_preq.json"


def extract_prerequisites(browser: Browser, courses_list: list[dict]) -> list[dict]:
    detail_page = browser.new_page()

    print("\n🕵️ Extracting prerequisites from detail pages...")
    with_urls = sum(1 for c in courses_list if c.get("detail_url"))
    print(f"   Entries with detail_url: {with_urls} / {len(courses_list)}")

    for idx, course in enumerate(courses_list):
        url = (course.get("detail_url") or "").strip()
        if not url:
            continue

        title_preview = (course.get("title") or "").splitlines()[0][:70]
        print(f"[{idx + 1}/{len(courses_list)}] {title_preview}")

        try:
            detail_page.goto(url, timeout=60_000)

            panel = detail_page.locator("div.panel.panel-default").filter(
                has=detail_page.locator("h2", has_text="Enrollment Requirements")
            )
            body = panel.locator(".panel-body").first

            if panel.count() > 0 and body.count() > 0:
                course["prerequisites"] = body.inner_text().strip()
            else:
                course["prerequisites"] = "None (section not found on page)"

        except Exception as e:
            print(f"   ⚠️ Failed: {e}")
            course["prerequisites"] = f"Unknown ({e})"

    detail_page.close()
    return courses_list


def main() -> None:
    parser = argparse.ArgumentParser(description="Add prerequisites from PISA detail pages.")
    parser.add_argument("--input", "-i", default=INPUT_DEFAULT, help="JSON from my_ucsc_scanner.py")
    parser.add_argument("--output", "-o", default=OUTPUT_DEFAULT, help="Where to write enriched JSON")
    parser.add_argument("--headless", action="store_true", help="Run browser headless")
    args = parser.parse_args()

    path = Path(args.input)
    if not path.is_file():
        print(f"❌ Missing {path.resolve()}. Run my_ucsc_scanner.py first.")
        return

    courses: list[dict] = json.loads(path.read_text(encoding="utf-8"))
    if not courses:
        print("❌ Input JSON is empty.")
        return

    missing = sum(1 for c in courses if not (c.get("detail_url") or "").strip())
    if missing == len(courses):
        print(
            "❌ No `detail_url` fields found in your JSON.\n"
            "   Re-run my_ucsc_scanner.py with the version that saves detail links\n"
            "   (panel-heading → href merged into detail_url)."
        )
        return
    if missing:
        print(f"⚠️ {missing} entries lack detail_url — those will be skipped.")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=args.headless)
        try:
            enriched = extract_prerequisites(browser, courses)
        finally:
            browser.close()

    out = Path(args.output)
    out.write_text(json.dumps(enriched, indent=4, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"\n🎉 Wrote {len(enriched)} rows → {out.resolve()}")


if __name__ == "__main__":
    main()
