import re


def check_prerequisites(prereq_string: str, completed_courses: list[str]) -> bool:
    """
    Evaluates if a student's completed courses satisfy a given prerequisite string.
    Converts text like "CSE 12 and MATH 19B" into "True and False" and evaluates it.
    """
    if not prereq_string or prereq_string.lower() in ("none", "section not found"):
        return True

    text = prereq_string.upper()

    course_tokens = re.findall(r"([A-Z]{2,4}\s*\d+[A-Z]?)", text)
    if not course_tokens:
        return True

    completed_set = {c.replace(" ", "").upper() for c in completed_courses}

    for token in sorted(set(course_tokens), key=len, reverse=True):
        normalized_token = token.replace(" ", "")
        has_completed = "True" if normalized_token in completed_set else "False"
        text = text.replace(token, has_completed)

    text = text.replace(";", " AND ").replace(",", " AND ")
    text = re.sub(r"\bAND\b", "and", text)
    text = re.sub(r"\bOR\b", "or", text)

    allowed_words = re.findall(r"(true|false|and|or|\(|\))", text.lower())
    boolean_expression = " ".join(allowed_words)

    if not boolean_expression.strip():
        return True

    try:
        return bool(eval(boolean_expression))
    except Exception:
        return any(token.replace(" ", "") in completed_set for token in course_tokens)
