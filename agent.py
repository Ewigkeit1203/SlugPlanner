import json
import re
from check_prereq import check_prerequisites

def load_data():
    # Enforce using your completed master file names
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
        # Supporting both 'ok' wrappers and raw dictionary returns natively
        if isinstance(data, dict):
            if data.get('status') == 'ok' or 'avg_rating' in data:
                return {
                    'rating': data.get('avg_rating') or data.get('rating'),
                    'difficulty': data.get('avg_difficulty') or data.get('difficulty'),
                    'would_take_again': data.get('would_take_again_percent') or data.get('would_take_again')
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
        min_rating = 3.5
    if any(w in user_input.lower() for w in ['no 8', 'no early', 'no morning']):
        no_early = True

    completed = re.findall(r'[A-Z]{2,4}\s*\d+[A-Z]?', user_input)
    return target_units, min_rating, no_early, completed

def detect_major(user_input):
    input_lower = user_input.lower()
    major_map = {
        'CSE': ['cs major', 'computer science', 'cse major', 'software', 'computing'],
        'MATH': ['math major', 'mathematics', 'applied math'],
    }
    for prefix, keywords in major_map.items():
        if any(kw in input_lower for kw in keywords):
            return prefix
    return None


def filter_courses(courses, rmp_cache, completed_normalized, completed_nums,
                   min_completed_num, min_rating, no_early, target_units, 
                   is_major_pass=False, existing_units=0, existing_recommendations=None):
    """Filter courses and return recommendations up to target units."""
    recommended = existing_recommendations if existing_recommendations is not None else []
    total_units = existing_units

    for course in courses:
        if total_units >= target_units:
            break

        content = course.get('content', '')
        time = extract_time(content)
        instructor = extract_instructor(content)
        rmp = get_rmp_data(instructor, rmp_cache)
        rating = rmp['rating']
        prereqs = course.get('prerequisites', 'None')

        if not instructor or not time or instructor.lower() == 'staff':
            continue

        # Hard Constraint: Time conflicts (No early classes if requested)
        if no_early and time and any(t in time for t in ['8:', '08:']):
            continue

        # Soft Constraint: Professor Rating
        # BUG FIX: If this is the Major Pass, do NOT drop the course completely due to a low rating.
        # We want to pick the course anyway because the student NEEDS it to graduate.
        if not is_major_pass and rating and rating < min_rating:
            continue

        course_code_match = re.search(r'[A-Z]{2,4}\s*\d+[A-Z]?', course.get('title', ''))

        if course_code_match:
            course_code = course_code_match.group().replace(' ', '')
            
            # Skip if already taken
            if course_code in completed_normalized:
                continue

            # Skip antirequisites
            if any(c in prereqs for c in completed_normalized):
                if 'cannot enroll' in prereqs.lower() or 'antirequisite' in prereqs.lower():
                    continue

            # Prevent duplication if already added in a previous pass
            if any(rec['title'] == clean_text(course.get('title', '')) for rec in recommended):
                continue

            # Skip lower-level courses if completed_nums constraints are active
            if completed_nums:
                course_num = re.search(r'\d+', course_code)
                if course_num:
                    num = int(course_num.group())
                    if num < min_completed_num or num >= 200:
                        continue

        # Hard Constraint: Prerequisite check engine
        if completed_normalized and not check_prerequisites(prereqs, completed_normalized):
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

    return recommended, total_units


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

    # Separate our main list into Major track buckets and General track buckets
    if major_prefix:
        major_courses = [c for c in courses if major_prefix in c.get('title', '')]
        other_courses = [c for c in courses if major_prefix not in c.get('title', '')]
    else:
        major_courses = []
        other_courses = courses

    # Sort major courses by rating descending so we find the best professors available first
    major_courses.sort(key=lambda x: get_rmp_data(extract_instructor(x.get('content', '')), rmp_cache)['rating'] or 0, reverse=True)

    recommended = []
    total_units = 0

    # ─── PASS 1: CORE MAJOR TRACK LOCK ───
    if major_courses:
        recommended, total_units = filter_courses(
            major_courses, rmp_cache, completed_normalized, completed_nums,
            min_completed_num, min_rating, no_early, target_units,
            is_major_pass=True, existing_units=total_units, existing_recommendations=recommended
        )

    # ─── PASS 2: ELECTIVE / GE FILLER PASS ───
    # If the student still needs units, look at outside departments with strict rating guards
    if total_units < target_units and other_courses:
        # Sort other courses by rating so the best options get evaluated first
        other_courses.sort(key=lambda x: get_rmp_data(extract_instructor(x.get('content', '')), rmp_cache)['rating'] or 0, reverse=True)
        
        recommended, total_units = filter_courses(
            other_courses, rmp_cache, completed_normalized, completed_nums,
            min_completed_num, min_rating, no_early, target_units,
            is_major_pass=False, existing_units=total_units, existing_recommendations=recommended
        )

    return recommended

def run_tool(user_input: str) -> str:
    results = recommend_schedule(user_input)
    return json.dumps(results, indent=2)

if __name__ == '__main__':
    user_input = "I am a computer science major. I want 15 units, easy professors, no 8am classes. I have completed CSE 20 and MATH 19A"
    print(run_tool(user_input))