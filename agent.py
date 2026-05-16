import json
import re

def load_data():
    courses = json.load(open('ucsc_courses_with_preq.json'))
    rmp_cache = json.load(open('rmp_cache.json'))
    return courses, rmp_cache

def extract_units(content):
    return 5

def clean_text(text):
    if not text:
        return text
    text = text.replace('\u00c2\u00a0', ' ').replace('\xa0', ' ').replace('Â', '').replace('\ufffd', ' ')
    text = re.sub(r'\s+', ' ', text)
    return text.strip()

def extract_instructor(content):
    lines = content.splitlines()
    for idx, line in enumerate(lines):
        if re.match(r'^\s*Instructor\s*:\s*$', line, re.I):
            for next_line in lines[idx + 1:]:
                candidate = clean_text(next_line.strip())
                if candidate:
                    return candidate
            return None
        if 'Instructor:' in line:
            parts = line.split(':', 1)
            if len(parts) > 1 and parts[1].strip():
                return clean_text(parts[1])
    return None

def extract_time(content):
    for line in content.splitlines():
        if any(day in line for day in ['MWF', 'TuTh', 'MW', 'TTh', 'Mon', 'Tue']):
            return clean_text(line)
    return None

def get_rmp_data(instructor, rmp_cache):
    if instructor and instructor in rmp_cache:
        data = rmp_cache[instructor]
        if data.get('status') == 'ok':
            return {
                'rating': data.get('avg_rating'),
                'difficulty': data.get('avg_difficulty'),
                'would_take_again': data.get('would_take_again_percent')
            }
    return {'rating': None, 'difficulty': None, 'would_take_again': None}

def parse_input(user_input):
    target_units = 15
    min_rating = 3.5
    no_early = False
    completed = []

    if match := re.search(r'(\d+)\s*units', user_input, re.I):
        target_units = int(match.group(1))
    if any(w in user_input.lower() for w in ['easy', 'good professor', 'high rated']):
        min_rating = 4.0
    if any(w in user_input.lower() for w in ['no 8', 'no early', 'no morning']):
        no_early = True

    completed = re.findall(r'[A-Z]{2,4}\s*\d+[A-Z]?', user_input)

    return target_units, min_rating, no_early, completed

def detect_major(user_input):
    """Detect major prefix from user input with fallback matching."""
    input_lower = user_input.lower()

    major_map = {
        'CSE': ['cs major', 'computer science', 'cse major', 'software', 'computing'],
        'MATH': ['math major', 'mathematics', 'applied math'],
        'BIOL': ['biology major', 'bio major', 'biological'],
        'PHYS': ['physics major', 'physics'],
        'CHEM': ['chemistry major', 'chem major'],
        'ECON': ['econ major', 'economics major', 'economics'],
        'PSYC': ['psychology major', 'psych major', 'psychology'],
        'ENGR': ['engineering major', 'general engineering'],
        'ECE': ['electrical engineering', 'ece major', 'electrical eng'],
        'LING': ['linguistics major', 'ling major'],
        'PHIL': ['philosophy major', 'phil major'],
        'SOCY': ['sociology major', 'sociology'],
        'HIST': ['history major', 'history'],
        'ANTH': ['anthropology major', 'anth major'],
    }

    for prefix, keywords in major_map.items():
        if any(kw in input_lower for kw in keywords):
            return prefix

    return None

def meets_prerequisites(prereqs, completed_normalized):
    """Check if completed courses satisfy prerequisites."""
    if not prereqs or prereqs == 'None' or 'section not found' in prereqs:
        return True

    required = re.findall(r'[A-Z]{2,4}\s*\d+[A-Z]?', prereqs)
    if not required:
        return True

    for req in required:
        if req.replace(' ', '') in completed_normalized:
            return True

    return False

def recommend_schedule(user_input):
    target_units, min_rating, no_early, completed = parse_input(user_input)
    courses, rmp_cache = load_data()

    completed_normalized = [c.replace(' ', '') for c in completed]

    completed_nums = []
    for c in completed:
        num = re.search(r'\d+', c)
        if num:
            completed_nums.append(int(num.group()))
    min_completed_num = min(completed_nums) if completed_nums else 0

    major_prefix = detect_major(user_input)

    if major_prefix:
        courses = sorted(courses, key=lambda c: (0 if major_prefix in c.get('title', '') else 1))

    recommended = []
    total_units = 0

    for course in courses:
        if total_units >= target_units:
            break

        content = course.get('content', '')
        time = extract_time(content)
        instructor = extract_instructor(content)
        rmp = get_rmp_data(instructor, rmp_cache)
        rating = rmp['rating']
        prereqs = course.get('prerequisites', 'None')

        # Skip missing instructor, time, or unassigned staff
        if not instructor or not time or instructor.lower() == 'staff':
            continue

        if no_early and time and any(t in time for t in ['8:', '08:']):
            continue

        if rating and rating < min_rating:
            continue

        course_code = re.search(r'[A-Z]{2,4}\s*\d+[A-Z]?', course.get('title', ''))

        # Skip already completed courses
        if course_code and course_code.group().replace(' ', '') in completed_normalized:
            continue

        # Skip courses below user's level or graduate level (200+)
        if course_code and completed_nums:
            course_num = re.search(r'\d+', course_code.group())
            if course_num:
                num = int(course_num.group())
                if num < min_completed_num or num >= 200:
                    continue

        # Skip courses whose prerequisites user hasn't met
        if completed_normalized and not meets_prerequisites(prereqs, completed_normalized):
            continue

        units = extract_units(content)
        recommended.append({
            'title': clean_text(course.get('title', '')),
            'instructor': instructor,
            'rmp_rating': rating,
            'rmp_difficulty': rmp['difficulty'],
            'would_take_again_percent': rmp['would_take_again'],
            'time': time,
            'prerequisites': prereqs,
            'units': units
        })
        total_units += units

    return recommended

def run_tool(user_input: str) -> str:
    results = recommend_schedule(user_input)
    return json.dumps(results, indent=2)

if __name__ == '__main__':
    user_input = "I want 15 units, easy professors, no 8am classes"
    print(run_tool(user_input))