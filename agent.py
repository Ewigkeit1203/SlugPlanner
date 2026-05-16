import json
import re

def load_data():
    courses = json.load(open('ucsc_courses_with_preq.json'))
    rmp_cache = json.load(open('rmp_cache.json'))
    return courses, rmp_cache

def extract_units(content):
    # Most UCSC courses are 5 units, some are 2 or 3
    return 5  # default, can be improved

def extract_instructor(content):
    for line in content.splitlines():
        if 'Instructor' in line:
            parts = line.split(':', 1)
            if len(parts) > 1 and parts[1].strip():
                return parts[1].strip()
    return None

def extract_time(content):
    for line in content.splitlines():
        if any(day in line for day in ['MWF', 'TuTh', 'MW', 'TTh', 'Mon', 'Tue']):
            return line.strip()
    return None

def get_rmp_rating(instructor, rmp_cache):
    if instructor and instructor in rmp_cache:
        data = rmp_cache[instructor]
        if data.get('status') == 'ok':
            return data.get('avg_rating', 0)
    return None

def recommend_schedule(user_input, target_units=15, min_rating=3.5, no_early=True):
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
        
        # Skip early classes if requested
        if no_early and time and '8:00AM' in time:
            continue
            
        # Filter by RMP rating
        if rating and rating < min_rating:
            continue
            
        units = extract_units(content)
        recommended.append({
            'title': course['title'],
            'instructor': instructor,
            'rmp_rating': rating,
            'time': time,
            'prerequisites': course.get('prerequisites', 'None'),
            'units': units
        })
        total_units += units
    
    return recommended

if __name__ == '__main__':
    results = recommend_schedule("15 units, easy professors, no 8am")
    for r in results:
        print(json.dumps(r, indent=2))