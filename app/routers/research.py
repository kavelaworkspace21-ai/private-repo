"""
Legal research — case-law search + grounded summaries (Indian Kanoon).

Every result carries a verifiable indiankanoon.org link. Summaries are derived ONLY
from the fetched judgment text. If no API key is configured, endpoints return empty
results rather than fabricating anything.
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from app.auth.dependencies import get_current_user
from app.models.user import User
from app.ai import case_law
from app.services import mapping

router = APIRouter()


@router.get("/mapping")
def statute_mapping(act: str = Query(..., min_length=2), section: str = Query(..., min_length=1),
                    direction: str = "old_to_new", _: User = Depends(get_current_user)):
    """
    Bridge legacy and new criminal law.
    direction=old_to_new: IPC/CrPC/IEA section → BNS/BNSS/BSA equivalent (default).
    direction=new_to_old: the reverse.
    """
    hit = (mapping.lookup_new(act, section) if direction == "new_to_old"
           else mapping.lookup_old(act, section))
    if not hit:
        raise HTTPException(404, "No mapping found for that act/section.")
    return hit


class CaseCard(BaseModel):
    title: str
    court: str
    date: str
    citation: str
    cited_by: str
    snippet: str
    url: str
    good_law: str = "unverified"
    good_law_caveat: str = ""


class CaseSummary(BaseModel):
    title: str
    court: str
    date: str
    cited_by: str
    summary: str
    url: str
    good_law: str = "unverified"
    disclaimer: str


@router.get("/cases", response_model=list[CaseCard])
def search_cases(q: str = Query(..., min_length=2), _: User = Depends(get_current_user)):
    """At-a-glance case cards with verifiable links (live from Indian Kanoon)."""
    return case_law.search_cases(q)


@router.get("/cases/{tid}/summary", response_model=CaseSummary)
def case_summary(tid: str, _: User = Depends(get_current_user)):
    """Brief, source-grounded summary of one judgment + verifiable link."""
    result = case_law.summarize_case(tid)
    if not result:
        raise HTTPException(404, "Judgment not found or case-law service unavailable")
    return result


@router.get("/latest-judgments", response_model=list[CaseCard])
def latest_judgments(_: User = Depends(get_current_user)):
    """Recent judgments for the dashboard 'Latest from the courts' feed (live + cached)."""
    return case_law.latest_judgments()


@router.get("/provisions")
def search_provisions(q: str = Query(..., min_length=2), _: User = Depends(get_current_user)):
    """Top matching statutory provisions from the source-verified corpus.
    Read-only; used by the drafting workspace's AI reference panel. Returns
    [{act, year, section, title, url, verified}] — never fabricated, only retrieved."""
    from app.ai import rag
    try:
        return rag.retrieve_structured(q)
    except Exception:
        return []  # corpus unavailable → empty, never an error page


@router.get("/status")
def research_status(_: User = Depends(get_current_user)):
    """Whether live case law is enabled (API key present)."""
    return {"case_law_enabled": case_law.is_enabled()}
