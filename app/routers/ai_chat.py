"""
AI Legal Assistant router — powered by the Universal Legal Agent.
Streaming chat via Server-Sent Events (SSE) + conversation persistence.
"""
import json
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.services.tenancy import write_audit
from app.auth.dependencies import get_current_user, require_ai_access
from app.models.user import User
from app.models.ai_chat import Conversation, AiMessage
from app.schemas.ai_chat import ChatRequest, ConversationOut, ConversationWithMessages
from app.ai.activity_tracker import build_activity_context, log_chat

router = APIRouter()


# ── POST /api/ai/transcribe — voice input (Whisper-compatible, provider-agnostic) ──
@router.post("/transcribe")
async def transcribe_audio(
    audio: UploadFile = File(...),
    language: str | None = Form(None),
    current_user: User = Depends(get_current_user),
):
    """Transcribe an uploaded audio clip to text (any Indian language) for voice input.
    Uses a Whisper-capable OpenAI-compatible endpoint (free option: Groq). Degrades gracefully
    if not configured. The audio is sent only to the configured provider for transcription."""
    from app.ai.llm_config import transcribe_config
    cfg = transcribe_config()
    if not cfg["api_key"]:
        raise HTTPException(503, "Voice transcription is not configured. Set TRANSCRIBE_* (or use a "
                                 "Whisper-capable AI provider key, e.g. free Groq whisper-large-v3).")
    data = await audio.read()
    if not data:
        raise HTTPException(400, "Empty audio file.")
    if len(data) > 25 * 1024 * 1024:
        raise HTTPException(413, "Audio too large (max 25 MB).")
    try:
        import io
        from openai import OpenAI
        client = OpenAI(api_key=cfg["api_key"], base_url=cfg["base_url"])
        buf = io.BytesIO(data)
        buf.name = audio.filename or "audio.webm"
        kwargs = {"model": cfg["model"], "file": buf}
        if language:
            kwargs["language"] = language
        resp = client.audio.transcriptions.create(**kwargs)
        return {"text": getattr(resp, "text", "") or ""}
    except Exception as e:
        raise HTTPException(502, f"Transcription failed: {e}")


@router.get("/transcribe/status")
def transcribe_status(_: User = Depends(get_current_user)):
    from app.ai.llm_config import is_transcribe_enabled
    return {"enabled": is_transcribe_enabled()}


# ── GET /api/ai/conversations ─────────────────────────────────────────────────
@router.get("/conversations", response_model=list[ConversationOut])
def list_conversations(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return (
        db.query(Conversation)
        .filter(Conversation.user_id == current_user.id)
        .order_by(Conversation.updated_at.desc())
        .limit(50)
        .all()
    )


# ── GET /api/ai/conversations/{id} ───────────────────────────────────────────
@router.get("/conversations/{conv_id}", response_model=ConversationWithMessages)
def get_conversation(
    conv_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    conv = db.query(Conversation).filter(
        Conversation.id == conv_id,
        Conversation.user_id == current_user.id,
    ).first()
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return conv


# ── DELETE /api/ai/conversations/{id} ────────────────────────────────────────
@router.delete("/conversations/{conv_id}", status_code=204)
def delete_conversation(
    conv_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    conv = db.query(Conversation).filter(
        Conversation.id == conv_id,
        Conversation.user_id == current_user.id,
    ).first()
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")
    cid = conv.id
    db.delete(conv)
    db.commit()
    write_audit(db, tenant_id=current_user.tenant_id, user_id=current_user.id,
                action="delete_conversation", entity="Conversation", entity_id=cid)


# ── POST /api/ai/chat  (SSE streaming) ───────────────────────────────────────
from app.services.ratelimit import ai_limiter


@router.post("/chat", dependencies=[Depends(ai_limiter)])
def chat(
    body: ChatRequest,
    current_user: User = Depends(require_ai_access),   # verification gate (LEGAL-07; flag-gated)
    db: Session = Depends(get_db),
):
    # THE SOUL — attempting to use Juriscite against the law ejects the user from the ecosystem.
    from app.ai.safety import screen_request_intent
    _refusal = screen_request_intent(body.message)
    if _refusal:
        from app.services.soul_enforcement import eject_user_for_soul_violation
        eject_user_for_soul_violation(db, current_user, "unlawful_request_via_ai_chat")

        def _ejected():
            yield f"data: {json.dumps({'content': _refusal})}\n\n"
            yield f"data: {json.dumps({'content': chr(10) + chr(10) + '⚠ Your access to Juriscite has been revoked for attempting to use it against the law. This action is final.'})}\n\n"
            yield f"data: {json.dumps({'confidence': 'LOW'})}\n\n"
            yield f"data: {json.dumps({'done': True})}\n\n"
        return StreamingResponse(_ejected(), media_type="text/event-stream",
                                 headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})

    # Entitlements (spec 3.4): a chat turn is a research query, unless the advocate
    # asked for a document — then it is a draft, and it is metered as one. Checked
    # BEFORE any model work, so an over-quota request costs nothing and 402s cleanly.
    from app.ai.agent import _detect_draft_intent
    from app.models.billing import KIND_DRAFT, KIND_RESEARCH
    from app.services.entitlements import enforce_quota, meter
    _kind = KIND_DRAFT if _detect_draft_intent(body.message)[0] else KIND_RESEARCH
    enforce_quota(db, current_user, _kind)

    # Resolve or create conversation
    if body.conversation_id:
        conv = db.query(Conversation).filter(
            Conversation.id == body.conversation_id,
            Conversation.user_id == current_user.id,
        ).first()
        if not conv:
            raise HTTPException(status_code=404, detail="Conversation not found")
    else:
        title = body.message[:60].strip() + ("..." if len(body.message) > 60 else "")
        conv = Conversation(user_id=current_user.id, title=title)
        db.add(conv)
        db.flush()

    # Persist user message
    user_msg = AiMessage(conversation_id=conv.id, role="user", content=body.message)
    db.add(user_msg)
    db.commit()
    db.refresh(conv)

    # Build message history (last 20 turns, excluding the message we just saved)
    history_rows = (
        db.query(AiMessage)
        .filter(AiMessage.conversation_id == conv.id)
        .order_by(AiMessage.id.asc())
        .all()
    )
    # Exclude the last user message (agent appends it)
    conversation_history = [
        {"role": m.role, "content": m.content}
        for m in history_rows[:-1]
    ][-20:]

    # The turn is now committed to run → record exactly one unit of usage.
    meter(db, current_user, _kind)

    # Build activity context and log
    activity_context = build_activity_context(db, current_user.id)
    log_chat(db, current_user.id, conv.id, body.message[:80])

    conv_id = conv.id
    message = body.message

    async def stream_generator():
        from app.ai.agent import stream_agent_response
        full_response = ""
        available_citations: list[str] = []

        yield f"data: {json.dumps({'conversation_id': conv_id})}\n\n"

        async for sse_chunk in stream_agent_response(
            message=message,
            conversation_history=conversation_history,
            activity_context=activity_context,
        ):
            payload = json.loads(sse_chunk)

            if "content" in payload:
                full_response += payload["content"]
                yield f"data: {sse_chunk}\n\n"
            elif "confidence" in payload:
                yield f"data: {sse_chunk}\n\n"
            elif "draft_status" in payload or "format_used" in payload:
                # chat drafting mode: review-status badge + format chip for the UI
                yield f"data: {sse_chunk}\n\n"
            elif "available_citations" in payload:
                available_citations = payload["available_citations"]  # internal; not forwarded
            elif "error" in payload:
                yield f"data: {sse_chunk}\n\n"
            elif payload.get("done"):
                if full_response:
                    from app.ai.safety import sanitize_answer, enforce_citations
                    # Gate ONLY the model's prose — not the auto-generated "Sources consulted"
                    # footer, which is built from real retrieved data (its section numbers are
                    # inherently verified and must not be re-flagged as unverified).
                    FOOTER_MARK = "\n\n---\n### 📚 Sources consulted"
                    if FOOTER_MARK in full_response:
                        answer_part, footer_part = full_response.split(FOOTER_MARK, 1)
                        footer_part = FOOTER_MARK + footer_part
                    else:
                        answer_part, footer_part = full_response, ""
                    answer_part = sanitize_answer(answer_part)
                    # Citation hard-gate (§2.2): flag any section the ANSWER cites that is
                    # not in the retrieved sources, so an unverified claim can't slip through.
                    context_for_gate = "\n".join(f"Section {c}" for c in available_citations)
                    answer_part, unverified = enforce_citations(answer_part, context_for_gate)
                    if unverified:
                        warn = chr(10) + chr(10) + '---' + chr(10) + '⚠ Citation check: ' + ', '.join('Section ' + u for u in unverified) + ' could not be verified against the retrieved sources.'
                        yield f"data: {json.dumps({'content': warn})}\n\n"
                        answer_part = answer_part + warn
                    full_response = answer_part + footer_part

                    # Additive corpus-integrity signal (Phase 4). The gate above checks the answer
                    # against the RETRIEVED sources (grounding, number-only); this additionally
                    # resolves each citation act-aware against the WHOLE corpus, catching a citation
                    # to a section that does not exist in the named act at all (hard fabrication /
                    # act-misattribution). Non-blocking — the act-pairing is heuristic and could
                    # false-positive, so it LOGS for review + emits a signal the UI may surface, and
                    # can NEVER break the stream. (A hard repair-or-refuse gate is a follow-up, once
                    # the guard is validated against real generated answers.)
                    try:
                        from app.ai.citation_guard import integrity_event
                        ci = integrity_event(answer_part)
                        if ci:
                            import logging
                            logging.getLogger(__name__).warning(
                                "Citation integrity: answer cites section(s) absent from the "
                                f"corpus (possible fabrication/misattribution): {ci['fabricated']}")
                            yield f"data: {json.dumps({'citation_integrity': ci})}\n\n"
                    except Exception:
                        pass  # integrity telemetry must never break the answer stream

                    new_db = next(get_db())
                    try:
                        ai_msg = AiMessage(
                            conversation_id=conv_id,
                            role="assistant",
                            content=full_response,
                        )
                        new_db.add(ai_msg)
                        from app.util.time import utcnow
                        c = new_db.get(Conversation, conv_id)
                        if c:
                            c.updated_at = utcnow()
                        new_db.commit()
                    finally:
                        new_db.close()

                yield f"data: {json.dumps({'done': True})}\n\n"

    return StreamingResponse(
        stream_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
