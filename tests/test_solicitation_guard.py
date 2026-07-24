"""LSAI-LEGAL-10 — no advertising/solicitation/marketplace surfaces in the UI (Bar Council Rule 36)."""
import glob

FORBIDDEN = [
    "find a lawyer", "find an advocate", "hire a lawyer", "hire an advocate",
    "lawyer marketplace", "legal marketplace", "get more clients", "win more cases",
    "rate your lawyer", "rank lawyer", "rank lawyers", "lead generation", "best lawyer",
    "find clients", "grow your practice with leads",
]


def test_no_solicitation_language_in_ui():
    files = glob.glob("app/templates/*.html") + glob.glob("app/static/*.js")
    assert files, "no UI files found to scan"
    for fp in files:
        with open(fp, encoding="utf-8") as f:
            txt = f.read().lower()
        for phrase in FORBIDDEN:
            assert phrase not in txt, f"solicitation phrase {phrase!r} found in {fp}"
