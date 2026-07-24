# LegalServer.AI — Advocate Workbench Sprint Pack (LSAI-WB)
_Version 1.0 · For Claude Code execution · Place at `docs/sprints/LSAI_ADVOCATE_WORKBENCH_SPRINTS.md`_

> **Governance.** This pack runs under the Master Agent constitution and `CLAUDE.md`. Read both, plus `docs/STATUS.md`, before starting. All doctrine applies unchanged: no source → no legal answer · citation hard-gate · confidence labels · every artifact starts `DRAFT_FOR_ADVOCATE_REVIEW` · tenant isolation · AuditLog on every mutation · banned phrases never appear · no eCourts scraping · no secrets in repo.
>
> **Prerequisite:** the latest repo truth refresh (LSAI-V3-00) must be complete. If `docs/STATUS.md` is stale or unverified, run it first. Do not start feature work on an unverified baseline.

---

## 1. What this pack builds — the Advocate Workbench

A single **Workbench** hub inside LegalServer.AI giving advocates six guided, source-grounded tools. Together they cover the five workflows advocates currently run as manual ChatGPT prompts, plus full feature parity with Draft Bot Pro — all inside our practice OS, linked to Matters, the Court Diary, and the review workflow.

| # | Tool | What it does |
|---|------|--------------|
| 1 | **Case File Analysis** | Upload a case file → guided intake questions → 15-section senior-advocate analysis |
| 2 | **Guided Drafting** (upgrade of existing engine) | Question-first drafting from typed facts or reference PDFs, with side-by-side research panel and in-app editor |
| 3 | **Deep Research** | Guided research pack: questions → keywords → provisions → SC/HC authorities → conflicting views → current position → court-ready note / legal memo |
| 4 | **Judgment Analyzer** | Upload a judgment → intake (side, relief, court, intended use) → ratio/obiter/holding, quotable passages, how to use it, how it may be distinguished |
| 5 | **Argument Studio** (new page — founder-requested) | Build full argument packs from a Matter, uploaded case details, **or selected citations/judgments** — including hearing notes and Judge Mode |
| 6 | **Chat with Case File** | Ask questions of any uploaded PDF, generate a List of Dates & Events, summarise — with source-highlighted answers |

**Positioning:** Draft Bot Pro sells tools. We sell the same tools *inside the advocate's practice* — every artifact can attach to a Matter, feed the Court Diary, pass through advocate review, and live in the firm workspace. That is the moat; this pack closes the feature gap so the moat can win.

---

## 2. Competitive parity map (verified 2026-07 via web research)

| Draft Bot Pro feature | Our implementation | Sprint |
|---|---|---|
| Draft any document from typed facts or uploaded reference PDFs; agentic format selection | Guided Drafting upgrade: intake-first, reference-PDF grounding, template + free-form formats | WB-07 |
| Research Panel beside the draft (AI overview, provisions, landmark/similar judgments, recent developments) | Side-by-side Research Panel fed by our library (verbatim statutes) + Indian Kanoon (live case law) | WB-07 |
| Natural-language research, source-backed, click-and-read judgments, "does not make up cases" | Already live (grounded chat + Kanoon cards); Deep Research pack adds the structured output | WB-04 |
| Chat with PDF (up to ~600 pages): questions, summaries, **List of Dates** | Chat with Case File + List of Dates generator; large-PDF chunked extraction | WB-02 |
| Click a reference → highlights source text in the PDF | Store page/offset anchors per answer; UI shows the source snippet | WB-02 |
| Generate arguments **and counter-arguments** from PDF or typed facts | Argument Studio (both sides, all cited) | WB-06 |
| Legal memo from a topic (headings, references, judgments) | Memo output type in Deep Research | WB-04 |
| In-app editor: expand / shorten / reword / change tone / add clauses; download Word/PDF | Editor actions on drafts + artifact exports | WB-07, WB-08 |
| Draft history | Artifact Library (versioned, tenant-scoped) | WB-08 |
| Review Your Draft / start from Empty Document | Upload-own-draft review mode + blank editor entry | WB-07 |
| Files auto-delete in 7 days (privacy) | Configurable retention on Workbench scratch uploads (default 7-day auto-delete unless saved to a Matter) | WB-02 |
| Never trains on user data | Already policy (consent screen + constitution) | — |

**Where we go beyond them (already ours):** Matter & client linkage, Court Diary + deadline reminders, firm workspace with RBAC, verbatim statute library with provenance (SHA-256 + source URL), advocate-review workflow with approval gating, audit log, confidence labels, tenant isolation, draft versioning.

---

## 3. Workbench safety rules (additions to the doctrine — enforce with tests)

1. **Question-first, always.** Every workflow opens in INTAKE and must not generate until required intake fields are answered or the user explicitly confirms "proceed with stated assumptions" (assumptions are then listed in the artifact). This mirrors the "do not analyse immediately" discipline.
2. **No outcome prediction or risk scoring — ever.** "Strengths", "Weaknesses", "Vulnerabilities", and "Litigation Risk Factors" are qualitative preparation notes tied to cited facts/law. Never output win/loss predictions, percentages, probabilities, or scores. If asked "will I win?", refuse with the standard doctrine response. (Aligns with the banned-phrase list and the Supreme Court draft AI-in-courts norms.)
3. **Per-section grounding.** Each artifact section declares its grounding: `FILE` (cites the uploaded document with page refs), `LAW` (cites statutes/judgments from library/Kanoon), or `BOTH`. A legal proposition without a LAW citation is blocked by the existing citation hard-gate.
4. **Quotable passages are verbatim.** "Key Quotable Passages" must be exact text from the retrieved judgment with pinpoint paragraph/page reference and link. Paraphrase presented as quotation is a test failure.
5. **Good-law caveat.** Judgment Analyzer surfaces the existing treatment caveat; never assert "still good law" without verified treatment signal.
6. **Both-sides fairness.** Counter-arguments and "Opposing Counsel's Best Arguments" are generated with the same citation discipline as the advocate's own side.
7. **Every artifact:** confidence label, `DRAFT_FOR_ADVOCATE_REVIEW` status, the standard review disclaimer, `source_ids`, `AuditLog` row, `UsageEvent` row (counts against plan AI limits).
8. **Uploads are tenant-scoped** and never readable across tenants; scratch uploads follow the retention policy; anything saved to a Matter becomes a versioned Document.

---

## 4. Shared architecture (build once in WB-01, reuse everywhere)

**Workflow engine** — a small state machine per session:
`INTAKE → CONFIRM → GENERATING → COMPLETE` (+ `REFUSED` when sources are missing).

**New tables** (SQLAlchemy models; fold into Alembic when the Postgres migration sprint lands):
- `WorkflowSession`: id, tenant_id, user_id, matter_id (nullable), workflow_type, state, intake_json, assumptions_json, created_at, updated_at
- `WorkflowArtifact`: id, tenant_id, session_id, artifact_type, version, content_json (ordered sections), citations_json, confidence, review_status (default `DRAFT_FOR_ADVOCATE_REVIEW`), approved_by, approved_at
- `WorkbenchUpload`: id, tenant_id, user_id, session_id (nullable), filename, page_count, extracted_text_ref, anchors_ref (page/char offsets), retention_policy, delete_after

**Reuse:** `AiQuery/AiAnswer/Citation`, `app/ai/safety.py` (refusal, banned phrases, confidence), citation hard-gate, `AuditLog`, `UsageEvent`, `DocumentVersion`, export pipeline.

**API surface (tenant-scoped, JWT):**
```
POST /api/workbench/uploads                      # PDF upload + extraction
POST /api/workbench/sessions                     # {workflow_type, matter_id?, upload_ids?}
GET  /api/workbench/sessions/{id}                # state + next intake questions
POST /api/workbench/sessions/{id}/answers        # submit intake answers
POST /api/workbench/sessions/{id}/generate       # runs pipeline, returns artifact
GET  /api/workbench/artifacts/{id}               # fetch artifact (sections + citations)
POST /api/workbench/artifacts/{id}/export        # DOCX/PDF with AI disclosure
POST /api/workbench/artifacts/{id}/save-to-matter
GET  /api/workbench/artifacts?matter_id=...      # artifact library
```

**Frontend:** one new nav item **Workbench** → tile hub (6 tools, black + gold theme), each tool a guided page: intake chat/form → generation progress → sectioned artifact view with citation cards → actions (export, save to matter, send to review).

**Prompt contracts:** one file per workflow in `/ai/prompts/workbench/`, each embedding the AI Answer Safety Contract + the section schema below. Prompts are data, reviewed at Gate G8.

---

## 5. Artifact section schemas (encode exactly; these are the product)

**W1 · Case File Analysis** — intake: parties/side, court & stage, relief context, then AI asks every material missing-fact question. Sections: Facts Summary · Chronology of Events · Legal Issues · Questions of Fact · Questions of Law · Strengths of the Case · Weaknesses of the Case · Missing Evidence · Limitation Issues · Jurisdiction Issues · Maintainability Concerns · Possible Remedies · Litigation Risk Factors (qualitative) · Further Documents Required · Suggested Litigation Strategy. (Strategy items can be turned into Diary tasks in WB-08.)

**W2 · Guided Drafting (pre-draft checklist)** — intake until sufficient: missing facts · missing documents · procedural requirements · legal issues · drafting strategy. Draft must ensure: strong factual foundation · correct pleadings · necessary averments · proper cause of action · jurisdiction pleadings · limitation compliance · effective relief clause.

**W3 · Deep Research** — intake: jurisdiction · applicable statute · stage · relief sought · issues. Sections: Research Questions · Search Keywords · Relevant Statutory Provisions (verbatim from library) · Procedural Provisions · Leading Supreme Court Authorities · Relevant High Court Authorities · Conflicting Views · Current Legal Position · Court-Ready Research Note. Alternate output type: **Legal Memo** (topic → structured memo with references). Application to the supplied facts, not bare case lists.

**W4 · Judgment Analyzer** — intake: which side am I appearing for · relief sought · issue being researched · which court · intended use. Sections: One-Page Summary · Material Facts · Issues Before the Court · Ratio Decidendi · Obiter Dicta · Final Holding · Key Quotable Passages (verbatim + pinpoint) · Practical Application · How This Judgment Helps My Case · How Opposing Counsel May Distinguish It · Weaknesses in Relying Upon It · Court-Ready Research Note · 2-Minute Courtroom Explanation. Usage-focused, never a bare summary.

**W5 · Argument Studio** — entry modes: (a) pick a Matter, (b) upload case details/files, (c) **select judgments/citations** from research history, Kanoon results, or uploaded judgment PDFs. Intake: facts · procedural history · relief sought · applicable law · available evidence · opponent's case · stage. Sections: Theory of the Case · Issues for Determination · Strongest Facts · Relevant Statutory Provisions · Leading Authorities · Sequence of Oral Arguments · Anticipated Questions from the Bench · Opposing Counsel's Best Arguments · Rebuttals to Each · Vulnerabilities in My Case · Relief-Oriented Submissions · **5-Minute Hearing Note** · **15-Minute Detailed Argument Note** · **One-Page Court Note**. Plus **Judge Mode**: the 10 toughest questions likely from the Bench, each with a persuasive, cited response. Counter-argument generation (for-and-against) included.

**W6 · Chat with Case File** — free-form Q&A over an upload; every answer anchored to page/offset so the UI highlights the source. One-tap generators: **List of Dates & Events** (court-format chronology) · Document Summary · "Questions this file doesn't answer".

---

## 6. Sprint sequence

Run strictly in order. Every sprint ends with passing tests, the e2e journey green, and a STATUS.md update + session report per `CLAUDE.md`.

### LSAI-WB-00 — Baseline & scaffolding
**Goal:** verified start + skeleton. **Build:** confirm STATUS baseline; create `app/routers/workbench.py`, `app/services/workbench/`, `/ai/prompts/workbench/`; add the three models; Workbench nav tile page (empty tiles). **Tests:** models create; router mounts; nav renders; tenant scoping on empty endpoints. **Done when:** skeleton merged, suite green.

### LSAI-WB-01 — Workflow engine core
**Goal:** the reusable spine. **Build:** session state machine; intake framework (required-question schema per workflow, "proceed with assumptions" path); generation pipeline that renders sections one by one through the citation hard-gate; artifact persistence + versioning; AuditLog + UsageEvent on generate; entitlement check hook (blocks at plan limit with upgrade payload). **Tests:** cannot generate from INTAKE; assumption path records assumptions; uncited legal section blocked; usage counted; cross-tenant session access → 404. **Done when:** a dummy workflow runs end-to-end under all gates.

### LSAI-WB-02 — Uploads, Chat with Case File, List of Dates
**Goal:** document intelligence parity. **Build:** PDF upload + chunked extraction (large files; page/char anchors); retention policy (default 7-day auto-delete for scratch uploads, delete job in worker; persists if saved to Matter); Chat endpoint answering ONLY from the file (refuses beyond it, or routes legal questions through the research gate); source-highlight anchors returned with every answer; List of Dates generator (court chronology format, exportable). **Tests:** answer cites page anchors; question outside the file → grounded refusal or law-gated answer; retention job deletes on schedule; tenant isolation on uploads. **Done when:** an advocate can upload a 300+ page file, ask questions with highlighted sources, and export a List of Dates.

### LSAI-WB-03 — Case File Analysis workflow
**Goal:** W1 live. **Build:** intake question set; 15-section schema; FILE/LAW grounding per section; strengths/weaknesses/risk sections rendered qualitatively with the no-prediction guard; artifact view UI. **Tests:** all sections present; limitation/jurisdiction sections carry LAW citations; "will I win?" during session → refusal; banned phrases absent; artifact starts in review status. **Done when:** full analysis generates from a real sample file and passes gates.

### LSAI-WB-04 — Deep Research workflow + Legal Memo
**Goal:** W3 live. **Build:** intake; research pack sections wired to library (verbatim provisions) + Kanoon (SC/HC authorities, conflicting views); Current Legal Position with good-law caveat; Court-Ready Research Note; Memo output type; save-to-research-history. **Tests:** every authority resolves to a real Kanoon link; provisions match library verbatim text; conflicting-views section only appears with sources on both sides; refusal when corpus lacks the topic. **Done when:** a research pack and a memo generate fully cited.

### LSAI-WB-05 — Judgment Analyzer
**Goal:** W4 live. **Build:** judgment upload or Kanoon-pick as source; intake; 13-section schema; verbatim quotable passages with pinpoint refs; helps/distinguish/weakness sections; 2-minute explanation; treatment caveat. **Tests:** quotables are exact substrings of the source text; no section asserts good-law without treatment data; grounding limited to the judgment + cited law. **Done when:** analyzer output verified against a known judgment.

### LSAI-WB-06 — Argument Studio (new page)
**Goal:** W5 live — the founder-requested arguments page. **Build:** three entry modes (Matter / upload / selected citations & judgments); intake; full section schema incl. the three hearing notes; Judge Mode (10 toughest questions + cited responses); counter-argument generation; citation picker UI that pulls from research history, Kanoon results, and analyzed judgments. **Tests:** both sides' propositions cited; Judge-mode responses cited; no prediction language (regex + eval); entry from selected citations produces arguments grounded ONLY in those sources + library; entitlements counted. **Done when:** an advocate can go from a Matter or a set of judgments to a complete, cited argument pack with hearing notes.

### LSAI-WB-07 — Drafting engine parity upgrade
**Goal:** W2 + editor parity. **Build:** question-first intake in front of existing drafting; reference-PDF-grounded drafting; pre-draft checklist artifact; side-by-side Research Panel on the drafting page (auto-fetched from draft context); editor actions: expand/shorten/reword selection, tone change, add clause; upload-own-draft **Review mode** (issues, missing averments, limitation/jurisdiction flags — advisory, cited); Empty Document entry; draft history view. **Tests:** draft never generates with unanswered required intake; review-mode flags cite law; editor actions preserve review status + create versions. **Done when:** drafting flow matches the checklist and the panel researches alongside.

### LSAI-WB-08 — Exports, Matter linkage & Artifact Library
**Goal:** artifacts become practice objects. **Build:** DOCX/PDF export for every artifact type with the AI-assistance disclosure + review disclaimer footer; save-to-matter (creates versioned Document); "create Diary tasks from strategy items"; Artifact Library page (filter by matter/type/date); approval flow reuse (advocate approves → status change audited). **Tests:** export contains disclosure; saved artifact appears under the Matter; task creation lands in Court Diary; approval gating enforced. **Done when:** a Case Analysis flows into Matter documents and Diary tasks end-to-end.

### LSAI-WB-09 — Workbench evals & e2e extension
**Goal:** prove safety at feature level. **Build:** eval set per workflow (≥10 cases each): citation presence, refusal-without-source, banned phrases, **no-prediction probes** ("what are my chances?"), quotable-verbatim checks, cross-tenant probes; extend the e2e advocate journey with: upload file → Case Analysis → Argument Studio pack → export → second tenant sees nothing; wire evals into CI. **Tests:** eval thresholds pass; e2e green. **Done when:** STATUS.md updated with the new verified test count and the pack is flagged ready for senior-advocate review (Gate G8 — human, do not self-certify).

---

## 7. Human gates & honest notes

- **Gate G8 (senior advocate)** must review every workflow's prompts and sample outputs before beta advocates use the Workbench. Prepare a sign-off packet in WB-09; never self-certify.
- Workbench generations consume plan AI limits (research-type artifacts count as research units; drafting/argument artifacts as draft units) per the subscription spec.
- DBP claims (user counts, judgment counts) are their marketing; our parity table tracks features, not their claims. We never copy their "#1" style claims into our UI — constitution forbids unverifiable superiority claims.
- If any sprint touches privacy-sensitive behaviour (retention, uploads), the Privacy & Consent rules apply; scratch-upload auto-delete is a user-facing promise once shipped — document it on the consent/privacy page.

## 8. How to run this pack in Claude Code

Paste as the session opener:

```text
Read CLAUDE.md, the controlling Master Agent constitution, docs/STATUS.md, and
docs/sprints/LSAI_ADVOCATE_WORKBENCH_SPRINTS.md. Confirm the verified baseline,
then execute sprint LSAI-WB-00 only. Stop at its Done-when, update docs/STATUS.md,
and give the standard session report. Do not proceed to WB-01 without instruction.
```

Then advance one sprint per session ("proceed to LSAI-WB-01", etc.). If tests fail or a gate is violated, stop-the-line rules apply.

---

*The Workbench closes the feature gap with Draft Bot Pro and turns the five prompt-workflows every advocate wants into governed product. Same doctrine as always: no source, no answer · no citation, no claim · no advocate approval, no final draft · no prediction, ever.*
