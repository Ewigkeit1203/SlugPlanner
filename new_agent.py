"""
UCSC Course Planner — DAG built directly from ucsc_courses_with_preq.json
--------------------------------------------------------------------------
No separate catalog file needed. The prerequisite graph is parsed from the
'prerequisites' field already scraped into each course entry.

Flow:
  1. Parse every course's prereq string → build { code: [prereqs] } DAG
  2. Mark student's completed courses on the DAG
  3. Compute frontier (courses whose prereqs are all satisfied)
  4. For each frontier course, find its best-rated section via RMP
  5. Greedily fill target units (major courses first, then electives)
"""

import json
import re
from collections import defaultdict


# ── Load data ─────────────────────────────────────────────────────────────────

def load_data():
    courses   = json.load(open("ucsc_courses_with_preq.json"))
    rmp_cache = json.load(open("rmp_cache.json"))
    return courses, rmp_cache


# ── Text helpers ──────────────────────────────────────────────────────────────

def clean_text(text: str) -> str:
    if not text:
        return text
    text = (text
            .replace("\u00c2\u00a0", " ")
            .replace("\xa0", " ")
            .replace("Â", "")
            .replace("\ufffd", " "))
    return re.sub(r"\s+", " ", text).strip()


def normalize_code(raw: str) -> str:
    """'CSE 101 - 02' → 'CSE101',  'MATH 19A' → 'MATH19A'"""
    m = re.search(r"([A-Z]{2,4})\s*(\d+[A-Z]?)", raw.upper())
    return f"{m.group(1)}{m.group(2)}" if m else ""


def parse_title(title: str) -> tuple[str, str]:
    """
    'Open\n CSE 101 - 02   Algorithms' → ('CSE101', 'CSE 101 - 02   Algorithms')
    Returns (normalized_code, clean_display_title).
    """
    clean = clean_text(title.replace("Open", "").replace("Closed", "").strip())
    code  = normalize_code(clean)
    return code, clean


# ── Field extractors ──────────────────────────────────────────────────────────

def extract_instructor(content: str) -> str | None:
    lines = content.splitlines()
    for idx, line in enumerate(lines):
        if re.match(r"^\s*Instructor\s*:\s*$", line, re.I):
            for next_line in lines[idx + 1:]:
                c = clean_text(next_line.strip())
                if c:
                    return c
            return None
        if "Instructor:" in line:
            parts = line.split(":", 1)
            if len(parts) > 1 and parts[1].strip():
                return clean_text(parts[1])
    return None


def extract_time(content: str) -> str | None:
    for line in content.splitlines():
        if any(d in line for d in ["MWF", "TuTh", "MW", "TTh", "Mon", "Tue", "Wed", "Fri"]):
            return clean_text(line)
    return None


def extract_units(content: str) -> int:
    m = re.search(r"(\d)\s*[Uu]nit", content)
    return int(m.group(1)) if m else 5


def is_closed(title: str) -> bool:
    return title.strip().startswith("Closed")


# ── RMP lookup ────────────────────────────────────────────────────────────────

def get_rmp(instructor: str | None, rmp_cache: dict) -> dict:
    if instructor and instructor in rmp_cache:
        d = rmp_cache[instructor]
        if isinstance(d, dict) and (d.get("status") == "ok" or "avg_rating" in d):
            return {
                "rating":           d.get("avg_rating")               or d.get("rating"),
                "difficulty":       d.get("avg_difficulty")           or d.get("difficulty"),
                "would_take_again": d.get("would_take_again_percent") or d.get("would_take_again"),
            }
    return {"rating": None, "difficulty": None, "would_take_again": None}


# ── Prereq string parser ──────────────────────────────────────────────────────

COURSE_RE = re.compile(r"\b([A-Z]{2,4})\s+(\d+[A-Z]?)\b")

def parse_prereq_codes(prereq_str: str) -> list[str]:
    """
    Extract every course code mentioned in a prerequisite string.
    'Prerequisite(s): CSE 20 or CSE 30, and MATH 19A.'
    → ['CSE20', 'CSE30', 'MATH19A']

    We collect ALL mentioned codes. The or/and logic is handled by
    check_prerequisites; here we just need the full set for the DAG.
    For the frontier check we conservatively require ALL listed codes —
    meaning a student only enters the frontier once they could satisfy
    ANY branch (since they'll have taken at least the OR options that
    appear in the string). This is intentionally conservative.
    """
    if not prereq_str or prereq_str.strip().lower() in ("none", ""):
        return []
    if "restricted to graduate" in prereq_str.lower():
        return []
    return [f"{m.group(1)}{m.group(2)}" for m in COURSE_RE.finditer(prereq_str)]


def any_prereq_branch_satisfied(prereq_str: str, completed: set[str]) -> bool:
    """
    Returns True if the student satisfies at least one OR-branch of the prereqs.
    This is a fast heuristic; check_prerequisites handles the full logic.

    Strategy: split the prereq string on ' and ' (case-insensitive) to get
    conjunctive groups, then within each group check if any 'or' alternative
    is completed. A student passes if ALL conjunctive groups are satisfied.
    """
    if not prereq_str or prereq_str.strip().lower() in ("none", ""):
        return True  # no prereqs — always open
    if "restricted to graduate" in prereq_str.lower():
        return False

    # Strip the "Prerequisite(s):" prefix
    body = re.sub(r"^[Pp]rerequisite[s]?\s*\(s\)?\s*:?\s*", "", prereq_str)
    body = re.sub(r"\.\s*$", "", body).strip()

    # Split into conjunctive clauses on "; and ", ", and ", " and "
    and_groups = re.split(r"[;,]?\s+and\s+", body, flags=re.I)

    for group in and_groups:
        # Within each group, extract courses and check if any is completed
        codes = [f"{m.group(1)}{m.group(2)}" for m in COURSE_RE.finditer(group)]
        if not codes:
            continue  # non-course text (e.g. "permission of instructor") — skip
        if not any(c in completed for c in codes):
            return False  # no OR option satisfied for this AND clause

    return True


def is_antireq(prereq_str: str, completed: set[str]) -> bool:
    if not prereq_str:
        return False
    low = prereq_str.lower()
    if "antirequisite" not in low and "cannot enroll" not in low:
        return False
    codes = parse_prereq_codes(prereq_str)
    return any(c in completed for c in codes)


# ── DAG builder ───────────────────────────────────────────────────────────────

def build_dag(courses: list[dict]) -> tuple[dict[str, str], dict[str, list[dict]]]:
    """
    Single O(n) pass over all course entries. Produces:
      prereq_strings: { 'CSE101': 'Prerequisite(s): CSE 20 or CSE 30...' }
                      (raw string kept so any_prereq_branch_satisfied can parse it)
      section_index:  { 'CSE101': [entry1, entry2, ...] }
    """
    prereq_strings = {}
    section_index  = defaultdict(list)

    for entry in courses:
        code, _ = parse_title(entry.get("title", ""))
        if not code:
            continue
        section_index[code].append(entry)
        if code not in prereq_strings:
            prereq_strings[code] = entry.get("prerequisites") or ""

    return prereq_strings, dict(section_index)


# ── Frontier computation ──────────────────────────────────────────────────────

def compute_frontier(
    prereq_strings: dict[str, str],
    completed:      set[str],
    exclude:        set[str],
    major_prefix:   str | None = None,
) -> list[str]:
    """
    Courses that are unlocked (at least one prereq branch satisfied) and
    not yet taken or already queued. Sorted by course number (lower first).
    """
    frontier = []
    for code, prereq_str in prereq_strings.items():
        if code in completed or code in exclude:
            continue
        if major_prefix and not code.startswith(major_prefix):
            continue
        if any_prereq_branch_satisfied(prereq_str, completed):
            frontier.append(code)

    frontier.sort(key=lambda c: int(re.search(r"\d+", c).group()) if re.search(r"\d+", c) else 999)
    return frontier


# ── Best section picker ───────────────────────────────────────────────────────

def pick_best_section(
    sections:    list[dict],
    rmp_cache:   dict,
    completed:   set[str],
    no_early:    bool,
    min_rating:  float,
    is_required: bool,
) -> dict | None:
    candidates = []

    for sec in sections:
        if is_closed(sec.get("title", "")):
            continue

        content    = sec.get("content", "")
        instructor = extract_instructor(content)
        time       = extract_time(content)
        prereq_str = sec.get("prerequisites") or ""

        if not instructor or not time or instructor.lower() == "staff":
            continue
        if no_early and any(t in time for t in ["8:", "08:"]):
            continue
        if is_antireq(prereq_str, completed):
            continue

        rmp    = get_rmp(instructor, rmp_cache)
        rating = rmp["rating"] or 0.0
        candidates.append((rating, sec, instructor, time, rmp))

    if not candidates:
        return None

    candidates.sort(key=lambda x: x[0], reverse=True)
    best_rating, sec, instructor, time, rmp = candidates[0]

    # Required courses: enroll even if the professor rating is low
    if not is_required and best_rating < min_rating:
        return None

    return {
        "title":                  clean_text(sec.get("title", "")),
        "instructor":             instructor,
        "rmp_rating":             rmp["rating"],
        "rmp_difficulty":         rmp["difficulty"],
        "would_take_again_percent": rmp["would_take_again"],
        "time":                   time,
        "prerequisites":          sec.get("prerequisites", ""),
        "units":                  extract_units(sec.get("content", "")),
        "detail_url":             sec.get("detail_url", ""),
    }


# ── Prompt parsing ────────────────────────────────────────────────────────────

def parse_input(user_input: str) -> tuple:
    target_units = 15
    min_rating   = 3.5
    no_early     = False

    if m := re.search(r"(\d+)\s*units?", user_input, re.I):
        target_units = int(m.group(1))
    if any(w in user_input.lower() for w in ["no 8", "no early", "no morning"]):
        no_early = True
    if any(w in user_input.lower() for w in ["easy", "high rated", "good professor"]):
        min_rating = 4.0

    completed_raw  = re.findall(r"[A-Z]{2,4}\s*\d+[A-Z]?", user_input)
    completed_norm = {normalize_code(c) for c in completed_raw if normalize_code(c)}
    return target_units, min_rating, no_early, completed_norm


MAJOR_MAP = {
    "CSE":  ["cs major", "computer science", "cse major", "software", "computing"],
    "MATH": ["math major", "mathematics", "applied math"],
    "BIOL": ["biology major", "bio major"],
    "PHYS": ["physics major"],
    "ECON": ["economics major", "econ major"],
    "BME":  ["biomedical engineering", "bme major"],
    "ECE":  ["electrical engineering", "ece major", "computer engineering"],
}

def detect_major(user_input: str) -> str | None:
    lower = user_input.lower()
    for prefix, keywords in MAJOR_MAP.items():
        if any(kw in lower for kw in keywords):
            return prefix
    return None


# ── Main planner ──────────────────────────────────────────────────────────────

def recommend_schedule(user_input: str) -> list[dict]:
    target_units, min_rating, no_early, completed = parse_input(user_input)
    courses, rmp_cache = load_data()
    major_prefix = detect_major(user_input)

    # Build DAG once — O(n) over all courses
    prereq_strings, section_index = build_dag(courses)

    recommended  = []
    total_units  = 0
    enrolled     = set(completed)   # grows as we simulate enrolling this quarter
    added_codes  = set()

    # ── PASS 1: Walk the major's DAG frontier ────────────────────────────────
    if major_prefix:
        while total_units < target_units:
            frontier = compute_frontier(prereq_strings, enrolled, added_codes, major_prefix)
            if not frontier:
                break

            made_progress = False
            for code in frontier:
                if total_units >= target_units:
                    break

                sections = section_index.get(code, [])
                if not sections:
                    # Not offered this quarter — let successors still unlock
                    enrolled.add(code)
                    added_codes.add(code)
                    continue

                pick = pick_best_section(
                    sections, rmp_cache, completed,
                    no_early, min_rating, is_required=True,
                )
                if pick:
                    recommended.append(pick)
                    added_codes.add(code)
                    enrolled.add(code)
                    total_units += pick["units"]
                    made_progress = True
                else:
                    enrolled.add(code)
                    added_codes.add(code)

            if not made_progress:
                break

    # ── PASS 2: Fill remaining units with electives / other depts ────────────
    if total_units < target_units:
        # Score every unlocked non-major course by best available RMP rating
        elective_pool = []
        all_frontier  = compute_frontier(prereq_strings, enrolled, added_codes)

        for code in all_frontier:
            if major_prefix and code.startswith(major_prefix):
                continue
            sections = section_index.get(code, [])
            if not sections:
                continue
            best_r = max(
                (get_rmp(extract_instructor(s.get("content", "")), rmp_cache)["rating"] or 0.0)
                for s in sections
            )
            elective_pool.append((best_r, code))

        elective_pool.sort(reverse=True)

        for _, code in elective_pool:
            if total_units >= target_units:
                break
            pick = pick_best_section(
                section_index[code], rmp_cache, completed,
                no_early, min_rating, is_required=False,
            )
            if pick:
                recommended.append(pick)
                added_codes.add(code)
                total_units += pick["units"]

    return recommended


# ── CLI ───────────────────────────────────────────────────────────────────────

def run_tool(user_input: str) -> str:
    results = recommend_schedule(user_input)
    return json.dumps(results, indent=2)


if __name__ == "__main__":
    user_input = (
        "I am a computer science major. I want 15 units, "
        "no 8am classes. I have completed CSE20 and MATH19A."
    )
    print(run_tool(user_input))