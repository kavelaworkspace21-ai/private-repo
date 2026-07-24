"""LSAI-LEGAL-04 / 06 — required legal documents exist, are non-empty, and the data map is real."""
import os

LEGAL_DIR = os.path.join("docs", "legal")
REQUIRED = [
    "DATA_MAP_AND_STORE_DISCLOSURE_MATRIX.md", "AI_DATA_POLICY.md",
    "TERMS_OF_SERVICE.md", "PRIVACY_POLICY.md", "ACCEPTABLE_USE_POLICY.md",
    "GRIEVANCE_POLICY.md", "AI_USE_DISCLOSURE_POLICY.md", "RETENTION_POLICY.md",
    "SUBPROCESSOR_REGISTER.md", "LAW_ENFORCEMENT_REQUEST_POLICY.md",
    "PRODUCT_IDENTITY.md", "PROHIBITED_FEATURES.md",
    "AI_SAFETY_POLICY.md", "ADVERTISING_SOLICITATION_POLICY.md",
    "ECOURTS_INTEGRATION_POLICY.md", "ACCESS_CONTROL_AND_ROLES.md",
    "INCIDENT_RESPONSE_POLICY.md", "MISUSE_REPORTING_POLICY.md",
    "BILLING_GST_REFUND_POLICY.md", "APP_STORE_PRIVACY_PACKET.md",
    "LEGAL_REQUEST_REGISTER.md", "HUMAN_SIGNOFF_PACKET.md", "PRE_PUBLISH_LOCK.md",
]


def test_required_legal_docs_exist_and_nonempty():
    for fn in REQUIRED:
        p = os.path.join(LEGAL_DIR, fn)
        assert os.path.exists(p), f"missing {fn}"
        assert os.path.getsize(p) > 200, f"{fn} too small"


def test_data_map_covers_key_categories():
    with open(os.path.join(LEGAL_DIR, "DATA_MAP_AND_STORE_DISCLOSURE_MATRIX.md"), encoding="utf-8") as f:
        t = f.read().lower()
    for cat in ["email", "ip address", "ai prompts", "audit logs", "documents/uploads"]:
        assert cat in t, f"data map missing category: {cat}"
