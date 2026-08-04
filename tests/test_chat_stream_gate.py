"""The fail-closed gate must hold in the STREAM, not just in the gate function.

Streaming is where the original design failed: content chunks were sent to the browser as
they arrived, and the citation check only ran at `done` — so a fabricated section was
already on screen, and the "gate" appended a warning underneath it.

These drive a real request through /api/ai/chat with a stubbed model, and assert on what
the client receives and what gets persisted.
"""
import json


from app.ai import agent as agent_mod
from tests.conftest import auth, register_and_login


def _stub_stream(answer: str, citations: list[str]):
    """Stand in for the model: emit the answer, then the retrieved citation list."""
    async def _gen(**kwargs):
        for chunk in answer.split(" "):
            yield json.dumps({"content": chunk + " "})
        yield json.dumps({"available_citations": citations})
        yield json.dumps({"done": True})
    return _gen


def _sse_events(body: str) -> list[dict]:
    out = []
    for line in body.splitlines():
        if line.startswith("data: "):
            try:
                out.append(json.loads(line[6:]))
            except json.JSONDecodeError:
                pass
    return out


FABRICATED = ("Section 138 governs cheque dishonour in the ordinary course. "
              "Section 999 requires the drawer to deposit security before filing. "
              "The limitation period runs from the date of the statutory notice. "
              "A complaint filed after that period is liable to be dismissed.")

GROUNDED = ("Section 138 governs cheque dishonour in the ordinary course. "
            "The limitation period runs from the date of the statutory notice. "
            "A complaint filed after that period is liable to be dismissed.")


def test_stream_replaces_the_answer_when_a_citation_is_unverified(client, monkeypatch):
    monkeypatch.setattr(agent_mod, "stream_agent_response",
                        _stub_stream(FABRICATED, ["138"]))
    tok = register_and_login(client, "gate-stream@firm.com")

    r = client.post("/api/ai/chat", headers=auth(tok), json={"message": "cheque bounce"})
    assert r.status_code == 200
    events = _sse_events(r.text)

    replaced = [e for e in events if "final_answer" in e]
    assert replaced, "the stream never told the client to replace the provisional text"

    final = replaced[0]["final_answer"]
    body = final.split("\n\n---\n", 1)[0]
    assert "999" not in body, "the fabricated section is still presented as law"
    assert "deposit security" not in final
    assert replaced[0]["answer_replaced"]["status"] in ("repaired", "withheld")


def test_persisted_message_is_the_validated_answer_not_the_raw_generation(client, monkeypatch):
    """What is stored is what the advocate sees later — it must be the gated text."""
    from app.db.session import get_db
    from app.main import app as fastapi_app
    from app.models.ai_chat import AiMessage

    monkeypatch.setattr(agent_mod, "stream_agent_response",
                        _stub_stream(FABRICATED, ["138"]))
    tok = register_and_login(client, "gate-persist@firm.com")
    client.post("/api/ai/chat", headers=auth(tok), json={"message": "cheque bounce"})

    db = next(fastapi_app.dependency_overrides[get_db]())
    stored = db.query(AiMessage).filter(AiMessage.role == "assistant").all()
    assert stored, "no assistant message was persisted"
    for m in stored:
        body = m.content.split("\n\n---\n", 1)[0]
        assert "999" not in body, "the raw ungated answer was persisted"


def test_grounded_answer_streams_through_untouched(client, monkeypatch):
    """The gate must not fire on a clean answer — over-blocking is its own failure."""
    monkeypatch.setattr(agent_mod, "stream_agent_response",
                        _stub_stream(GROUNDED, ["138"]))
    tok = register_and_login(client, "gate-clean@firm.com")

    r = client.post("/api/ai/chat", headers=auth(tok), json={"message": "cheque bounce"})
    events = _sse_events(r.text)
    assert not [e for e in events if "final_answer" in e], (
        "a fully grounded answer was replaced — the gate is over-blocking")
    streamed = "".join(e["content"] for e in events if "content" in e)
    assert "Section 138" in streamed
