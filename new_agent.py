import json
import re
from check_prereq import check_prerequisites

def load_data():
    courses = json.load(open('ucsc_courses_with_preq.json'))
    rmp_cache = json.load(open('rmp_cache.json'))
    major_catalog = json.load(open('major_catalog.json'))
    return courses, rmp_cache, major_catalog

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
    """
    Analyzes the prompt to find the specific catalog key (e.g., 'CSE_BS') 
    and the department prefix (e.g., 'CSE') for filtering.
    """
    input_lower = user_input.lower()
    
    catalog_key = None
    dept_prefix = None
    
    if any(kw in input_lower for kw in ['applied math', 'applied mathematics']):
        catalog_key = 'AM_BS'
        dept_prefix = 'AM' 
    elif any(kw in input_lower for kw in ['cs major', 'computer science', 'cse major', 'software']):
        dept_prefix = 'CSE'
        if any(kw in input_lower for kw in ['b.a.', ' ba', 'arts']):
            catalog_key = 'CSE_BA'
        else:
            catalog_key = 'CSE_BS'
    elif any(kw in input_lower for kw in ['math major', 'mathematics']):
        dept_prefix = 'MATH'
        if any(kw in input_lower for kw in ['b.a.', ' ba', 'arts']):
            catalog_key = 'MATH_BA'
        else:
            catalog_key = 'MATH_BS'
    elif any(kw in input_lower for kw in ['electrical engineering', 'ee major']):
        catalog_key = 'Electrical_Engineering'
        dept_prefix = 'ECE'
    elif any(kw in input_lower for kw in ['robotics', 'robo major']):
        catalog_key = 'ROBO_BS'
        dept_prefix = 'ECE'
    elif any(kw in input_lower for kw in ['business', 'bmec']):
        catalog_key = 'Business'
        dept_prefix = 'ECON'
    elif any(kw in input_lower for kw in ['econ', 'economics']):
        catalog_key = 'ECON'
        dept_prefix = 'ECON'
            
    return catalog_key, dept_prefix

def get_frontier_courses(major_track, completed, courses):
    """
    Calculates the 'Frontier' by dynamically looking up the prereq string 
    from the course database and passing it through the boolean engine.
    """
    # Create a fast lookup dictionary mapping "CSE101" -> "Prerequisite(s): CSE 30..."
    course_prereqs = {}
    for c in courses:
        title = c.get('title', '')
        match = re.search(r'[A-Z]{2,4}\s*\d+[A-Z]?', title)
        if match:
            code = match.group().replace(' ', '').upper()
            course_prereqs[code] = c.get('prerequisites', 'None')

    frontier = []
    for course_code, data in major_track.items():
        if course_code in completed:
            continue
            
        prereq_string = course_prereqs.get(course_code, 'None')
        
        # Only add to frontier if the boolean logic engine clears the prerequisite!
        if check_prerequisites(prereq_string, completed):
            frontier.append({
                "code": course_code,
                "required": data.get("required", False)
            })
            
    return frontier

def filter_courses(courses, rmp_cache, completed_normalized, completed_nums,
                   min_completed_num, min_rating, no_early, target_units, 
                   is_major_pass=False, existing_units=0, existing_recommendations=None):
    
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

        # Force the agent to take low-rated professors IF it's a mandatory major requirement pass
        if not is_major_pass and rating and rating < min_rating:
            continue

        if any(rec['title'] == clean_text(course.get('title', '')) for rec in recommended):
            continue

        # 🚨 STRICT HARD CONSTRAINT: Every single class MUST pass the prereq check
        if not check_prerequisites(prereqs, completed_normalized):
            continue

        units = extract_units(content)
        recommended.append({
            'title': clean_text(course.get('title', '')),
            'instructor': instructor,
            'rmp_rating': rating,
            'rmp_difficulty': rmp['difficulty'],
            'time': time,
            'units': units
        })
        total_units += units

    return recommended, total_units


def recommend_schedule(user_input):
    target_units, min_rating, no_early, completed = parse_input(user_input)
    courses, rmp_cache, major_catalog = load_data()

    completed_normalized = [c.replace(' ', '').upper() for c in completed]
    completed_nums = [int(num.group()) for c in completed if (num := re.search(r'\d+', c))]
    min_completed_num = min(completed_nums) if completed_nums else 0

    catalog_key, dept_prefix = detect_major(user_input)
    
    frontier_data = []
    if catalog_key and catalog_key in major_catalog:
        # Cross-reference the catalog track with the live course data
        frontier_data = get_frontier_courses(major_catalog[catalog_key], completed_normalized, courses)

    frontier_codes = {item["code"] for item in frontier_data}
    required_frontier = {item["code"] for item in frontier_data if item["required"]}

    frontier_courses = []
    other_courses = []

    for c in courses:
        title = c.get('title', '')
        course_code_match = re.search(r'[A-Z]{2,4}\s*\d+[A-Z]?', title)
        
        if course_code_match:
            code = course_code_match.group().replace(' ', '').upper()
            if code in frontier_codes:
                sort_weight = 10 if code in required_frontier else 0
                c['_sort_weight'] = sort_weight
                frontier_courses.append(c)
                
            elif dept_prefix and dept_prefix in code:
                # Locked or already completed major classes are hidden
                continue
            else:
                other_courses.append(c)
        else:
            other_courses.append(c)

    recommended = []
    total_units = 0

    # ─── PASS 1: CORE MAJOR TRACK LOCK (The Frontier) ───
    if frontier_courses:
        frontier_courses.sort(
            key=lambda x: (
                x.get('_sort_weight', 0), 
                get_rmp_data(extract_instructor(x.get('content', '')), rmp_cache)['rating'] or 0
            ), 
            reverse=True
        )
        
        recommended, total_units = filter_courses(
            frontier_courses, rmp_cache, completed_normalized, completed_nums,
            min_completed_num, min_rating, no_early, target_units,
            is_major_pass=True, existing_units=total_units, existing_recommendations=recommended
        )

    # ─── PASS 2: ELECTIVE / GE FILLER PASS ───
    if total_units < target_units and other_courses:
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
    user_input = "I am a computer science major. I want 15 units, easy professors, no 8am classes. I have completed CSE 20, CSE 30, CSE 12, CSE 13S, MATH 19A, MATH 19B."
    print(run_tool(user_input))