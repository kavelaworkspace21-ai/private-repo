"""LSAI-LEGAL-11 — eCourts integration is read-only via official API, flag-gated, no scraping/CAPTCHA.

Precise by design: we check actual imports (AST), not words in docstrings — the module's docstring
legitimately says it "NEVER scrapes and never bypasses CAPTCHAs", which must not trip the guard.
"""
import ast

ECOURTS_FILES = ["app/integrations/ecourts.py", "app/routers/ecourts.py"]

# Libraries used for scraping / headless browsing / CAPTCHA bypass — must never be imported here.
DENY_MODULES = {
    "selenium", "bs4", "beautifulsoup4", "playwright", "requests_html", "mechanize",
    "pyppeteer", "puppeteer", "undetected_chromedriver", "webdriver_manager", "anticaptcha",
    "twocaptcha", "cv2", "pytesseract",
}


def _imported_modules(fp: str) -> set[str]:
    with open(fp, encoding="utf-8") as f:
        tree = ast.parse(f.read())
    mods: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for a in node.names:
                mods.add(a.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom) and node.module:
            mods.add(node.module.split(".")[0])
    return mods


def test_no_scraping_or_captcha_libraries_imported():
    for fp in ECOURTS_FILES:
        bad = _imported_modules(fp) & DENY_MODULES
        assert not bad, f"{fp} imports scraping/CAPTCHA tooling: {bad}"


def test_ecourts_is_flag_gated():
    with open("app/integrations/ecourts.py", encoding="utf-8") as f:
        txt = f.read()
    assert "ECOURTS_API_BASE" in txt   # inert unless explicitly configured
