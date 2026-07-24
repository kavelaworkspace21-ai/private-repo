# Legal Corpus — Authentic Sources & Ingestion Legality (Loop output, 2026-06-25)

How Juriscite sources legal text **legally** (DPDP + Copyright Act compliant) and authentically.
Owner directive (Kavela Narula): ingest authentic bare acts, judgments, and law materials — verified only.

## Legal basis for ingesting (Copyright Act, 1957)
- **Judgments / orders of any court or tribunal** — reproduction is **not** an infringement
  (§52(1)(q)), and the Supreme Court in *Eastern Book Company v. D.B. Modak* (2008) held the **raw
  text of judgments is public domain**; only a publisher's original editorial work (headnotes,
  copy-editing, paragraph numbering) is copyrightable. → **Ingest raw judgments from OFFICIAL free
  sources only**, never a publisher's value-added version.
- **Acts of a Legislature / Official Gazette matter** — covered by §52(1)(q); statutes are government
  works. We reproduce statutory text together with our **own original matter** (summaries, citations,
  structured metadata), consistent with the provision. A formal IP opinion before public launch is
  prudent (tracked, not self-certified).

## ✅ Authentic, free, legal-to-ingest sources
| Material | Official source |
|---|---|
| Central & State **bare Acts** + rules/regs | **India Code** — https://www.indiacode.nic.in (Ministry of Law & Justice) |
| New criminal codes **BNS / BNSS / BSA, 2023** | India Code (e.g., BNS https://www.indiacode.nic.in/handle/123456789/20062) + **MHA** official PDFs (https://www.mha.gov.in) |
| **Supreme Court judgments** (raw, public-domain) | **e-SCR / DigiSCR** — https://digiscr.sci.gov.in · https://main.sci.gov.in |
| Judgment search (SC + High Courts) | https://judgments.ecourts.gov.in (official, read-only; **no scraping/CAPTCHA bypass**) |
| **Official Gazette** | https://egazette.gov.in |
| Constitution of India | India Code / https://legislative.gov.in |
| Govt handbooks (e.g., BPRD/NCRB on BNS) | Respective official .gov.in/.nic.in portals |

## ⛔ RED LINE — do NOT ingest (would be infringement / contradict the "stay legal" directive)
- **Commercial law books, textbooks, treatises, commentaries** (publisher content).
- **Publisher editorial versions** of judgments — SCC, AIR, Manupatra headnotes/copy-edited text
  (copyrightable per *Eastern Book Co.*). Use the official raw judgment instead.
- Anything **paywalled** or whose **Terms of Service forbid** reuse/scraping.
- Scraping / CAPTCHA bypass of any portal (barred by CLAUDE.md §12). Use official downloads/APIs.

## Ingestion method (authentic + provable)
1. Fetch from the official source above (download the official PDF/page; do not scrape ToS-restricted sites).
2. Extract **verbatim** statutory/section text; preserve section numbers + structure.
3. Record **provenance per chunk**: `source_url`, `source_name`, `retrieved_at`, `version/date`,
   `tier` (verbatim vs heading-only), `act/section/year/jurisdiction`.
4. Chunk + embed (free local ONNX) into ChromaDB; mark `verbatim=true` only when full text is stored.
5. Maturity label stays SEED/AUTHORED until a human spot-checks authenticity (corpus-authenticity gate
   remains — the agent never self-certifies that the text is correct).

## Status / plan
- Current corpus (per repo): ~30 books, 9 verbatim (~3,063 sections), heading-tier for the rest + live
  Indian Kanoon (cached). **Next batch to ingest (highest value):** Constitution, BNS, BNSS, BSA, and the
  core civil/criminal/procedure + evidence + contract acts, verbatim from India Code, with provenance.
- Bulk ingestion is an **ongoing batched pipeline**, not a one-shot — each batch is fetched from the
  official source, verbatim-extracted, provenance-tagged, and embedded.
