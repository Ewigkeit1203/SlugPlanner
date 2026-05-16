from playwright.sync_api import sync_playwright
import json

def scrape_cs_catalog():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        
        print("🔗 Opening UCSC CS Catalog...")
        page.goto("https://catalog.ucsc.edu/en/current/general-catalog/academic-units/baskin-engineering/computer-science-and-engineering/computer-science-bs")
        
        # Click the 'Requirements and Planners' tab
        page.click("button:has-text('Requirements and Planners')")
        
        # Look for the course list tables (Courseleaf uses .sc_courselist)
        course_tables = page.locator("table.sc_courselist").all()
        
        major_requirements = []
        
        for table in course_tables:
            rows = table.locator("tr").all()
            current_rule = "MANDATORY"
            
            for row in rows:
                text = row.inner_text().strip()
                
                # Detect the "Choose one of" rule blocks
                if "Choose one of the following" in text or "Plus one of the following" in text:
                    current_rule = "CHOOSE_ONE"
                    continue
                
                # If it's a course row, grab the course code
                course_link = row.locator("a.bubblelink")
                if course_link.count() > 0:
                    course_code = course_link.first.inner_text().replace('\u00a0', ' ')
                    
                    # If the row has an "and" (like MATH 23A & 23B), bundle them
                    if "&" in text or "and" in text.lower():
                        bundled_courses = [course_code, "MATH 23B"] # simplified extraction
                        major_requirements.append({"rule": current_rule, "courses": bundled_courses})
                    else:
                        major_requirements.append({"rule": current_rule, "courses": [course_code]})
                        
        with open("major_catalog.json", "w") as f:
            json.dump({"CSE": major_requirements}, f, indent=4)
            
        print("✅ CS Requirements Saved!")
        browser.close()

if __name__ == "__main__":
    scrape_cs_catalog()