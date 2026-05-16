import PyPDF2
import re
import os

PDF_PATH = os.path.join(os.path.dirname(__file__), '2025-26-General-Catalog.pdf')

MAJOR_SEARCH_TERMS = {
    'CSE': 'COMPUTER SCIENCE B.S.',
    'MATH': 'MATHEMATICS B.S.',
    'ECON': 'ECONOMICS B.A.',
    'BIOL': 'BIOLOGY B.S.',
    'PHYS': 'PHYSICS B.S.',
    'ECE': 'ELECTRICAL ENGINEERING B.S.',
}

def get_major_requirements(major_prefix):
    search_term = MAJOR_SEARCH_TERMS.get(major_prefix)
    if not search_term or not os.path.exists(PDF_PATH):
        return []
    
    with open(PDF_PATH, 'rb') as f:
        reader = PyPDF2.PdfReader(f)
        start_page = None
        for i, page in enumerate(reader.pages):
            if search_term in page.extract_text():
                start_page = i
                break
        
        if start_page is None:
            return []
        
        all_courses = []
        for i in range(start_page, min(start_page + 4, len(reader.pages))):
            text = reader.pages[i].extract_text()
            courses = re.findall(r'[A-Z]{2,4} \d+[A-Z]?', text)
            all_courses.extend(courses)
    
    # Clean up false positives
    valid = [c.replace(' ', '') for c in set(all_courses) 
             if not any(x in c for x in ['CRUZ', 'UCSC', 'UC S'])]
    return sorted(valid)

def get_missing_requirements(major_prefix, completed):
    completed_normalized = [c.replace(' ', '') for c in completed]
    required = get_major_requirements(major_prefix)
    return [r for r in required if r not in completed_normalized]

if __name__ == '__main__':
    completed = ['CSE20', 'CSE30', 'MATH19A']
    missing = get_missing_requirements('CSE', completed)
    print('Missing CS requirements:', missing)