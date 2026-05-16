from playwright.sync_api import sync_playwright
import json

def scrape_cs_catalog():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        page = browser.new_page()
        
        # 1. THE URL HACK: We append your anchor right to the end of the URL
        # (I used #requirementstext as it targets the whole tab, but #degree-req-2 works the same way!)
        target_url = "https://catalog.ucsc.edu/en/current/general-catalog/academic-units/baskin-engineering/computer-science-and-engineering/computer-science-bs#requirementstext"
        
        print("🔗 Opening UCSC CS Catalog directly to the Planner tab...")
        page.goto(target_url, timeout=60000)
        
        # 2. NO MORE CLICKING! The URL handled the tab switch for us. 
        # We just wait for the tables to render.
        print("⏳ Waiting for course tables to load...")
        page.locator("table.sc_courselist").first.wait_for(state="visible", timeout=15000)
        
        course_tables = page.locator("table.sc_courselist").all()
        print(f"📊 Found {len(course_tables)} requirement tables.")
        
        major_requirements = {}
        
        for table in course_tables:
            rows = table.locator("tr").all()
            
            # We assume classes are mandatory until we hit an elective header
            is_mandatory_block = True 
            
            for row in rows:
                text = row.inner_text().strip()
                
                # Detect "Choose one" / OR logic blocks
                if "Choose one of the following" in text or "Plus one of the following" in text or "Electives" in text:
                    is_mandatory_block = False
                    continue
                
                # Extract the course code from the CourseLeaf hyperlink
                course_link = row.locator("a.bubblelink")
                if course_link.count() > 0:
                    raw_code = course_link.first.inner_text()
                    clean_code = raw_code.replace('\xa0', '').replace(' ', '').upper()
                    
                    if clean_code not in major_requirements:
                        major_requirements[clean_code] = {
                            "prereqs": [], 
                            "required": is_mandatory_block
                        }
        
        final_output = {"CSE": major_requirements}
        
        with open("major_catalog.json", "w", encoding="utf-8") as f:
            json.dump(final_output, f, indent=4)
            
        print(f"✅ CS Requirements Saved! Extracted {len(major_requirements)} courses into major_catalog.json.")
        browser.close()

if __name__ == "__main__":
    scrape_cs_catalog()