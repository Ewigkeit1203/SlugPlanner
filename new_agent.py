"""
UCSC Course Planner — DAG-based scheduling agent
-------------------------------------------------
Key improvement over the original brute-force filter loop:

  1. Parse the major requirement PDF into a prerequisite DAG once.
  2. Mark nodes "completed" using the student's course history.
  3. Compute a topological frontier — only the courses whose prereqs
     are fully satisfied (the next legal moves).
  4. Greedily pick from the frontier by RMP rating, not by scanning
     every course in the scraped list.

This is O(frontier) per pass instead of O(all_courses), and it
naturally respects the catalog's intended course progression.
"""

import json
import re
from collections import defaultdict, deque
from check_prereq import check_prerequisites


# ── Data loading ──────────────────────────────────────────────────────────────

def load_data():
    courses   = json.load(open("ucsc_courses_with_preq.json"))
    rmp_cache = json.load(open("rmp_cache.json"))
    catalog   = json.load(open("major_catalog.json"))   # see build_catalog.py
    return courses, rmp_cache, catalog


# ── Text utilities ────────────────────────────────────────────────────────────

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
    """'CSE 101' → 'CSE101'"""
    return raw.replace(" ", "").upper()


# ── Field extractors ──────────────────────────────────────────────────────────

def extract_instructor(content: str) -> str | None:
    lines = content.splitlines()
    for idx, line in enumerate(lines):
        if re.match(r"^\s*Instructor\s*:\s*$", line, re.I):
            for next_line in lines[idx + 1:]:
                candidate = clean_text(next_line.strip())
                if candidate:
                    return candidate
            return None
        if "Instructor:" in line:
            parts = line.split(":", 1)
            if len(parts) > 1 and parts[1].strip():
                return clean_text(parts[1])
    return None


def extract_time(content: str) -> str | None:
    for line in content.splitlines():
        if any(day in line for day in ["MWF", "TuTh", "MW", "TTh", "Mon", "Tue"]):
            return clean_text(line)
    return None


def extract_units(content: str) -> int:
    # Try to parse the actual unit count; fall back to 5
    m = re.search(r"(\d+)\s*[Uu]nits?", content)
    return int(m.group(1)) if m else 5


# ── RMP lookup ────────────────────────────────────────────────────────────────

def get_rmp_data(instructor: str | None, rmp_cache: dict) -> dict:
    if instructor and instructor in rmp_cache:
        data = rmp_cache[instructor]
        if isinstance(data, dict) and (data.get("status") == "ok" or "avg_rating" in data):
            return {
                "rating":          data.get("avg_rating")              or data.get("rating"),
                "difficulty":      data.get("avg_difficulty")          or data.get("difficulty"),
                "would_take_again": data.get("would_take_again_percent") or data.get("would_take_again"),
            }
    return {"rating": None, "difficulty": None, "would_take_again": None}


# ── Prompt parsing ────────────────────────────────────────────────────────────

def parse_input(user_input: str) -> tuple:
    target_units = 15
    min_rating   = 3.5
    no_early     = False

    if m := re.search(r"(\d+)\s*units?", user_input, re.I):
        target_units = int(m.group(1))
    if any(w in user_input.lower() for w in ["no 8", "no early", "no morning"]):
        no_early = True
    if any(w in user_input.lower() for w in ["easy", "good professor", "high rated"]):
        min_rating = 4.0

    completed_raw  = re.findall(r"[A-Z]{2,4}\s*\d+[A-Z]?", user_input)
    completed_norm = [normalize_code(c) for c in completed_raw]
    return target_units, min_rating, no_early, completed_norm


def detect_major(user_input: str) -> str | None:
    major_map = {
        "CSE":  ["cs major", "computer science", "cse major", "software", "computing"],
        "MATH": ["math major", "mathematics", "applied math"],
        "BIOL": ["biology major", "bio major"],
        "PHYS": ["physics major"],
        "ECON": ["economics major", "econ major"],
    }
    lower = user_input.lower()
    for prefix, keywords in major_map.items():
        if any(kw in lower for kw in keywords):
            return prefix
    return None


# ── DAG / catalog logic ───────────────────────────────────────────────────────

def build_dag(catalog: dict, major_prefix: str) -> tuple[dict, dict]:
    """
    Parse the major catalog for a given prefix and return:
      prereq_map  : { 'CSE101': ['CSE20', 'MATH19A'], ... }
      successor_map: { 'CSE20': ['CSE101', 'CSE102'], ... }  (reverse edges)

    The catalog JSON is expected to look like:
      {
        "CSE": {
          "CSE20":  { "prereqs": [] },
          "CSE101": { "prereqs": ["CSE20"] },
          ...
        }
      }
    """
    courses_in_major = catalog.get(major_prefix, {})
    prereq_map    = {}   # course → list of prereqs
    successor_map = defaultdict(list)

    for code, meta in courses_in_major.items():
        code_norm = normalize_code(code)
        prereqs   = [normalize_code(p) for p in meta.get("prereqs", [])]
        prereq_map[code_norm] = prereqs
        for p in prereqs:
            successor_map[p].append(code_norm)

    return prereq_map, dict(successor_map)


def compute_frontier(prereq_map: dict, completed: set[str]) -> list[str]:
    """
    Return all courses in the DAG that are immediately takeable:
    every prereq is in `completed` and the course itself is not yet completed.
    Sorted by course number so lower-level courses come first within the same tier.
    """
    frontier = []
    for code, prereqs in prereq_map.items():
        if code in completed:
            continue
        if all(p in completed for p in prereqs):
            frontier.append(code)

    frontier.sort(key=lambda c: int(re.search(r"\d+", c).group()) if re.search(r"\d+", c) else 999)
    return frontier


# ── Course section index ──────────────────────────────────────────────────────

def build_section_index(courses: list[dict]) -> dict[str, list[dict]]:
    """
    Group scraped course sections by normalized course code so we can quickly
    find all sections of e.g. 'CSE101' without scanning the full list.
    """
    index = defaultdict(list)
    for course in courses:
        m = re.search(r"[A-Z]{2,4}\s*\d+[A-Z]?", course.get("title", ""))
        if m:
            index[normalize_code(m.group())].append(course)
    return dict(index)


# ── Best section picker ───────────────────────────────────────────────────────

def best_section(
    sections:   list[dict],
    rmp_cache:  dict,
    completed:  set[str],
    no_early:   bool,
    min_rating: float,
    is_required: bool,
) -> dict | None:
    """
    Among all sections of a single course, return the one with the highest
    RMP rating that passes all hard constraints.

    If the course is required (is_required=True) and no section clears the
    rating bar, we still return the best available so the student can graduate.
    """
    candidates = []

    for sec in sections:
        content    = sec.get("content", "")
        instructor = extract_instructor(content)
        time       = extract_time(content)
        prereqs    = sec.get("prerequisites", "None")

        # Hard: need a real instructor and meeting time
        if not instructor or not time or instructor.lower() == "staff":
            continue

        # Hard: no 8 AM if requested
        if no_early and time and any(t in time for t in ["8:", "08:"]):
            continue

        # Hard: antirequisite check
        if completed and any(c in prereqs for c in completed):
            if "cannot enroll" in prereqs.lower() or "antirequisite" in prereqs.lower():
                continue

        # Hard: prerequisite engine (belt-and-suspenders; DAG already filtered)
        if completed and not check_prerequisites(prereqs, completed):
            continue

        rmp    = get_rmp_data(instructor, rmp_cache)
        rating = rmp["rating"] or 0.0
        candidates.append((rating, sec, instructor, time, rmp))

    if not candidates:
        return None

    # Sort by rating descending
    candidates.sort(key=lambda x: x[0], reverse=True)
    best_rating, best_sec, best_instr, best_time, best_rmp = candidates[0]

    # Soft: rating gate (skip for required courses so the student can graduate)
    if not is_required and best_rating < min_rating:
        return None

    content = best_sec.get("content", "")
    return {
        "title":                  clean_text(best_sec.get("title", "")),
        "instructor":             best_instr,
        "rmp_rating":             best_rmp["rating"],
        "rmp_difficulty":         best_rmp["difficulty"],
        "would_take_again_percent": best_rmp["would_take_again"],
        "time":                   best_time,
        "prerequisites":          best_sec.get("prerequisites", "None"),
        "units":                  extract_units(content),
        "detail_url":             best_sec.get("detail_url", ""),
    }


# ── Main planner ──────────────────────────────────────────────────────────────

def recommend_schedule(user_input: str) -> list[dict]:
    target_units, min_rating, no_early, completed_norm = parse_input(user_input)
    courses, rmp_cache, catalog = load_data()
    major_prefix = detect_major(user_input)

    completed = set(completed_norm)
    section_index = build_section_index(courses)

    recommended = []
    total_units  = 0
    seen_titles  = set()

    # ── PASS 1: Walk the major DAG ────────────────────────────────────────────
    if major_prefix and major_prefix in catalog:
        prereq_map, _ = build_dag(catalog, major_prefix)

        # Iterative frontier expansion: after we "enroll" in a course we treat
        # it as completed for downstream frontier calculations, letting us chain
        # e.g. CSE101 → unlocks CSE102 in the same quarter if units allow.
        simulated_completed = set(completed)  # don't mutate the original
        visited = set()

        while total_units < target_units:
            frontier = compute_frontier(prereq_map, simulated_completed)
            # Remove already-visited or recommended courses
            frontier = [c for c in frontier if c not in visited]

            if not frontier:
                break  # no more courses unlock in this major

            made_progress = False
            for code in frontier:
                if total_units >= target_units:
                    break
                visited.add(code)

                sections = section_index.get(code, [])
                if not sections:
                    # Course is in catalog but not offered this term — skip
                    # but don't block it from unlocking successors
                    simulated_completed.add(code)
                    continue

                pick = best_section(
                    sections, rmp_cache, completed,
                    no_early, min_rating, is_required=True,
                )
                if pick and pick["title"] not in seen_titles:
                    recommended.append(pick)
                    seen_titles.add(pick["title"])
                    total_units += pick["units"]
                    # Simulate enrolling so successors can unlock next iteration
                    simulated_completed.add(code)
                    made_progress = True

            if not made_progress:
                break  # frontier exists but nothing passes constraints; stop

    # ── PASS 2: Fill remaining units with electives / GEs ────────────────────
    if total_units < target_units:
        # Gather every section NOT in the major prefix, sorted by RMP rating
        other_sections = [
            c for c in courses
            if major_prefix not in c.get("title", "")
        ]
        # Sort by rating so we evaluate best options first
        other_sections.sort(
            key=lambda x: get_rmp_data(extract_instructor(x.get("content", "")), rmp_cache)["rating"] or 0,
            reverse=True,
        )

        for sec in other_sections:
            if total_units >= target_units:
                break

            m = re.search(r"[A-Z]{2,4}\s*\d+[A-Z]?", sec.get("title", ""))
            if not m:
                continue
            code = normalize_code(m.group())

            pick = best_section(
                [sec], rmp_cache, completed,
                no_early, min_rating, is_required=False,
            )
            if pick and pick["title"] not in seen_titles:
                recommended.append(pick)
                seen_titles.add(pick["title"])
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