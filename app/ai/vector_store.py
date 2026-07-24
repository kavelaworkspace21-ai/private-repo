"""
Vector store — ChromaDB backed by OpenAI embeddings.
Indexes every section from law_index.json as a searchable document.
"""
import os
import json
import logging
import shutil
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv

load_dotenv()  # CHROMA_PATH is read at import time — standalone scripts must see .env too

logger = logging.getLogger(__name__)

CORPUS_DIR  = Path(__file__).parent.parent / "legal_corpus"
CORPUS_PATH = CORPUS_DIR / "law_index.json"  # kept for legacy reference
# Overridable so the store can live off the app drive (2026-07-20: C: ran to 43 MB free
# and sqlite "disk full" broke reseed; the dev store now lives on D: via .env). Default
# unchanged — prod/EC2 and CI keep the in-repo path.
CHROMA_PATH = Path(os.getenv("CHROMA_PATH") or Path(__file__).parent.parent.parent / "chroma_db")
COLLECTION_NAME = "indian_law_sections"
EMBEDDING_MODEL = "text-embedding-3-small"

# Disk preflight thresholds (S0.2). The 2026-07-20 incident: a reseed ran with 43 MB free,
# sqlite raised "database or disk is full" mid-write, and the store was left corrupt. Boot
# warns early; reseed refuses outright rather than risk a half-written store.
DISK_WARN_FREE_BYTES   = 2 * 1024 ** 3    # 2 GB — boot logs a warning below this
RESEED_MIN_FREE_BYTES  = 500 * 1024 ** 2  # 500 MB — reseed refuses to start below this


def disk_free_bytes(path: Optional[Path] = None) -> int:
    """Bytes free on the volume backing the Chroma store (``CHROMA_PATH`` by default).

    Walks up to the nearest existing ancestor so it works before the store dir is created
    (first boot). Raises only if even the drive root can't be stat'd.
    """
    target = Path(path or CHROMA_PATH)
    while not target.exists() and target != target.parent:
        target = target.parent
    return shutil.disk_usage(str(target)).free

_client   = None
_collection = None


def _get_client():
    global _client
    if _client is None:
        try:
            import chromadb
            _client = chromadb.PersistentClient(path=str(CHROMA_PATH))
        except ImportError:
            raise RuntimeError("chromadb not installed. Run: pip install chromadb")
    return _client


def get_collection():
    """Return the ChromaDB collection, creating it if it doesn't exist."""
    global _collection
    if _collection is not None:
        return _collection

    client = _get_client()

    try:
        import chromadb.utils.embedding_functions as ef
        # Embeddings default to a FREE local model (ONNX MiniLM, runs on CPU, no API/cost).
        # Only use paid OpenAI embeddings if explicitly opted in via OPENAI_EMBEDDINGS_KEY —
        # this keeps a free LLM key (AI_API_KEY / OPENAI_API_KEY) from triggering paid embed calls.
        emb_key = os.getenv("OPENAI_EMBEDDINGS_KEY", "").strip()
        if emb_key:
            embed_fn = ef.OpenAIEmbeddingFunction(
                api_key=emb_key,
                model_name=EMBEDDING_MODEL,
            )
        else:
            embed_fn = ef.DefaultEmbeddingFunction()   # free, local, no key

        _collection = client.get_or_create_collection(
            name=COLLECTION_NAME,
            embedding_function=embed_fn,
            metadata={"hnsw:space": "cosine"},
        )

        # Seed if empty
        if _collection.count() == 0:
            logger.info("Legal corpus is empty — seeding from law_index.json …")
            _seed_collection(_collection)
            logger.info(f"Seeded {_collection.count()} law sections into ChromaDB.")

    except Exception as e:
        logger.error(f"ChromaDB init failed: {e}")
        raise

    return _collection


FULLTEXT_DIR = CORPUS_DIR / "fulltext"


def _seed_collection(collection):
    """
    Embed sections into the vector store.

    Priority: any Act that has a SOURCE-VERIFIED full-text file in legal_corpus/fulltext/
    is indexed from that file (verbatim text, quotable, with provenance). For every other
    Act we fall back to the heading-only index files in legal_corpus/. We never index both
    for the same Act, so verified full text always supersedes headings.
    """
    documents, metadatas, ids = [], [], []
    verified_act_ids: set[str] = set()

    # ── Pass 1: source-verified full-text files (preferred) ──────────────────────
    if FULLTEXT_DIR.exists():
        for ft_file in sorted(FULLTEXT_DIR.glob("*.fulltext.json")):
            try:
                with open(ft_file, "r", encoding="utf-8") as f:
                    index = json.load(f)
            except Exception as e:
                logger.warning(f"Could not load {ft_file.name}: {e}")
                continue

            for act in index.get("acts", []):
                act_id = act["id"]
                verified_act_ids.add(act_id)
                src = act.get("source", {})
                # Currency metadata: a repealed act's chunks carry the repeal pointer so the
                # citation layer can warn (IPC→BNS, Income-tax 1961→ITA 2025). Doctrine: a
                # repealed provision must never be cited as if in force.
                act_repealed_by = act.get("repealed_by", "")
                act_note = act.get("note", "")
                for sec in act.get("sections", []):
                    sec_num, sec_title = sec["num"], sec.get("title", "")
                    sec_text = sec.get("text", "")
                    # Embed the ACTUAL section text so retrieval is by substance.
                    text = (f"{act['title']} ({act['year']}), Section {sec_num} — "
                            f"{sec_title}.\n{sec_text}")
                    doc_id = f"{act_id}_s{sec_num}".replace(" ", "_").replace("/", "-")
                    documents.append(text)
                    metadatas.append({
                        "act_id": act_id, "act_title": act["title"],
                        "act_year": str(act["year"]), "act_status": act.get("status", "in_force"),
                        "section": sec_num, "title": sec_title,
                        "full_text": sec_text,
                        "source_verified": True,
                        "source_url": src.get("url", ""),
                        "source_sha256": src.get("sha256", ""),
                        "page": str(sec.get("page", "")),
                        "replaces": "", "repealed_by": act_repealed_by, "note": act_note,
                    })
                    ids.append(doc_id)

    # ── Pass 2: heading-only index files (fallback for non-verified acts) ─────────
    for corpus_file in sorted(CORPUS_DIR.glob("*.json")):
        try:
            with open(corpus_file, "r", encoding="utf-8") as f:
                index = json.load(f)
        except Exception as e:
            logger.warning(f"Could not load {corpus_file.name}: {e}")
            continue

        for act in index.get("acts", []):
            act_id = act["id"]
            if act_id in verified_act_ids:
                continue  # verified full text already indexed — don't add headings
            act_title = act["title"]
            act_year  = act["year"]
            act_status = act.get("status", "in_force")
            replaces  = act.get("replaces", "")
            repealed_by = act.get("repealed_by", "")
            note      = act.get("note", "")

            for sec in act.get("sections", act.get("key_sections", [])):
                sec_num, sec_title = sec["num"], sec["title"]
                text = (
                    f"{act_title} — Section {sec_num}: {sec_title}. "
                    f"Act: {act_title} ({act_year}). Status: {act_status}."
                )
                if replaces:
                    text += f" This Act replaces {replaces}."
                if repealed_by:
                    text += f" Repealed by {repealed_by}. {note}"
                doc_id = f"{act_id}_s{sec_num}".replace(" ", "_").replace("/", "-")
                documents.append(text)
                metadatas.append({
                    "act_id": act_id, "act_title": act_title,
                    "act_year": str(act_year), "act_status": act_status,
                    "section": sec_num, "title": sec_title,
                    "full_text": "",
                    "source_verified": False,
                    "source_url": "", "source_sha256": "", "page": "",
                    "replaces": replaces, "repealed_by": repealed_by, "note": note,
                })
                ids.append(doc_id)

    # Defensive de-dup: ChromaDB rejects a whole upsert batch if it contains a duplicate
    # id, which aborts the seed and SILENTLY DROPS every act that sorts after the offender
    # (a corpus-wipe hit 2026-07-12 when an IPC mis-parse produced two "354E" sections —
    # 12 acts incl. the NI Act vanished). Keep the FIRST occurrence of each id: in document
    # order the real section precedes stray fragments. One bad section can never again nuke
    # the corpus.
    if len(set(ids)) != len(ids):
        seen: set[str] = set()
        ddoc, dmeta, dids = [], [], []
        for doc, meta, _id in zip(documents, metadatas, ids):
            if _id in seen:
                continue
            seen.add(_id)
            ddoc.append(doc); dmeta.append(meta); dids.append(_id)
        logger.warning(
            f"Seed de-dup: kept first of {len(ids) - len(dids)} duplicate section id(s) "
            f"(deterministic). These are recorded as PENDING_LEGAL_REVIEW anomalies — see "
            f"corpus_updates.corpus_anomalies() / docs/CORPUS_LIMITATIONS.md.")
        documents, metadatas, ids = ddoc, dmeta, dids

    BATCH = 100
    for i in range(0, len(documents), BATCH):
        collection.upsert(
            documents=documents[i:i+BATCH],
            metadatas=metadatas[i:i+BATCH],
            ids=ids[i:i+BATCH],
        )
    logger.info(f"Seeded {len(documents)} sections "
                f"({len(verified_act_ids)} acts source-verified).")


def reseed():
    """Force re-embed the entire corpus (call after updating law_index.json)."""
    # Disk preflight (S0.2): refuse BEFORE the destructive delete. A reseed on a near-full
    # volume is how the 2026-07-20 corruption happened — sqlite failed mid-write after the
    # old collection was already gone. Better to keep the working store than half-write a new one.
    free = disk_free_bytes()
    if free < RESEED_MIN_FREE_BYTES:
        raise RuntimeError(
            f"reseed refused: only {free / 1024**2:.0f} MB free on the volume backing "
            f"{CHROMA_PATH} (need >= {RESEED_MIN_FREE_BYTES // 1024**2} MB). Free space first — "
            f"a reseed on a near-full disk can corrupt the store (2026-07-20 incident).")

    client = _get_client()
    try:
        client.delete_collection(COLLECTION_NAME)
    except Exception as e:
        # Deleting a missing collection is fine (first-ever seed). Anything else must
        # NOT silently no-op: on 2026-07-20 a sqlite "disk full" here left the old
        # 8,072-chunk corpus in place and reseed() returned it as if freshly seeded.
        still = 0
        try:
            still = client.get_collection(COLLECTION_NAME).count()
        except Exception:
            pass
        if still:
            raise RuntimeError(
                f"reseed aborted: could not delete '{COLLECTION_NAME}' "
                f"({still} chunks still present): {e}") from e
    global _collection
    _collection = None
    return get_collection()
