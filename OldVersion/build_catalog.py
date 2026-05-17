"""
build_catalog.py — Parse the UCSC major-map PDF into major_catalog.json
------------------------------------------------------------------------
Output format:
  {
    "CSE": {
      "CSE20":  { "prereqs": [],                  "required": true  },
      "CSE101": { "prereqs": ["CSE20"],            "required": true  },
      "CSE102": { "prereqs": ["CSE101"],           "required": true  },
      "CSE150": { "prereqs": ["CSE101", "CSE102"], "required": false }
    },
    "MATH": { ... }
  }

Usage:
  pip install pdfplumber --break-system-packages
  python build_catalog.py
  # → writes major_catalog.json

HOW TO ADD A MAJOR
  1. Run the script once with SHOW_TEXT=True to see how UCSC's PDF lays out
     the page for your major — every PDF is slightly different.
  2. Write a parser function (like parse_cse_text) for that major.
  3. Register it in MAJOR_PARSERS.

Note: The HARD_CODED_CATALOG below is a working fallback you can extend
manually if automatic PDF parsing is unreliable for your major.
"""

import json
import re
import pdfplumber

PDF_PATH    = "ucsc_major_map.pdf"
OUTPUT_FILE = "major_catalog.json"
SHOW_TEXT   = False   # set True to debug raw PDF text


# ── Hard-coded fallback (use this until PDF parsing is solid) ─────────────────
# Mirrors the official UCSC CS B.S. major map as of 2025-26.
# Format: { course_code: [list_of_prereqs] }
# Extend this dict as you add more majors.

HARD_CODED: dict[str, dict] = {
    "CSE": {
        # ── Lower division core ──────────────────────────────────────────
        "CSE20":   {"prereqs": [],                         "required": True},
        "CSE30":   {"prereqs": [],                         "required": True},
        "MATH19A": {"prereqs": [],                         "required": True},
        "MATH19B": {"prereqs": ["MATH19A"],                "required": True},
        "MATH23A": {"prereqs": ["MATH19B"],                "required": True},
        "MATH23B": {"prereqs": ["MATH23A"],                "required": True},
        "CSE16":   {"prereqs": [],                         "required": True},
        "CSE40":   {"prereqs": ["CSE30"],                  "required": True},
        # ── Upper division core ──────────────────────────────────────────
        "CSE101":  {"prereqs": ["CSE30", "CSE20"],         "required": True},
        "CSE102":  {"prereqs": ["CSE101"],                 "required": True},
        "CSE103":  {"prereqs": ["CSE101", "CSE16"],        "required": True},
        "CSE110":  {"prereqs": ["CSE40", "CSE101"],        "required": True},
        "CSE111":  {"prereqs": ["CSE110"],                 "required": True},
        "CSE112":  {"prereqs": ["CSE110"],                 "required": True},
        "CSE120":  {"prereqs": ["CSE110"],                 "required": True},
        "CSE130":  {"prereqs": ["CSE101", "CSE30"],        "required": True},
        # ── Electives (sample — add the rest) ───────────────────────────
        "CSE115A": {"prereqs": ["CSE101", "CSE30"],        "required": False},
        "CSE115B": {"prereqs": ["CSE115A"],                "required": False},
        "CSE150":  {"prereqs": ["CSE101", "CSE102"],       "required": False},
        "CSE160":  {"prereqs": ["CSE101"],                 "required": False},
        "CSE183":  {"prereqs": ["CSE110"],                 "required": False},
        "CSE185S": {"prereqs": ["CSE101"],                 "required": False},
    },
    "MATH": {
        "MATH19A":  {"prereqs": [],                        "required": True},
        "MATH19B":  {"prereqs": ["MATH19A"],               "required": True},
        "MATH23A":  {"prereqs": ["MATH19B"],               "required": True},
        "MATH23B":  {"prereqs": ["MATH23A"],               "required": True},
        "MATH100":  {"prereqs": ["MATH23B"],               "required": True},
        "MATH101":  {"prereqs": ["MATH100"],               "required": True},
        "MATH103A": {"prereqs": ["MATH23B"],               "required": True},
        "MATH110":  {"prereqs": ["MATH23B"],               "required": False},
        "MATH117":  {"prereqs": ["MATH23B"],               "required": False},
        "MATH128A": {"prereqs": ["MATH23B"],               "required": False},
    },
}


# ── PDF-based parser (auto-extraction from the official major-map PDF) ────────

def extract_course_codes(text: str) -> list[str]:
    """Pull every CSE/MATH/etc. course code from a block of text."""
    return re.findall(r"\b([A-Z]{2,4})\s*(\d+[A-Z]?)\b", text)


def parse_cse_text(text: str) -> dict:
    """
    UCSC's CS major-map PDF typically lists courses as:
        CSE 20 — Introduction to Discrete Mathematics
        Prerequisite: none
        ...
        CSE 101 — Introduction to Analysis of Algorithms
        Prerequisite: CSE 20, CSE 30

    Adjust the regex patterns if your PDF uses different formatting.
    """
    catalog = {}
    # Split on section headers that look like "CSE NNN"
    chunks = re.split(r"(?=\bCSE\s+\d+)", text)
    for chunk in chunks:
        header = re.match(r"CSE\s+(\d+[A-Z]?)", chunk)
        if not header:
            continue
        code = f"CSE{header.group(1)}"

        # Try to find prereq line
        prereq_match = re.search(
            r"[Pp]rerequisite[s]?\s*[:\-]?\s*([^\n]+)", chunk
        )
        prereqs = []
        if prereq_match:
            raw = prereq_match.group(1)
            if "none" not in raw.lower():
                for prefix, num in extract_course_codes(raw):
                    prereqs.append(f"{prefix}{num}")

        catalog[code] = {"prereqs": prereqs, "required": True}
    return catalog


MAJOR_PARSERS = {
    "CSE": parse_cse_text,
    # "MATH": parse_math_text,  ← add parsers for other majors here
}


def build_from_pdf(pdf_path: str) -> dict:
    """Extract all text from the PDF and run each major's parser over it."""
    catalog = {}
    try:
        with pdfplumber.open(pdf_path) as pdf:
            full_text = "\n".join(
                page.extract_text() or "" for page in pdf.pages
            )
        if SHOW_TEXT:
            print(full_text[:4000])

        for major, parser in MAJOR_PARSERS.items():
            parsed = parser(full_text)
            if parsed:
                catalog[major] = parsed
                print(f"  PDF → {major}: {len(parsed)} courses extracted")
    except FileNotFoundError:
        print(f"  ⚠️  {pdf_path} not found — falling back to hard-coded catalog")
    return catalog


def main():
    print("🗂️  Building major catalog…")
    # Start with the hard-coded baseline
    catalog = {k: dict(v) for k, v in HARD_CODED.items()}

    # Overlay with PDF-extracted data (PDF wins if both exist for a major)
    pdf_catalog = build_from_pdf(PDF_PATH)
    for major, data in pdf_catalog.items():
        catalog[major] = data

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(catalog, f, indent=2, ensure_ascii=False)

    total = sum(len(v) for v in catalog.values())
    print(f"✅  Wrote {OUTPUT_FILE} — {len(catalog)} majors, {total} courses total")


if __name__ == "__main__":
    main()