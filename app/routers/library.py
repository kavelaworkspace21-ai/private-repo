"""
Legal Library — quick access to all bare acts + sections, with on-demand summaries.

Browsing returns verbatim section text + a verifiable source link. Summaries are
grounded ONLY in that section's text (no outside knowledge), so they cannot introduce
facts not in the statute. Falls back to an extractive excerpt without an OpenAI key.
"""
import os
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from app.auth.dependencies import get_current_user, require_founder
from app.models.user import User
from app.services import library

router = APIRouter()


# ── Corpus versioning + upstream-change detection (Roadmap P3) ─────────────────────
@router.get("/corpus-status")
def corpus_status(_: User = Depends(get_current_user)):
    """Corpus provenance snapshot: per-act sha256/fetched_on/status, totals, the corpus
    fingerprint, and the last upstream drift check (if one has run)."""
    from app.ai.corpus_updates import corpus_manifest, last_upstream_check
    m = corpus_manifest()
    m["last_upstream_check"] = last_upstream_check()
    return m


@router.post("/corpus-check-updates", dependencies=[Depends(require_founder)])
def corpus_check_updates(act_id: str | None = Query(default=None)):
    """Founder-only: re-download each act's OFFICIAL bitstream and report which acts India
    Code has republished (drift). Reports only — re-ingestion stays a human-supervised
    slice (landmark verification before any reseed). ~1-2 min for the full corpus."""
    from app.ai.corpus_updates import check_upstream
    return check_upstream([act_id] if act_id else None)


class ActSummary(BaseModel):
    id: str
    title: str
    short: str
    year: int | None
    status: str
    source_verified: bool
    section_count: int


@router.get("/acts", response_model=list[ActSummary])
def list_acts(_: User = Depends(get_current_user)):
    return library.list_acts()


@router.get("/acts/{act_id}")
def get_act(act_id: str, _: User = Depends(get_current_user)):
    act = library.get_act(act_id)
    if not act:
        raise HTTPException(404, "Act not found")
    return act


@router.get("/acts/{act_id}/sections/{num}")
def get_section(act_id: str, num: str, _: User = Depends(get_current_user)):
    sec = library.get_section(act_id, num)
    if not sec:
        raise HTTPException(404, "Section not found")
    return sec


@router.get("/search")
def search(q: str = Query(..., min_length=2), _: User = Depends(get_current_user)):
    return library.search(q)


@router.get("/acts/{act_id}/sections/{num}/summary")
def summarize_section(act_id: str, num: str, _: User = Depends(get_current_user)):
    sec = library.get_section(act_id, num)
    if not sec:
        raise HTTPException(404, "Section not found")
    text = (sec.get("text") or "").strip()
    if not text:
        raise HTTPException(404, "No text available to summarise for this section")

    summary = ""
    from app.ai.llm_config import ai_config
    cfg = ai_config()
    if cfg["api_key"] and len(text) > 350:   # only worth summarising longer sections
        try:
            from openai import OpenAI
            client = OpenAI(api_key=cfg["api_key"], base_url=cfg["base_url"])
            resp = client.chat.completions.create(
                model=cfg["model"], temperature=0.1, max_tokens=260,
                messages=[
                    {"role": "system", "content":
                        "You explain a single Indian statutory provision to an advocate in "
                        "plain English. Use ONLY the provided text — add nothing not in it. "
                        "2-4 sentences: what it covers and its key effect. No outcome "
                        "guarantees, no advice."},
                    {"role": "user", "content":
                        f"{sec['act_title']} — Section {sec['num']}: {sec['title']}\n\n{text[:6000]}"},
                ],
            )
            summary = (resp.choices[0].message.content or "").strip()
        except Exception:
            summary = ""
    if not summary:
        summary = text[:600].strip() + ("…" if len(text) > 600 else "")

    return {
        "act_id": sec["act_id"], "act_title": sec["act_title"],
        "num": sec["num"], "title": sec["title"],
        "summary": summary, "source_verified": sec["source_verified"],
        "source_url": sec["source_url"],
        "disclaimer": "Plain-English summary grounded in the section text. "
                      "Read the full provision (and verify at the source) before relying on it.",
    }
