"""The citation gate must WITHHOLD, not warn (Phase 2).

The 22 July audit called this a "citation hard-gate". It was not: enforce_citations
appended a notice and returned the answer, so a fabricated section still reached the
advocate. These tests pin the property that makes it a real gate — content that cannot be
grounded does not come back in `verdict.text`.
"""
from app.ai.answer_gate import (WITHHELD_MESSAGE, AnswerVerdict, split_sentences,
                                validate_answer)

# Retrieved, source-verified material. Only these provisions may be cited.
CONTEXT = "Section 138. Section 141. Section 148."


# ── The core property ───────────────────────────────────────────────────────────
def test_verified_answer_passes_untouched():
    answer = ("Section 138 of the Negotiable Instruments Act penalises dishonour of a "
              "cheque for insufficiency of funds. The complaint must be filed within the "
              "period prescribed. Section 141 extends liability to companies.")
    v = validate_answer(answer, CONTEXT)
    assert v.status == "ok"
    assert v.text == answer
    assert v.blocked is False


def test_fabricated_citation_does_not_survive_into_the_answer():
    """The whole point: the bad section must not be presented as law.

    `body` is the answer proper. The gate's notice below the separator may name the
    rejected citation — an advocate is entitled to know what was dropped — but it is
    framed there as unverified, never asserted.
    """
    answer = ("Section 138 governs cheque dishonour and is well established. "
              "Section 999 additionally requires the drawer to deposit security before "
              "filing, which is a mandatory precondition. "
              "The limitation period is calculated from the date of the notice. "
              "A complaint filed beyond it is liable to be dismissed at threshold.")
    v = validate_answer(answer, CONTEXT)

    assert v.blocked is True
    assert "999" not in v.body, "the fabricated section is still presented as law"
    assert "deposit security" not in v.text, "the fabricated CLAIM survived, not just the number"
    assert "999" in v.unverified


def test_the_notice_never_asserts_the_rejected_provision_exists():
    """Naming it is fine; implying it is real law is not."""
    answer = ("Section 138 governs cheque dishonour in the ordinary course. "
              "Section 999 requires the drawer to deposit security before filing. "
              "The limitation period runs from the date of the statutory notice. "
              "A complaint filed beyond that period is liable to be dismissed.")
    v = validate_answer(answer, CONTEXT)
    notice = v.text[len(v.body):].lower()
    assert "could not be found" in notice
    assert "may not exist" in notice, "the advocate must not infer the provision is real"


def test_repair_keeps_the_grounded_part_of_the_answer():
    answer = ("Section 138 penalises dishonour of a cheque for insufficiency of funds. "
              "Section 999 requires a security deposit before filing. "
              "Notice must be issued within thirty days of the dishonour intimation. "
              "The payee may then file a complaint before the competent magistrate.")
    v = validate_answer(answer, CONTEXT)

    assert v.status == "repaired"
    assert "Section 138 penalises dishonour" in v.body, "sound content should not be thrown away"
    assert "Section 999" not in v.body
    assert len(v.removed_sentences) == 1
    assert "removed" in v.text.lower(), "the advocate must be told something was withheld"


def test_withholds_when_too_little_survives():
    """A two-word stub left after removal reads as a confident answer with no reasoning."""
    answer = ("Yes. Section 999 makes a security deposit mandatory before any complaint "
              "under the cheque-dishonour provisions may be entertained by the magistrate.")
    v = validate_answer(answer, CONTEXT)

    assert v.status == "withheld"
    assert v.text == WITHHELD_MESSAGE
    assert "999" not in v.text


def test_no_retrieved_context_means_every_citation_is_unverified():
    """Fail-closed: with nothing retrieved, nothing is grounded."""
    answer = ("Section 138 of the Negotiable Instruments Act applies here directly. "
              "The drawer is liable to be prosecuted on the payee's complaint. "
              "The magistrate may take cognizance once the statutory notice has expired.")
    v = validate_answer(answer, "")
    assert v.blocked is True
    assert "138" in v.unverified


def test_answer_with_no_citations_at_all_is_not_blocked():
    """Refusals and general guidance cite nothing and must pass cleanly."""
    answer = ("I cannot advise on that without knowing which court the matter is before. "
              "Please tell me the forum and I will look up the applicable provision.")
    v = validate_answer(answer, "")
    assert v.status == "ok"
    assert v.text == answer


def test_empty_answer_is_handled():
    assert validate_answer("", CONTEXT).status == "ok"
    assert validate_answer("   ", CONTEXT).status == "ok"


# ── Sentence splitting must not strand citations ────────────────────────────────
def test_splitter_does_not_break_on_citation_periods():
    """"Section 138." must not split into its own fragment — that would make repair
    remove a bare number while leaving the claim it supported."""
    text = "The rule in Sec. 138 is settled. It applies to post-dated cheques."
    parts = split_sentences(text)
    assert len(parts) == 2, f"expected 2 sentences, got {parts}"
    assert "Sec. 138 is settled" in parts[0]


def test_removal_takes_the_claim_not_just_the_number():
    """Stripping '999' but leaving 'a security deposit is mandatory' would be worse than
    useless — an unsourced legal assertion with the citation filed off."""
    answer = ("Section 138 covers cheque dishonour in the ordinary case. "
              "Under Section 999 a security deposit is mandatory. "
              "The notice period runs from intimation of dishonour by the bank. "
              "Thereafter the payee has a limited window in which to act.")
    v = validate_answer(answer, CONTEXT)
    assert "security deposit is mandatory" not in v.text


# ── The verdict object ──────────────────────────────────────────────────────────
def test_verdict_event_is_compact_and_leaks_no_answer_text():
    answer = "Section 999 requires a deposit. " * 6
    ev = validate_answer(answer, CONTEXT).to_event()
    assert set(ev) == {"status", "unverified", "removed_count", "reason"}
    assert "deposit" not in str(ev.get("reason") or "")
    assert isinstance(ev["removed_count"], int)


def test_blocked_is_true_for_both_repaired_and_withheld():
    assert AnswerVerdict(status="repaired", text="x").blocked is True
    assert AnswerVerdict(status="withheld", text="x").blocked is True
    assert AnswerVerdict(status="ok", text="x").blocked is False
