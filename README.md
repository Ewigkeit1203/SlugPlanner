# SlugPlanner
Nvidia Hack a Claw Hackathon Team project by Maven Lam, and Alan Xiong

Purpose:
When we are planing the course ahead, we are always going to jump between MyUCSC and RMP. It's not convenient at all. 
This tool is going to get all info from myUCSC class search, about (Prof Name, units...) Then go RMP for score, base all the info give you a recommend schedule.

How it works:
1. It will scrape all information from MyUCSC class search, get all information about Professor's name, units...
2. It will go to UCSC class Catalog, then get all the prequistes
3. It goes to RMP and scrape all information including quality and difficulty score of professor.
4. After comparing all the information, it will give user recommend schedule based on the user's prompt.

Challenges:
IP blockage:
RMP have anti craping script, there might be issue when we are craping the whole website and get banned.

How to solve:
Add time delay, try to make it like human operation.
