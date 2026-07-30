"""
Vector store — ChromaDB backed by OpenAI embeddings.
Indexes every section from law_index.json as a searchable document.
"""
import os
import json
import logging
import shutil
import socket
import tempfile
import time
from contextlib import contextmanager
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

# Reseed atomicity. A reseed used to delete the live collection FIRST and then embed for
# minutes; any interruption in that window left the store empty or truncated while still
# answering queries, just with most of the law missing. It happened three times
# (2026-07-20 disk-full, 2026-07-25 and 2026-07-29 concurrent/killed runs — the last left
# 1,200 of 8,704 chunks). The index is now built HERE and renamed over the live collection
# only once complete.
BUILD_COLLECTION_NAME     = COLLECTION_NAME + "__building"
RESEED_LOCK_PATH          = CHROMA_PATH / ".reseed.lock"
RESEED_LOCK_STALE_SECONDS = 300    # a LIVE reseed touches the lock every batch (see
                                   # _reseed_lock); 5 min of silence means the holder died
RESEED_SHRINK_RATIO       = 0.9    # refuse to swap in a build this much smaller than live


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


def _embedding_fn():
    """The embedding function for the corpus collection.

    Extracted so the reseed build collection is created with the IDENTICAL function — a
    build embedded differently from the live collection would swap in silently and return
    nonsense for every query.
    """
    import chromadb.utils.embedding_functions as ef
    # Embeddings default to a FREE local model (ONNX MiniLM, runs on CPU, no API/cost).
    # Only use paid OpenAI embeddings if explicitly opted in via OPENAI_EMBEDDINGS_KEY —
    # this keeps a free LLM key (AI_API_KEY / OPENAI_API_KEY) from triggering paid embed calls.
    emb_key = os.getenv("OPENAI_EMBEDDINGS_KEY", "").strip()
    if emb_key:
        return ef.OpenAIEmbeddingFunction(api_key=emb_key, model_name=EMBEDDING_MODEL)
    return ef.DefaultEmbeddingFunction()   # free, local, no key


def get_collection():
    """Return the ChromaDB collection, creating it if it doesn't exist."""
    global _collection
    if _collection is not None:
        return _collection

    client = _get_client()

    try:
        _adopt_orphaned_build(client)

        _collection = client.get_or_create_collection(
            name=COLLECTION_NAME,
            embedding_function=_embedding_fn(),
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


def _seed_collection(collection, heartbeat=None, fulltext_dir=None, corpus_dir=None):
    """
    Embed sections into the vector store.

    ``fulltext_dir`` / ``corpus_dir`` override the module-level paths so a reseed can read
    from a frozen SNAPSHOT instead of the live corpus. A full build takes minutes and reads
    the JSON files progressively; if ingest() rewrites one partway through, the index mixes
    two corpus versions and matches no fingerprint. Nothing about that is visible in the
    chunk count. Defaults keep the live paths for the boot-time first seed.

    Priority: any Act that has a SOURCE-VERIFIED full-text file in legal_corpus/fulltext/
    is indexed from that file (verbatim text, quotable, with provenance). For every other
    Act we fall back to the heading-only index files in legal_corpus/. We never index both
    for the same Act, so verified full text always supersedes headings.
    """
    documents, metadatas, ids = [], [], []
    verified_act_ids: set[str] = set()
    ft_dir = fulltext_dir or FULLTEXT_DIR
    cp_dir = corpus_dir or CORPUS_DIR

    # ── Pass 1: source-verified full-text files (preferred) ──────────────────────
    if ft_dir.exists():
        for ft_file in sorted(ft_dir.glob("*.fulltext.json")):
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
    for corpus_file in sorted(cp_dir.glob("*.json")):
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
        if heartbeat:
            heartbeat()   # prove the reseed is alive; see _reseed_lock
    logger.info(f"Seeded {len(documents)} sections "
                f"({len(verified_act_ids)} acts source-verified).")


@contextmanager
def _corpus_snapshot():
    """Freeze the corpus JSON for the duration of a build.

    A reseed reads ~50 fulltext files PROGRESSIVELY over several minutes. If ingest()
    rewrites one partway through — re-parsing an act while a reseed runs — the resulting
    index mixes two corpus versions. It matches no fingerprint, the chunk count looks
    entirely normal, and every guard added on 2026-07-29 passes it: build-then-swap only
    protects against a build DYING, not against one reading a corpus that changes
    underneath it. Hit for real on 2026-07-30.

    ~15 MB, so the copy is cheap next to a store measured in hundreds. On failure it falls
    back to the live paths rather than refusing to reseed — a snapshot is a safety margin,
    not a precondition.
    """
    tmp = None
    try:
        tmp = Path(tempfile.mkdtemp(prefix="juriscite-corpus-"))
        snap_ft = tmp / "fulltext"
        snap_ft.mkdir()
        for f in CORPUS_DIR.glob("*.json"):
            shutil.copy2(f, tmp / f.name)
        if FULLTEXT_DIR.exists():
            for f in FULLTEXT_DIR.glob("*.fulltext.json"):
                shutil.copy2(f, snap_ft / f.name)
        logger.info(f"Corpus snapshot taken for this reseed ({tmp}).")
        yield snap_ft, tmp
    except OSError as e:
        logger.warning(f"Could not snapshot the corpus ({e}); reading it live instead. "
                       f"Do NOT run ingest() until this reseed finishes.")
        yield None, None
    finally:
        if tmp:
            shutil.rmtree(tmp, ignore_errors=True)


def _store_size_bytes() -> int:
    """Bytes currently occupied by the Chroma store, 0 if it doesn't exist yet.

    Used to size the reseed disk floor: the rebuild is a second copy that must fit beside
    the live index. Never raises — an unreadable store must not block a reseed, it just
    falls back to the flat floor.
    """
    try:
        return sum(f.stat().st_size for f in Path(CHROMA_PATH).rglob("*") if f.is_file())
    except OSError:
        return 0


@contextmanager
def _reseed_lock():
    """Refuse a second concurrent reseed rather than let two writers race.

    Two overlapping reseeds corrupted the store twice (2026-07-25, 2026-07-29): the second
    process deleted the collection the first was still writing into, ChromaDB threw inside
    upsert, and ~4,200 of 8,637 chunks survived.

    Yields a ``heartbeat()`` that the build loop calls each batch. Without it the lock can
    only be judged stale by age, and a HARD-KILLED reseed (no finally, no cleanup) wedges
    every later reseed until that timeout expires — which happened twice on 2026-07-29 and
    needed the file deleted by hand. A live reseed now refreshes the lock continuously, so
    silence is real evidence the holder is gone and the timeout can be short.

    Staleness is decided by MTIME, never by probing the recorded pid. On Windows
    ``os.kill(pid, 0)`` does not test liveness — CPython maps a non-CTRL signal to
    TerminateProcess, so the "is it alive?" check would KILL the process it asks about. The
    pid is recorded for humans to read, nothing more.
    """
    RESEED_LOCK_PATH.parent.mkdir(parents=True, exist_ok=True)
    if RESEED_LOCK_PATH.exists():
        age = time.time() - RESEED_LOCK_PATH.stat().st_mtime
        if age < RESEED_LOCK_STALE_SECONDS:
            try:
                holder = RESEED_LOCK_PATH.read_text(encoding="utf-8").strip()
            except OSError:
                holder = "unknown"
            raise RuntimeError(
                f"reseed refused: another reseed is in progress ({holder}, started "
                f"{age:.0f}s ago). Concurrent reseeds corrupt the store. If that process is "
                f"definitely dead, delete {RESEED_LOCK_PATH}.")
        logger.warning(f"Reseed lock is stale ({age:.0f}s old) — taking it over.")
        RESEED_LOCK_PATH.unlink(missing_ok=True)

    try:
        fd = os.open(str(RESEED_LOCK_PATH), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError as e:      # lost the race between the check above and here
        raise RuntimeError(
            f"reseed refused: another reseed took the lock at {RESEED_LOCK_PATH}.") from e
    try:
        os.write(fd, f"pid={os.getpid()} host={socket.gethostname()}".encode())
    finally:
        os.close(fd)
    def heartbeat():
        """Refresh the lock's mtime; never fatal — a reseed must not die over a touch."""
        try:
            os.utime(RESEED_LOCK_PATH, None)
        except OSError:
            pass

    try:
        yield heartbeat
    finally:
        RESEED_LOCK_PATH.unlink(missing_ok=True)


def _adopt_orphaned_build(client) -> bool:
    """Finish a swap that was interrupted between the delete and the rename.

    That window is two metadata operations wide, but a process dying inside it leaves the
    live collection gone and a COMPLETE build collection beside it. Completing the rename
    is strictly better than re-embedding the whole corpus.
    """
    try:
        names = {c.name for c in client.list_collections()}
    except Exception:
        return False
    if COLLECTION_NAME in names or BUILD_COLLECTION_NAME not in names:
        return False
    try:
        build = client.get_collection(BUILD_COLLECTION_NAME)
        n = build.count()
        if n == 0:
            client.delete_collection(BUILD_COLLECTION_NAME)
            return False
        logger.warning(
            f"Found a build collection with {n} chunks and NO live collection — a reseed "
            f"died mid-swap. Completing the rename instead of re-embedding.")
        build.modify(name=COLLECTION_NAME)
        return True
    except Exception as e:
        logger.error(f"Could not adopt orphaned build collection: {e}")
        return False


def reseed(force: bool = False):
    """Rebuild the corpus index, swapping it in only once it is COMPLETE.

    The index is built in a SEPARATE collection and the live one is replaced by a rename
    after the build succeeds and passes a size check, so an interrupted build cannot touch
    the live corpus at all. The only destructive window is delete+rename, which does no
    embedding work and is recoverable by _adopt_orphaned_build().

    ``force=True`` waives the shrink check, for when the corpus genuinely got smaller.
    """
    # Disk preflight (S0.2): refuse before doing any work. A reseed on a near-full volume is
    # how the 2026-07-20 corruption happened — sqlite failed mid-write.
    #
    # The floor is DYNAMIC, because build-then-swap changed the disk profile: the build is a
    # second full copy of the index that must fit ALONGSIDE the live one until the rename.
    # The old delete-first reseed freed that space before writing; this one cannot. A flat
    # 500 MB floor would let a reseed start and then run out of room deep into the embed —
    # safe (the live corpus is never touched) but a slow and confusing way to fail.
    free = disk_free_bytes()
    needed = max(RESEED_MIN_FREE_BYTES, _store_size_bytes() + RESEED_MIN_FREE_BYTES)
    if free < needed:
        raise RuntimeError(
            f"reseed refused: {free / 1024**2:.0f} MB free on the volume backing "
            f"{CHROMA_PATH}, need >= {needed / 1024**2:.0f} MB. The rebuild is written "
            f"beside the live index and only replaces it once complete, so it needs room "
            f"for both ({_store_size_bytes() / 1024**2:.0f} MB store + "
            f"{RESEED_MIN_FREE_BYTES // 1024**2} MB headroom). Free space first — a reseed "
            f"on a near-full disk can corrupt the store (2026-07-20 incident).")

    with _reseed_lock() as heartbeat:
        client = _get_client()

        live_count = 0
        try:
            live_count = client.get_collection(COLLECTION_NAME).count()
        except Exception:
            pass   # no live collection yet (first-ever seed)

        # A build collection left by an earlier crash is scrap — it may be partial, and
        # nothing distinguishes a complete one from a truncated one at this point.
        try:
            client.delete_collection(BUILD_COLLECTION_NAME)
        except Exception:
            pass

        build = client.create_collection(
            name=BUILD_COLLECTION_NAME,
            embedding_function=_embedding_fn(),
            metadata={"hnsw:space": "cosine"},
        )
        try:
            with _corpus_snapshot() as (snap_ft, snap_cp):
                _seed_collection(build, heartbeat=heartbeat,
                                 fulltext_dir=snap_ft, corpus_dir=snap_cp)
            built = build.count()

            if built == 0:
                raise RuntimeError(
                    "reseed aborted: the rebuild produced 0 chunks, so it was NOT swapped "
                    "in — the live corpus is untouched. Check that "
                    "app/legal_corpus/fulltext/*.json is populated.")
            if live_count and built < live_count * RESEED_SHRINK_RATIO and not force:
                raise RuntimeError(
                    f"reseed aborted: the rebuild holds {built} chunks against {live_count} "
                    f"live (below {RESEED_SHRINK_RATIO:.0%}), so it was NOT swapped in — the "
                    f"live corpus is untouched. This is the shape of a truncated build "
                    f"(2026-07-29 left 1,200 of 8,704). If the corpus genuinely shrank, "
                    f"re-run with reseed(force=True).")
        except BaseException:
            # BaseException, not Exception: a Ctrl-C'd reseed raises KeyboardInterrupt, and
            # leaving a partial build behind on the commonest interruption of all defeats
            # the point. A hard kill still cannot be caught here — that is what the
            # scrap-delete above and _adopt_orphaned_build() are for.
            try:
                client.delete_collection(BUILD_COLLECTION_NAME)
            except Exception:
                pass
            raise

        # ── swap: metadata only, no embedding work ──────────────────────────────────
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
                try:
                    client.delete_collection(BUILD_COLLECTION_NAME)
                except Exception:
                    pass
                raise RuntimeError(
                    f"reseed aborted: could not delete '{COLLECTION_NAME}' "
                    f"({still} chunks still present): {e}") from e
        build.modify(name=COLLECTION_NAME)
        logger.info(f"Reseed complete: {built} chunks swapped in atomically.")

    global _collection
    _collection = None
    return get_collection()
