import re

def check_prerequisites(prereq_string: str, completed_courses: list) -> bool:
    if not prereq_string or prereq_string.lower() in ("none", "section not found"):
        return True
    
    # Extract the actual prerequisite part (before "Enrollment restricted")
    prereq_lower = prereq_string.lower()
    if 'enrollment' in prereq_lower:
        prereq_string = prereq_string[:prereq_lower.index('enrollment')]
    
    text = prereq_string.upper()
    completed_set = {c.replace(' ', '').upper() for c in completed_courses}
    
    course_tokens = re.findall(r'[A-Z]{2,4}\s*\d+[A-Z]?', text)
    if not course_tokens:
        return True
    
    # Replace course codes with True/False
    for token in sorted(set(course_tokens), key=len, reverse=True):
        normalized = token.replace(' ', '')
        replacement = 'True' if normalized in completed_set else 'False'
        text = text.replace(token, replacement)
    
    # Normalize logical operators
    text = re.sub(r'\bAND\b', 'and', text)
    text = re.sub(r'\bOR\b', 'or', text)
    text = text.replace(';', ' and ').replace(',', ' and ')
    
    # Extract only valid boolean expression parts
    tokens = re.findall(r'true|false|and|or|\(|\)', text.lower())
    if not tokens:
        return True
    
    boolean_expr = ' '.join(tokens)
    
    try:
        return bool(eval(boolean_expr))
    except Exception:
        return any(t.replace(' ', '') in completed_set for t in course_tokens)

if __name__ == '__main__':
    completed = ['CSE12', 'CSE13S', 'CSE20', 'CSE30']
    prereq = 'Prerequisite(s): CSE 12 and CSE 101.'
    print(check_prerequisites(prereq, completed))  # Should print False