import re
import sys
import os
sys.path.insert(0, os.path.abspath('.'))
import requests
from bs4 import BeautifulSoup
from app.scraper.parser import PageParser
from app.scraper.extractors import clean_text, StrategyHTMLCards

GENERIC_TITLES = [
    "contact", "about us", "privacy policy", "terms & conditions", "quality control",
    "home", "homepage", "services", "quotes to scrape", "top ten tags", "login", "authors", "tags",
    "company profile"
]

def is_generic_title(title):
    if not title or len(title.strip()) < 2:
        return True
    t_clean = clean_text(title).lower()
    for gt in GENERIC_TITLES:
        if gt == t_clean:
            return True
        if gt in ("quotes to scrape", "top ten tags") and gt in t_clean:
            return True
        if gt == "home":
            if (
                t_clean.startswith(("home -", "home –", "home —", "home |", "home :", "home-", "home–", "home|", "home:", "home page"))
                or t_clean.endswith((" home", "-home", "–home", "|home"))
            ):
                return True
        else:
            if (
                t_clean.startswith((f"{gt} ", f"{gt}-", f"{gt}–", f"{gt}:", f"{gt}|", f"{gt} -", f"{gt} –", f"{gt} |"))
                or t_clean.endswith((f" {gt}", f"-{gt}", f"–{gt}", f"|{gt}", f"- {gt}", f"– {gt}", f"| {gt}"))
            ):
                return True
    return False

# Test 1: Generic title checks
cases = [
    ("Quotes to Scrape", True),
    ("Top Ten tags", True),
    ("Contact", True),
    ("Contact Us", True),
    ("About Us", True),
    ("Company Profile", True),
    ("Daily Contact Lenses", False),
    ("Company Medical Gas Pipeline System", False),
    ("Heavy Duty Electrical Junction Box", False),
    ("A Light in the Attic", False),
    ("Smart Watch Series 5", False),
]

for t, expected in cases:
    res = is_generic_title(t)
    assert res == expected, f"Failed for '{t}': got {res}, expected {expected}"
print("All is_generic_title tests passed!")

# Test 2: Quotes to Scrape HTML parsing
quotes_html = requests.get("https://quotes.toscrape.com/").text
soup = BeautifulSoup(quotes_html, "lxml")

LAYOUT_KEYWORDS = re.compile(
    r"(header|navbar|\bnav\b|sidebar|footer|breadcrumb|pagination|\btags?-box\b|\btag-cloud\b)", re.I
)

candidates = []
for tag in soup.find_all(["article", "li", "div"]):
    if tag.find_parent(["header", "nav", "footer", "aside"]):
        continue
    classes = " ".join(tag.get("class", [])) if tag.get("class") else ""
    id_str = str(tag.get("id", ""))
    if LAYOUT_KEYWORDS.search(classes) or LAYOUT_KEYWORDS.search(id_str):
        continue
    if StrategyHTMLCards.CARD_KEYWORDS.search(classes) or StrategyHTMLCards.CARD_KEYWORDS.search(id_str):
        if tag.find("a") and (tag.find(["h1", "h2", "h3", "h4", "h5", "h6"]) or tag.find("img")):
            candidates.append(tag)

print(f"Candidates found on Quotes to Scrape with layout filter: {len(candidates)}")
assert len(candidates) == 0, f"Expected 0 candidates on Quotes to Scrape, got {len(candidates)}"
print("Quotes to Scrape candidates successfully reduced to 0!")
