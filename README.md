🐌 SlugPlanner
NVIDIA OpenClaw Hackathon | Team: Maven Lam & Alan Xiong

🛑 The Problem
Planning a course schedule at UCSC is a massive headache. Students are forced to keep 50 tabs open to cross-reference MyUCSC class searches, the official degree catalog for prerequisites, and RateMyProfessor (RMP) for instructor quality. Worse, if you blindly chase "easy" classes, you might miss a critical prerequisite and delay your graduation.

💡 The Solution
SlugPlanner is an intelligent, agent-driven course scheduling assistant. It doesn't just blindly scrape data; it calculates your exact academic "Frontier," proving you are eligible for a class before it ever looks at professor ratings. Tell the agent your major, what you've taken, and your preferences (e.g., "15 units, easy professors, no 8 AMs"), and it will mathematically guarantee the best possible path forward.

⚙️ How It Works (The Pipeline)
SlugPlanner operates on a multi-stage data ingestion and reasoning pipeline:

The PISA Scraper (my_ucsc_scanner.py): Uses Playwright to navigate the live MyUCSC class search, capturing currently offered courses, times, and instructor assignments.

The Catalog Grapher (catalog_scraper.py): Directly targets the UCSC CourseLeaf catalog, reading raw HTML text to map out the exact sequence of mandatory core classes and electives for multiple majors (B.S., B.A., Applied Math, etc.).

The RMP Oracle (rmp_scouter.py): Enriches the scraped courses with difficulty and quality scores by querying the RateMyProfessor database.

The Planning Agent (agent.py): Takes user input, evaluates the boolean logic of prerequisites, calculates the valid academic frontier, and outputs a highly optimized, conflict-free schedule.

🚀 Technical Highlights (Why It's Cool)
Topological Graph Traversal: Instead of using a slow, "greedy" search that evaluates every class, the agent uses a Dependency Graph. It calculates the Frontier (the immediate next steps unlocked by your completed classes) and only processes those. This drops the computational load and ensures graduation progress.

Boolean Prerequisite Engine: University catalogs use messy text like "CSE 12; and CSE 13S or ECE 16". We built a custom logic engine (check_prereq.py) that converts these strings into safe Python boolean expressions to instantly evaluate student eligibility.

Bypassing Cloudflare via GraphQL: Scraping RMP with a standard browser is slow and triggers IP bans (403 Forbidden). We reverse-engineered RMP's frontend to hit their hidden public GraphQL API directly. By injecting disguised browser headers and implementing a local cache (rmp_cache.json), we achieve instant data retrieval with zero IP bans.

🛠️ Quickstart / How to Run
1. Generate the Course Data
python my_ucsc_scanner.py

2. Map the Degree Pathways
python catalog_scraper.py

3. Fetch RMP Ratings (Caches automatically!)
python rmp_scouter.py

4. Ask the Agent for a Schedule
python slug_tool.py "I am a CS BS major. I want 15 units, no early classes, and easy professors. I have completed CSE 20, CSE 30, and MATH 19A."