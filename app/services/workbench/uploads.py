"""
WB-02 — Workbench document intelligence: uploads, page-anchored extraction,
file-grounded chat, List of Dates, scratch retention.

Doctrine mapping:
  • FILE grounding (pack §3.3): chat answers come ONLY from the uploaded file's
    extracted text. A question the file can't answer is refused deterministically
    (relevance threshold) — before any model is involved.
  • Every answer returns page/char ANCHORS so the UI can highlight the exact source
    passage (parity: "click a reference → highlights source text").
  • Privacy promise (pack §2): scratch uploads auto-delete after 7 days unless the
    advocate saves them to a Matter — then they become a versioned Document and
    leave the scratch lifecycle entirely.
  • Uploads are tenant-scoped; cross-tenant access is a 404, never a 403 hint.
"""
import io
import json
import logging
import re
from datetime import date, datetime, timedelta

from app.util.time import utcnow
from pathlib import Path

from sqlalchemy.orm import Session

from app.models.user import User
from app.models.workbench import WorkbenchUpload
from app.services import storage
from app.services.tenancy import write_audit

logger = logging.getLogger(__name__)

SCRATCH_RETENTION_DAYS = 7
ALLOWED_UPLOAD_EXT = {".pdf", ".txt"}          # WB-02 scope: text-extractable formats
CHUNK_CHARS = 1200                              # Q&A excerpt size
TOP_K = 6                                       # excerpts handed to the answerer
MIN_OVERLAP = 2                                 # matched keywords below this → refuse

_STOPWORDS = {
    "the", "a", "an", "of", "in", "on", "at", "to", "for", "and", "or", "is", "are",
    "was", "were", "be", "been", "by", "with", "as", "that", "this", "these", "those",
    "what", "which", "who", "whom", "when", "where", "how", "why", "does", "did", "do",
    "from", "it", "its", "into", "any", "all", "not", "no", "he", "she", "they", "we",
    "his", "her", "their", "our", "you", "your", "there", "here", "have", "has", "had",
    "will", "shall", "may", "can", "about", "under", "over", "between", "against",
}


class UploadError(Exception):
    def __init__(self, status_code: int, detail: str):
        self.status_code, self.detail = status_code, detail
        super().__init__(detail)


# ── Extraction ────────────────────────────────────────────────────────────────
def _extract_pdf(data: bytes) -> list[dict]:
    """Per-page text with running char offsets. Handles large files page-by-page."""
    from pypdf import PdfReader
    reader = PdfReader(io.BytesIO(data))
    pages, offset = [], 0
    for i, page in enumerate(reader.pages, start=1):
        try:
            text = page.extract_text() or ""
        except Exception:            # a single corrupt page must not sink the file
            text = ""
        text = text.strip()
        pages.append({"page": i, "text": text, "start": offset, "end": offset + len(text)})
        offset += len(text) + 1
    return pages


def _extract_txt(data: bytes) -> list[dict]:
    """Plain text: split into pseudo-pages of ~3000 chars on paragraph boundaries."""
    text = data.decode("utf-8", "ignore").strip()
    if not text:
        return []
    paras = re.split(r"\n\s*\n", text)
    pages, buf, offset, page_no = [], "", 0, 1
    for para in paras:
        if buf and len(buf) + len(para) > 3000:
            pages.append({"page": page_no, "text": buf.strip(),
                          "start": offset, "end": offset + len(buf)})
            offset += len(buf) + 1
            page_no += 1
            buf = ""
        buf += para + "\n\n"
    if buf.strip():
        pages.append({"page": page_no, "text": buf.strip(),
                      "start": offset, "end": offset + len(buf)})
    return pages


def save_upload(db: Session, user: User, filename: str, data: bytes,
                session_id: int | None = None) -> WorkbenchUpload:
    ext = Path(filename or "").suffix.lower()
    if ext not in ALLOWED_UPLOAD_EXT:
        raise UploadError(400, f"Workbench accepts {', '.join(sorted(ALLOWED_UPLOAD_EXT))} "
                               f"for now — '{ext or 'unknown'}' isn't supported yet.")
    try:
        info = storage.save_file(user.tenant_id, filename, data)   # 20MB cap + tenant dir
    except (storage.FileTooLarge, storage.FileTypeNotAllowed) as e:
        raise UploadError(400, str(e))

    pages = _extract_pdf(data) if ext == ".pdf" else _extract_txt(data)
    if not any(p["text"] for p in pages):
        raise UploadError(422, "No readable text found in the file. Scanned/image PDFs "
                               "need OCR, which isn't part of this update.")

    sidecar = Path(info["storage_path"]).with_suffix(".pages.json")
    sidecar.write_text(json.dumps({"pages": pages}, ensure_ascii=False), encoding="utf-8")

    up = WorkbenchUpload(
        tenant_id=user.tenant_id, user_id=user.id, session_id=session_id,
        filename=filename, page_count=len(pages),
        extracted_text_ref=str(sidecar), anchors_ref=info["storage_path"],
        retention_policy="scratch_7d",
        delete_after=utcnow() + timedelta(days=SCRATCH_RETENTION_DAYS),
    )
    db.add(up); db.commit(); db.refresh(up)
    write_audit(db, tenant_id=user.tenant_id, user_id=user.id,
                action="workbench_upload", entity="WorkbenchUpload", entity_id=up.id,
                detail=f"{filename} ({len(pages)} pages, auto-delete "
                       f"{up.delete_after:%Y-%m-%d} unless saved to a matter)")
    return up


def get_owned_upload(db: Session, upload_id: int, tenant_id: int) -> WorkbenchUpload:
    up = (db.query(WorkbenchUpload)
            .filter(WorkbenchUpload.id == upload_id,
                    WorkbenchUpload.tenant_id == tenant_id).first())
    if not up:
        raise UploadError(404, "Upload not found.")
    return up


def load_pages(up: WorkbenchUpload) -> list[dict]:
    try:
        return json.loads(Path(up.extracted_text_ref).read_text(encoding="utf-8"))["pages"]
    except Exception:
        raise UploadError(410, "The extracted text for this upload is no longer available "
                               "(it may have passed its retention window).")


# ── File-grounded Q&A ─────────────────────────────────────────────────────────
def _tokens(s: str) -> set[str]:
    return {w for w in re.findall(r"[a-z0-9]{3,}", s.lower()) if w not in _STOPWORDS}


def _chunks(pages: list[dict]) -> list[dict]:
    out = []
    for p in pages:
        text = p["text"]
        for i in range(0, max(len(text), 1), CHUNK_CHARS):
            piece = text[i:i + CHUNK_CHARS]
            if piece.strip():
                out.append({"page": p["page"], "start": p["start"] + i,
                            "end": p["start"] + i + len(piece), "text": piece})
    return out


def select_chunks(pages: list[dict], question: str, k: int = TOP_K) -> list[dict]:
    """Deterministic relevance: keyword overlap. Below MIN_OVERLAP → nothing → refusal.
    (Semantic ranking can layer on later; the refusal threshold must stay deterministic.)"""
    q = _tokens(question)
    if not q:
        return []
    scored = []
    for ch in _chunks(pages):
        hits = len(q & _tokens(ch["text"]))
        if hits >= min(MIN_OVERLAP, len(q)):
            scored.append((hits, ch))
    scored.sort(key=lambda t: -t[0])
    return [ch for _, ch in scored[:k]]


FILE_REFUSAL = ("The uploaded file does not appear to contain material answering this "
                "question. Nothing was invented. Ask about what the file covers, or put a "
                "legal question to the AI Assistant, which answers from verified statute.")


def answer_from_file(db: Session, user: User, up: WorkbenchUpload, question: str) -> dict:
    pages = load_pages(up)
    chunks = select_chunks(pages, question)
    anchors = [{"page": c["page"], "start": c["start"], "end": c["end"],
                "snippet": c["text"][:400]} for c in chunks]
    if not chunks:
        return {"refused": True, "answer": FILE_REFUSAL, "anchors": [], "mode": "refusal"}

    from app.ai.llm_config import ai_config
    cfg = ai_config()
    if not cfg["api_key"]:
        # Degraded-but-honest: the matching passages themselves, page-referenced.
        listing = "\n\n".join(f"[p.{c['page']}] {c['text'][:500]}" for c in chunks[:4])
        return {"refused": False, "mode": "excerpts",
                "answer": "The AI engine isn't connected, so here are the file's matching "
                          f"passages instead:\n\n{listing}", "anchors": anchors}

    def _excerpts_fallback(note: str) -> dict:
        listing = "\n\n".join(f"[p.{c['page']}] {c['text'][:500]}" for c in chunks[:4])
        return {"refused": False, "mode": "excerpts",
                "answer": f"{note}\n\n{listing}", "anchors": anchors}

    excerpts = "\n\n".join(f"[p.{c['page']}] {c['text']}" for c in chunks)
    system = (
        "You answer questions about ONE uploaded legal case file, for the advocate who "
        "uploaded it.\nABSOLUTE RULES:\n"
        "1. Use ONLY the excerpts below. If they don't contain the answer, say exactly "
        "that — never fill gaps from general knowledge.\n"
        "2. Cite the page for every claim, inline, as [p.N].\n"
        "3. Quote names, dates and amounts verbatim from the excerpts.\n"
        "4. No legal advice, no outcome forecasts — describe what the file says.\n\n"
        f"FILE EXCERPTS:\n{excerpts}"
    )
    try:
        from openai import OpenAI
        client = OpenAI(api_key=cfg["api_key"], base_url=cfg["base_url"],
                        timeout=90, max_retries=0)
        resp = client.chat.completions.create(
            model=cfg["model"],
            messages=[{"role": "system", "content": system},
                      {"role": "user", "content": question[:4000]}],
            max_tokens=1200, temperature=0.1,
        )
    except Exception as e:                     # provider down/throttled → degrade, never 500
        logger.warning(f"File-chat LLM unavailable: {e}")
        return _excerpts_fallback(
            "The AI engine is busy right now, so here are the file's matching passages "
            "instead (page-referenced):")
    answer = (resp.choices[0].message.content or "").strip()
    used_pages = {int(m) for m in re.findall(r"\[p\.(\d+)\]", answer)}
    if used_pages:
        anchors = [a for a in anchors if a["page"] in used_pages] or anchors
    return {"refused": False, "mode": "grounded", "answer": answer, "anchors": anchors}


# ── List of Dates & Events (court chronology) ─────────────────────────────────
_MONTHS = "january|february|march|april|may|june|july|august|september|october|november|december"
_DATE_RES = [
    # 12.06.2026 / 12-06-2026 / 12/06/2026  (dd first — Indian convention)
    (re.compile(r"\b(\d{1,2})[./-](\d{1,2})[./-](\d{4})\b"), "dmy"),
    # 12 June 2026 / 12th June, 2026
    (re.compile(rf"\b(\d{{1,2}})(?:st|nd|rd|th)?\s+({_MONTHS})[,.]?\s+(\d{{4}})\b", re.I), "dMy"),
    # June 12, 2026
    (re.compile(rf"\b({_MONTHS})\s+(\d{{1,2}})(?:st|nd|rd|th)?,?\s+(\d{{4}})\b", re.I), "Mdy"),
]
_MONTH_NO = {m: i + 1 for i, m in enumerate(_MONTHS.split("|"))}


def _to_iso(kind: str, g: tuple) -> str | None:
    try:
        if kind == "dmy":
            d, m, y = int(g[0]), int(g[1]), int(g[2])
        elif kind == "dMy":
            d, m, y = int(g[0]), _MONTH_NO[g[1].lower()], int(g[2])
        else:
            d, m, y = int(g[1]), _MONTH_NO[g[0].lower()], int(g[2])
        date(y, m, d)                          # validates the calendar date (rejects 31.02.)
        return f"{y:04d}-{m:02d}-{d:02d}"
    except (ValueError, KeyError):
        return None


def _event_context(text: str, span: tuple[int, int]) -> str:
    """The sentence/line the date sits in — the 'event' column of the chronology."""
    lo = max(text.rfind("\n", 0, span[0]), text.rfind(". ", 0, span[0]))
    hi_candidates = [x for x in (text.find("\n", span[1]), text.find(". ", span[1])) if x != -1]
    hi = min(hi_candidates) if hi_candidates else len(text)
    return re.sub(r"\s+", " ", text[lo + 1:hi + 1]).strip()[:300]


def list_of_dates(pages: list[dict]) -> dict:
    """Deterministic court-format chronology: every recognisable date + its context line,
    sorted, page-referenced. Extraction, not generation — costs no plan units."""
    rows, seen = [], set()
    for p in pages:
        for rx, kind in _DATE_RES:
            for m in rx.finditer(p["text"]):
                iso = _to_iso(kind, m.groups())
                if not iso:
                    continue
                event = _event_context(p["text"], m.span())
                key = (iso, event[:60])
                if key in seen:
                    continue
                seen.add(key)
                rows.append({"date": iso, "date_text": m.group(0),
                             "event": event, "page": p["page"]})
    rows.sort(key=lambda r: (r["date"], r["page"]))

    md = ["# List of Dates & Events", "",
          "| S.No. | Date | Event | Page |", "|---|---|---|---|"]
    for i, r in enumerate(rows, 1):
        md.append(f"| {i} | {r['date_text']} | {r['event'].replace('|', '/')} | {r['page']} |")
    md += ["", "Draft for advocate review. Verify facts, jurisdiction, limitation, "
              "court rules, and latest case law before filing."]
    return {"rows": rows, "markdown": "\n".join(md)}


# ── Kanoon-pick source (WB-05) ────────────────────────────────────────────────
def save_kanoon_judgment(db: Session, user: User, tid: str) -> WorkbenchUpload:
    """Materialise an Indian Kanoon judgment as a Workbench upload, so everything
    downstream (page anchors, verbatim gate, chat) treats it exactly like a file.
    Same 7-day scratch retention; the source URL is kept in the audit trail."""
    tid = re.sub(r"\D", "", tid or "")            # accepts a bare id or a full doc URL
    if not tid:
        raise UploadError(400, "Provide an Indian Kanoon document id or link.")
    from app.ai import case_law
    doc = case_law.fetch_document(tid)
    if not doc or not doc.get("text"):
        raise UploadError(502, "Could not fetch that judgment from Indian Kanoon "
                               "(check the id, or the service may be unavailable).")
    title = (doc.get("title") or f"kanoon_{tid}").strip()[:180]
    filename = re.sub(r"[^\w\s.-]", "", title)[:120].strip() + ".txt"
    header = f"{title}\n{doc.get('court', '')} · {doc.get('date', '')}\nSource: {doc['url']}\n\n"
    return save_upload(db, user, filename, (header + doc["text"]).encode("utf-8"))


# ── Retention + save-to-matter ────────────────────────────────────────────────
def purge_expired(db: Session, now: datetime | None = None) -> int:
    """Delete scratch uploads past their window — the 7-day privacy promise, kept."""
    now = now or utcnow()
    expired = (db.query(WorkbenchUpload)
                 .filter(WorkbenchUpload.delete_after.isnot(None),
                         WorkbenchUpload.delete_after < now).all())
    n = 0
    for up in expired:
        for ref in (up.anchors_ref, up.extracted_text_ref):
            try:
                if ref:
                    Path(ref).unlink(missing_ok=True)
            except OSError:
                pass
        write_audit(db, tenant_id=up.tenant_id, user_id=0,
                    action="workbench_upload_purged", entity="WorkbenchUpload",
                    entity_id=up.id, detail=f"{up.filename} (retention window passed)")
        db.delete(up)
        n += 1
    if n:
        db.commit()
    return n


def save_to_matter(db: Session, user: User, up: WorkbenchUpload, case_id: int):
    """Promote a scratch upload to a permanent, versioned case Document."""
    from app.services.tenancy import get_owned_case
    from app.models.document import Document
    from app.models.document_version import DocumentVersion
    get_owned_case(case_id, user.tenant_id, db)

    stored = Path(up.anchors_ref) if up.anchors_ref else None
    if not stored or not stored.exists():
        raise UploadError(410, "The stored file is no longer available.")
    data = stored.read_bytes()
    import hashlib
    doc = Document(tenant_id=user.tenant_id, case_id=case_id,
                   filename=up.filename, file_path=str(stored),
                   notes="Saved from Workbench")
    db.add(doc); db.flush()
    db.add(DocumentVersion(tenant_id=user.tenant_id, document_id=doc.id, version_no=1,
                           original_filename=up.filename, storage_path=str(stored),
                           content_type="application/pdf" if up.filename.lower().endswith(".pdf")
                                        else "text/plain",
                           size_bytes=len(data), sha256=hashlib.sha256(data).hexdigest(),
                           uploaded_by=user.id))
    up.retention_policy = "saved_to_matter"
    up.delete_after = None                       # leaves the scratch lifecycle
    db.commit(); db.refresh(doc)
    write_audit(db, tenant_id=user.tenant_id, user_id=user.id,
                action="workbench_upload_saved_to_matter", entity="Document",
                entity_id=doc.id, detail=f"upload={up.id} case={case_id}")
    return doc
