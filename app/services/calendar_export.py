"""
iCalendar (.ics) export of a tenant's Court Diary — hearings + filing deadlines.

This is the user-friendly, no-OAuth path to the device's default calendar: the advocate
downloads (or subscribes to) the .ics and it imports into Google/Apple/Outlook calendars.
Everything is tenant-scoped (via the parent Case) — never cross-tenant.
"""
from datetime import date, datetime, timezone
from sqlalchemy.orm import Session

from app.models.case import Case
from app.models.diary_entry import DiaryEntry
from app.models.filing_deadline import FilingDeadline


def _esc(text: str) -> str:
    """Escape per RFC 5545."""
    return (str(text or "")
            .replace("\\", "\\\\").replace(";", "\\;")
            .replace(",", "\\,").replace("\n", "\\n"))


def _fold(line: str) -> str:
    """RFC 5545 lines should be <=75 octets; fold long ones."""
    out, s = [], line
    while len(s) > 73:
        out.append(s[:73])
        s = " " + s[73:]
    out.append(s)
    return "\r\n".join(out)


def _event(uid: str, day: date, summary: str, desc: str, stamp: str) -> list[str]:
    d = day.strftime("%Y%m%d")
    return [
        "BEGIN:VEVENT",
        _fold(f"UID:{uid}@legalserver.ai"),
        f"DTSTAMP:{stamp}",
        f"DTSTART;VALUE=DATE:{d}",
        f"DTEND;VALUE=DATE:{d}",
        _fold(f"SUMMARY:{_esc(summary)}"),
        _fold(f"DESCRIPTION:{_esc(desc)}"),
        "END:VEVENT",
    ]


def build_diary_ics(db: Session, tenant_id: int) -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    lines = [
        "BEGIN:VCALENDAR", "VERSION:2.0",
        "PRODID:-//Juriscite//Court Diary//EN",
        "CALSCALE:GREGORIAN", "METHOD:PUBLISH",
        "X-WR-CALNAME:Juriscite Court Diary",
    ]

    hearings = (
        db.query(DiaryEntry, Case.title)
        .join(Case, DiaryEntry.case_id == Case.id)
        .filter(Case.tenant_id == tenant_id)
        .all()
    )
    for e, case_title in hearings:
        summary = f"Hearing: {case_title}"
        desc_parts = [p for p in [
            e.court_name,
            f"Stage: {e.stage.value}" if getattr(e, "stage", None) else "",
            f"Court room: {e.court_room}" if e.court_room else "",
        ] if p]
        lines += _event(f"hearing-{e.id}", e.hearing_date, summary,
                        " · ".join(desc_parts), stamp)

    deadlines = (
        db.query(FilingDeadline, Case.title)
        .join(Case, FilingDeadline.case_id == Case.id)
        .filter(Case.tenant_id == tenant_id, FilingDeadline.is_filed == False)
        .all()
    )
    for dl, case_title in deadlines:
        lines += _event(f"deadline-{dl.id}", dl.deadline_date,
                        f"Deadline: {dl.title}", f"{case_title}", stamp)

    lines.append("END:VCALENDAR")
    return "\r\n".join(lines) + "\r\n"
