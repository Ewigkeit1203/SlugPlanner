import json
import re
from check_prereq import check_prerequisites

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

MAJOR_RESTRICTION_NAMES = {
    'CSE': ['computer science', 'computer engineering'],
    'MATH': ['mathematics'],
    'BIOL': ['biology', 'biological sciences'],
    'PHYS': ['physics'],
    'CHEM': ['chemistry'],
    'ECON': ['economics'],
    'PSYC': ['psychology'],
    'ENGR': ['engineering'],
    'ECE': ['electrical engineering', 'computer engineering'],
    'LING': ['linguistics'],
    'PHIL': ['philosophy'],
    'SOCY': ['sociology'],
    'HIST': ['history'],
    'ANTH': ['anthropology'],
}

def is_restricted_to_other_major(prereqs, major_prefix):
    if 'enrollment is restricted to' not in prereqs.lower() and 'restricted to' not in prereqs.lower():
        return False
    if not major_prefix:
        return False
    allowed_names = MAJOR_RESTRICTION_NAMES.get(major_prefix, [])
    prereqs_lower = prereqs.lower()
    for name in allowed_names:
        if name in prereqs_lower:
            return False
    return True

def filter_courses(courses, rmp_cache, completed_normalized, completed_nums,
                   min_completed_num, min_rating, no_early, target_units,
                   is_major_pass=False, existing_units=0, existing_recommendations=None,
                   major_prefix=None):
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

        if no_early and time and any(t in time for t in ['8:', '08:']):
            continue

        if not is_major_pass and rating and rating < min_rating:
            continue

        if is_restricted_to_other_major(prereqs, major_prefix):
            continue

        course_code_match = re.search(r'[A-Z]{2,4}\s*\d+[A-Z]?', course.get('title', ''))

        if course_code_match:
            course_code = course_code_match.group().replace(' ', '')

            if course_code in completed_normalized:
                continue

            if any(c in prereqs for c in completed_normalized):
                if 'cannot enroll' in prereqs.lower() or 'antirequisite' in prereqs.lower():
                    continue

            if any(rec['title'] == clean_text(course.get('title', '')) for rec in recommended):
                continue

            if completed_nums:
                course_num = re.search(r'\d+', course_code)
                if course_num:
                    num = int(course_num.group())
                    if num < min_completed_num or num >= 200:
                        continue

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

    if major_prefix:
        major_courses = [c for c in courses if major_prefix in c.get('title', '')]
        other_courses = [c for c in courses if major_prefix not in c.get('title', '')]
    else:
        major_courses = []
        other_courses = courses

    major_courses.sort(key=lambda x: get_rmp_data(extract_instructor(x.get('content', '')), rmp_cache)['rating'] or 0, reverse=True)

    recommended = []
    total_units = 0

    if major_courses:
        recommended, total_units = filter_courses(
            major_courses, rmp_cache, completed_normalized, completed_nums,
            min_completed_num, min_rating, no_early, target_units,
            is_major_pass=True, existing_units=total_units, existing_recommendations=recommended,
            major_prefix=major_prefix
        )

    if total_units < target_units and other_courses:
        other_courses.sort(key=lambda x: get_rmp_data(extract_instructor(x.get('content', '')), rmp_cache)['rating'] or 0, reverse=True)

        recommended, total_units = filter_courses(
            other_courses, rmp_cache, completed_normalized, completed_nums,
            min_completed_num, min_rating, no_early, target_units,
            is_major_pass=False, existing_units=total_units, existing_recommendations=recommended,
            major_prefix=major_prefix
        )

    # Add missing degree requirements
    try:
        from major_requirements import get_missing_requirements
        if major_prefix:
            missing = get_missing_requirements(major_prefix, completed)
            for course in courses:
                if total_units >= target_units:
                    break
                title = course.get('title', '')
                for req in missing:
                    if req in title.replace(' ', ''):
                        instructor = extract_instructor(course.get('content', ''))
                        time = extract_time(course.get('content', ''))
                        if instructor and time and instructor.lower() != 'staff':
                            recommended.insert(0, {
                                'title': clean_text(title),
                                'instructor': instructor,
                                'rmp_rating': get_rmp_data(instructor, rmp_cache)['rating'],
                                'rmp_difficulty': get_rmp_data(instructor, rmp_cache)['difficulty'],
                                'would_take_again_percent': get_rmp_data(instructor, rmp_cache)['would_take_again'],
                                'time': time,
                                'prerequisites': course.get('prerequisites', 'None'),
                                'units': 5,
                                'required_for_degree': True
                            })
                            missing.remove(req)
                            break
    except Exception:
        pass

    return recommended

def run_tool(user_input: str) -> str:
    results = recommend_schedule(user_input)
    return json.dumps(results, indent=2)

if __name__ == '__main__':
    user_input = "I am a computer science major. I want 15 units, easy professors, no 8am classes. I have completed CSE 20 and MATH 19A"
    print(run_tool(user_input))