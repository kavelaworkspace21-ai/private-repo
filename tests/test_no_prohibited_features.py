"""
Doctrine guard (CLAUDE.md §1 + SC AI-Regs reg. 20(d)/(f)): the product must NEVER advertise or build
AI case-outcome prediction / win-probability / bail-or-recidivism risk-scoring. This test fails if any
such language reappears in the UI templates, so the reclassified-PROHIBITED feature can't creep back.
"""
import re
from pathlib import Path

TEMPLATES = Path(__file__).resolve().parent.parent / "app" / "templates"

PROHIBITED_PATTERNS = [
    r"case prediction",
    r"predict (?:the )?case outcome",
    r"predict case outcomes",
    r"win probability",
    r"winning argument",
    r"recidivism",
    r"flight[- ]risk score",
    r"bail eligibility score",
]


def test_ui_has_no_prohibited_prediction_features():
    offenders = []
    for f in sorted(TEMPLATES.glob("*.html")):
        text = f.read_text(encoding="utf-8").lower()
        for pat in PROHIBITED_PATTERNS:
            if re.search(pat, text):
                offenders.append(f"{f.name}: matched /{pat}/")
    assert not offenders, "PROHIBITED prediction/risk-scoring language found in UI: " + "; ".join(offenders)
