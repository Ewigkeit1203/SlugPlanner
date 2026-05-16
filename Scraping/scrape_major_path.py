from playwright.sync_api import sync_playwright
import json
import re

# Add the majors you want to support for your demo here!
# Just grab the URL for the major and make sure it ends with /#degree-req-2
TARGET_MAJORS = {
    "CSE_BS": "https://catalog.ucsc.edu/en/current/general-catalog/academic-units/baskin-engineering/computer-science-and-engineering/computer-science-bs/#degree-req-2",
    "CSE_BA": "https://catalog.ucsc.edu/en/current/general-catalog/academic-units/baskin-engineering/computer-science-and-engineering/computer-science-ba/#degree-req-2",
    "MATH_BS": "https://catalog.ucsc.edu/en/current/general-catalog/academic-units/physical-and-biological-sciences-division/mathematics/mathematics-bs/#degree-req-2",
    "MATH_BA": "https://catalog.ucsc.edu/en/current/general-catalog/academic-units/physical-and-biological-sciences-division/mathematics/mathematics-ba/#degree-req-2",
    "EE_BS": "https://catalog.ucsc.edu/en/current/general-catalog/academic-units/baskin-engineering/electrical-and-computer-engineering/electrical-engineering-bs/#degree-req-2",
    "ROBO_BS": "https://catalog.ucsc.edu/en/current/general-catalog/academic-units/baskin-engineering/electrical-and-computer-engineering/robotics-engineering-bs/#degree-req-2",
    "ECON": "https://catalog.ucsc.edu/en/current/general-catalog/academic-units/social-sciences-division/economics/economics-ba/#degree-req-2",
    "Business": "https://catalog.ucsc.edu/en/current/general-catalog/academic-units/social-sciences-division/economics/business-management-economics-ba/#degree-req-2"
}   

def scrape_catalogs():
    master_catalog = {}
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        page = browser.new_page()
        
        for major_code, url in TARGET_MAJORS.items():
            print(f"\n🔗 Scraping {major_code}...")
            
            try:
                page.goto(url, timeout=60000)
                
                req_container = page.locator("#degree-req-2")
                req_container.wait_for(state="attached", timeout=15000)
                page.wait_for_timeout(2000) 
                
                raw_text = req_container.inner_text()
                
                if not raw_text.strip():
                    print(f"⚠️ Warning: Could not read text for {major_code}. Skipping...")
                    continue
                    
                major_requirements = {}
                is_mandatory = True 
                
                for line in raw_text.split('\n'):
                    line = line.strip()
                    if not line:
                        continue
                        
                    lower_line = line.lower()
                    
                    if "choose one of the following" in lower_line or "electives" in lower_line or "plus one of the following" in lower_line:
                        is_mandatory = False
                    elif "plus the following" in lower_line or "requirements" in lower_line or "core" in lower_line:
                        is_mandatory = True
                        
                    matches = re.findall(r'\b[A-Z]{2,4}\s+\d+[A-Z]?\b', line)
                    
                    for match in matches:
                        clean_code = match.replace(' ', '').upper()
                        
                        if clean_code not in major_requirements:
                            major_requirements[clean_code] = {
                                "prereqs": [], 
                                "required": is_mandatory
                            }
                        elif is_mandatory:
                            major_requirements[clean_code]["required"] = True
                            
                # Save this major's requirements under its unique key
                master_catalog[major_code] = major_requirements
                print(f"✅ Successfully processed {major_code} ({len(major_requirements)} courses).")
                
            except Exception as e:
                print(f"❌ Failed to scrape {major_code}: {e}")
        
        # Save the master dictionary containing ALL majors
        with open("major_catalog.json", "w", encoding="utf-8") as f:
            json.dump(master_catalog, f, indent=4)
            
        print(f"\n🎉 Finished! Saved {len(master_catalog)} majors to major_catalog.json.")
        browser.close()

if __name__ == "__main__":
    scrape_catalogs()