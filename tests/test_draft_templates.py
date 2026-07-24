"""Reference draft skeletons (templates/drafts/) — the drafting engine's format pack."""
import json
from pathlib import Path

from app.services import draft_templates
from app.routers.ai_drafting import DOCUMENT_TYPES

MANIFEST = Path("templates/drafts/manifest.json")


def test_every_registered_doc_type_has_a_skeleton():
    """Every concrete backend document type must ship an authentic format skeleton."""
    for doc_type in DOCUMENT_TYPES:
        if doc_type == "custom_document":
            continue  # matched dynamically instead
        skel = draft_templates.get_skeleton(doc_type)
        assert skel, f"missing skeleton for {doc_type}"
        assert len(skel) > 300, f"skeleton for {doc_type} too thin"
        assert "[●]" in skel or "[●" in skel, f"skeleton for {doc_type} has no placeholders"


def test_skeletons_carry_correct_statutory_anchors():
    assert "SECTION 138" in draft_templates.get_skeleton("cheque_dishonour").upper()
    assert "FIFTEEN (15)" in draft_templates.get_skeleton("cheque_dishonour")
    assert "SECTION 482" in draft_templates.get_skeleton("anticipatory_bail").upper()
    assert "13B" in draft_templates.get_skeleton("divorce_petition")
    assert "ARTICLE 226" in draft_templates.get_skeleton("writ_petition").upper()


def test_custom_matching_finds_the_right_skeleton():
    hit = draft_templates.match_skeleton("Reply to legal notice received from landlord about rent")
    assert hit and hit[0] == "reply_legal_notice"
    hit = draft_templates.match_skeleton("civil suit plaint for recovery of money from contractor")
    assert hit and hit[0] == "civil_plaint"
    # vague text with no legal signal -> no match (engine then drafts unguided but safely)
    assert draft_templates.match_skeleton("hello world nice weather") is None


def test_manifest_flags_pending_advocate_approval():
    """G8 discipline: templates are NOT self-certified as approved."""
    data = json.loads(MANIFEST.read_text(encoding="utf-8"))
    assert data["_review"]["advocate_approved"] is False


def test_pack_has_full_template_set_and_files_exist():
    """Batch-2 expansion: 26 formats, every manifest file present and substantial."""
    data = json.loads(MANIFEST.read_text(encoding="utf-8"))
    templates = data["templates"]
    assert len(templates) >= 26
    for tid, meta in templates.items():
        f = MANIFEST.parent / meta["file"]
        assert f.exists(), f"missing file for {tid}"
        assert len(f.read_text(encoding="utf-8")) > 300, f"skeleton too thin: {tid}"


def test_new_skeletons_statutory_anchors():
    assert "223" in draft_templates.get_skeleton("complaint_138_ni")          # BNSS cognizance route
    assert "142" in draft_templates.get_skeleton("complaint_138_ni")          # limitation/jurisdiction
    assert "SECTION 144" in draft_templates.get_skeleton("maintenance_application").upper()
    assert "528" in draft_templates.get_skeleton("quash_petition")
    assert "148A" in draft_templates.get_skeleton("caveat_148a")
    assert "SECTION 12" in draft_templates.get_skeleton("dv_application_12").upper()
    assert "372" in draft_templates.get_skeleton("succession_certificate")


def test_matcher_new_types_and_no_generic_word_hijack():
    assert draft_templates.match_skeleton("quash the FIR registered against my client")[0] == "quash_petition"
    assert draft_templates.match_skeleton("rent agreement for a flat, 11 months tenancy")[0] == "rent_agreement"
    assert draft_templates.match_skeleton("maintenance for wife under 125 crpc")[0] == "maintenance_application"
    assert draft_templates.match_skeleton("draft a last will and testament for my client")[0] == "will_simple"
    # ordinary-English "will" must NOT hijack an unrelated request
    hit = draft_templates.match_skeleton("rent agreement — the tenant will pay monthly rent of Rs 20,000")
    assert hit and hit[0] == "rent_agreement"


def test_universal_application_types_registered():
    """The engine covers ANY BNSS/CrPC section and ANY CPC Order via the two
    universal application types — registered end-to-end (backend type + skeleton)."""
    for tid in ("crpc_application", "cpc_application"):
        assert tid in DOCUMENT_TYPES, f"{tid} missing from backend DOCUMENT_TYPES"
        assert "provision" in DOCUMENT_TYPES[tid]["fields"]
        label, skel = draft_templates.resolve_format(tid, {})
        assert label and skel and "PROVISION INVOKED" in skel.upper()
    assert "I.A. No." in draft_templates.get_skeleton("cpc_application")
    assert "BHARATIYA NAGARIK SURAKSHA" in draft_templates.get_skeleton("crpc_application").upper()


def test_provision_lookup_feeds_verbatim_statute():
    """A named provision like 'Section 311 CrPC' must resolve to verbatim corpus text
    (this is what lets applications track the statute's exact language)."""
    import pytest
    from app.ai import rag
    try:
        from app.ai.vector_store import get_collection
        if get_collection().count() == 0:
            pytest.skip("corpus not present")
    except Exception:
        pytest.skip("corpus not present")
    out = rag.retrieve_by_section("Application under Section 311 CrPC to recall a witness")
    assert "VERBATIM TEXT" in out and "311" in out
    out2 = rag.retrieve_by_section("Application under Section 349 of the BNSS")
    assert "349" in out2


def test_chat_draft_intent_detection():
    """Single-prompt drafting in chat: drafting requests flip into draft mode,
    research questions never do."""
    from app.ai.agent import _detect_draft_intent

    is_d, label, skel = _detect_draft_intent(
        "Draft a legal notice for cheque bounce of Rs 5 lakh against ABC Traders")
    assert is_d and label and skel      # matched a skeleton (cheque dishonour family)

    is_d, label, skel = _detect_draft_intent("Prepare a rent agreement for 11 months in Hyderabad")
    assert is_d and label == "Rent / Leave & Licence Agreement"

    # clear intent, but no matching skeleton -> unguided draft mode
    is_d, label, skel = _detect_draft_intent("Draft an adoption deed for my client")
    assert is_d and label is None and skel is None

    # common practitioner phrasing: strong verb + broader noun
    assert _detect_draft_intent("Draft anticipatory bail for my client in FIR 45/2026")[0] is True

    # research questions must NOT flip into drafting
    assert _detect_draft_intent("What is a legal notice and when is it required?")[0] is False
    assert _detect_draft_intent("Explain Section 138 of the NI Act")[0] is False
    assert _detect_draft_intent("write about the law on anticipatory bail")[0] is False


def test_resolve_format_registered_custom_and_none():
    """resolve_format drives both the prompt and the UI transparency chip."""
    label, skel = draft_templates.resolve_format("cheque_dishonour", {})
    assert label == "Cheque Dishonour Notice (s.138 NI Act)" and "SECTION 138" in skel.upper()

    label, skel = draft_templates.resolve_format(
        "custom_document", {"document_title": "Reply to Legal Notice", "instructions": "deny the claim"})
    assert label == "Reply to Legal Notice" and "PARA-WISE REPLY" in skel.upper()

    label, skel = draft_templates.resolve_format("custom_document", {"document_title": "hello", "instructions": "world"})
    assert label is None and skel is None
