from playwright.sync_api import sync_playwright
import json
import time

# Configurations
SUBJECT = "CSE"
TERM_LABEL = "2026 Fall Quarter"  # Adjust this to the quarter you want to scrape
REG_STATUS = "All Classes"        # Options: "Open Classes", "All Classes"
OUTPUT_FILE = "ucsc_courses.json"


def has_next_page(page) -> bool:
    return page.locator("a[onclick*=\"action.value = 'next'\"]").count() > 0


def scrape_current_page(page, page_num: int) -> list[dict]:
    page.wait_for_selector(".panel.panel-default", timeout=30_000)
    courses = []
    
    cards = page.locator(".panel.panel-default").all()
    
    for card in cards:
        title_el = card.locator(".panel-heading")
        body_el = card.locator(".panel-body")
        
        # FIND THE LINK TO THE CLASS DETAILS
        link_el = card.locator(".panel-heading a").first
        
        if title_el.count() > 0 and body_el.count() > 0:
            # PISA uses relative links (e.g., "index.php?action=detail..."), so we append the base URL
            relative_url = link_el.get_attribute("href") if link_el.count() > 0 else ""
            detail_url = f"https://pisa.ucsc.edu/class_search/{relative_url}" if relative_url else ""
            
            courses.append({
                "page": page_num,
                "title": title_el.inner_text().strip(),
                "content": body_el.inner_text().strip(),
                "detail_url": detail_url  # Save this for later!
            })
    return courses


def run():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False) 
        page = browser.new_page()

        print("🔗 Opening PISA...")
        page.goto("https://pisa.ucsc.edu/class_search/", timeout=60_000)
        
        print(f"⏳ Configuring search parameters [Term: {TERM_LABEL} | Subject: {SUBJECT} | Status: {REG_STATUS}]...")
        
        # Select search constraints dropdown parameters
        page.select_option('select[name="binds[:term]"]', label=TERM_LABEL)
        page.select_option('select[name="binds[:subject]"]', SUBJECT)
        page.select_option('select[name="binds[:reg_status]"]', label=REG_STATUS)
        
        print("🚀 Submitting search query...")
        # The Search control is a submit input element
        page.click('input[type="submit"]')

        all_courses = []
        page_num = 1

        while True:
            batch = scrape_current_page(page, page_num)
            all_courses.extend(batch)
            print(f"  Page {page_num}: {len(batch)} courses fetched.")

            if not has_next_page(page):
                print("🏁 Reached the last page.")
                break

            print("⏭️ Clicking Next page...")
            
            # Wait for the network/navigation to completely process the POST request
            # We wrap the click inside a wait_for_navigation block so Playwright doesn't race ahead.
            with page.expect_navigation(timeout=30_000):
                page.locator("a[onclick*=\"action.value = 'next'\"]").first.click()
            
            # Small buffer to let the old elements detach and new ones attach to the DOM
            time.sleep(1) 
            page_num += 1

        # Save unstructured payload output
        with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
            json.dump(all_courses, f, indent=4, ensure_ascii=False)

        with_urls = sum(1 for c in all_courses if (c.get("detail_url") or "").strip())
        print(f"🔗 detail_url filled: {with_urls}/{len(all_courses)} (needed for preq.py)")
        if with_urls == 0 and len(all_courses) > 0:
            print(
                "⚠️ No detail links captured — check that course cards have .panel-heading a "
                "or re-save after updating this script."
            )

        print(f"\n🎉 Done — Finished gathering {len(all_courses)} courses across {page_num} page(s) → {OUTPUT_FILE}")
        browser.close()


if __name__ == "__main__":
    run()