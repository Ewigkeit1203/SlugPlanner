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

def get_rmp_rating(instructor, rmp_cache):
    if instructor and instructor in rmp_cache:
        data = rmp_cache[instructor]
        if data.get('status') == 'ok':
            return data.get('avg_rating', 0)
    return None

def parse_input(user_input):
    target_units = 15
    min_rating = 3.5
    no_early = False

    if match := re.search(r'(\d+)\s*units', user_input, re.I):
        target_units = int(match.group(1))
    if any(w in user_input.lower() for w in ['easy', 'good professor', 'high rated']):
        min_rating = 4.0
    if any(w in user_input.lower() for w in ['no 8', 'no early', 'no morning']):
        no_early = True

    return target_units, min_rating, no_early

def recommend_schedule(user_input):
    target_units, min_rating, no_early = parse_input(user_input)
    courses, rmp_cache = load_data()

    recommended = []
    total_units = 0

    for course in courses:
        if total_units >= target_units:
            break

        content = course.get('content', '')
        time = extract_time(content)
        instructor = extract_instructor(content)
        rating = get_rmp_rating(instructor, rmp_cache)

        if no_early and time and any(t in time for t in ['8:', '08:']):
            continue

        if rating and rating < min_rating:
            continue

        units = extract_units(content)
        recommended.append({
            'title': clean_text(course.get('title', '')),
            'instructor': instructor,
            'rmp_rating': rating,
            'time': time,
            'prerequisites': course.get('prerequisites', 'None'),
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