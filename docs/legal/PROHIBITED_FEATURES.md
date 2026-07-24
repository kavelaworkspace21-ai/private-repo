# Prohibited Features (LSAI-LEGAL-09)

These AI features are **permanently disabled**. They are barred by CLAUDE.md §1 and the Supreme Court
draft "Regulations for Use of AI in Courts, 2026" (reg. 20(d)/(f)), and are incompatible with the
no-hallucination, human-primacy doctrine.

Encoded as `PROHIBITED_FEATURES` (all `False`) in `app/legal_config.py`. `assert_prohibited_disabled()`
runs at startup and raises if any is enabled. Tests assert they stay False, and
`tests/test_no_prohibited_features.py` greps the UI for prohibited language.

| Flag | Prohibited capability |
|---|---|
| case_prediction | predicting case outcomes |
| win_probability | "win %" / likelihood of success |
| bail_risk_score | scoring bail/flight risk |
| recidivism_risk | re-offending risk scoring |
| witness_credibility_score | scoring witness credibility |
| judge_behavior_prediction | predicting a judge's behaviour |
| automated_filing | autonomous court filing |
| ai_evidence_authenticity | AI asserting evidence is authentic |
| legal_outcome_guarantee | guaranteeing a legal outcome |

## Amendment process
Enabling any flag requires an explicit **Founder + qualified-counsel** constitutional amendment recorded
in the governance amendment log. Until then, code, tests and CI keep them off. There is **no** UI,
route, or endpoint that exposes these capabilities.
