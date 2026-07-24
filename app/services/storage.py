"""
File storage for case documents.

Local filesystem now, behind a small interface so Phase B can swap in S3 without touching
callers. Files are namespaced by tenant (data/uploads/<tenant_id>/...) which keeps tenants
physically separated on disk too. Validation (size/type) lives here so every caller is safe.
"""
import re
import uuid
import hashlib
from pathlib import Path

ROOT = Path(__file__).parent.parent.parent
UPLOAD_DIR = ROOT / "data" / "uploads"

MAX_BYTES = 20 * 1024 * 1024  # 20 MB
ALLOWED_EXT = {".pdf", ".docx", ".doc", ".txt", ".rtf", ".png", ".jpg", ".jpeg"}

# Magic-byte signatures per extension. Content sniffing so a renamed file (e.g. an executable
# saved as "brief.pdf") can't bypass the extension allowlist. Extensions absent here (.txt) have
# no reliable signature and are allowed by extension, but still screened for obvious binaries below.
_MAGIC: dict[str, list[bytes]] = {
    ".pdf":  [b"%PDF"],
    ".png":  [b"\x89PNG"],
    ".jpg":  [b"\xff\xd8\xff"],
    ".jpeg": [b"\xff\xd8\xff"],
    ".docx": [b"PK\x03\x04"],           # OOXML is a zip
    ".doc":  [b"\xd0\xcf\x11\xe0"],     # OLE compound file
    ".rtf":  [b"{\\rtf"],
}
# Signatures that must NEVER appear at the start of a supposed .txt (blatant spoofing).
_BINARY_SIGS: list[bytes] = [b"MZ", b"PK\x03\x04", b"\x7fELF", b"%PDF", b"\xd0\xcf\x11\xe0",
                             b"\x89PNG", b"\xff\xd8\xff", b"GIF8"]


class FileTooLarge(Exception):
    pass


class FileTypeNotAllowed(Exception):
    pass


def _content_matches_ext(ext: str, data: bytes) -> bool:
    """True if the file's leading bytes match what its extension claims."""
    sigs = _MAGIC.get(ext)
    if sigs is not None:
        return any(data[:len(s)] == s for s in sigs)
    if ext == ".txt":   # no signature, but reject an obvious binary masquerading as text
        return not any(data[:len(s)] == s for s in _BINARY_SIGS)
    return True


def _safe_name(name: str) -> str:
    name = (name or "file").strip().replace("\\", "/").split("/")[-1]
    return re.sub(r"[^A-Za-z0-9._-]+", "_", name)[:120] or "file"


def validate(filename: str, data: bytes) -> None:
    if len(data) > MAX_BYTES:
        raise FileTooLarge(f"File exceeds {MAX_BYTES // (1024*1024)} MB limit.")
    ext = Path(_safe_name(filename)).suffix.lower()
    if ext not in ALLOWED_EXT:
        raise FileTypeNotAllowed(f"File type '{ext or 'unknown'}' not allowed.")
    if not _content_matches_ext(ext, data):
        raise FileTypeNotAllowed(
            f"File content does not match its '{ext}' extension (possible renamed/spoofed file).")


def save_file(tenant_id: int, filename: str, data: bytes) -> dict:
    """Validate + persist bytes. Returns {storage_path, sha256, size, stored_name}."""
    validate(filename, data)
    safe = _safe_name(filename)
    tdir = UPLOAD_DIR / str(tenant_id)
    tdir.mkdir(parents=True, exist_ok=True)
    stored_name = f"{uuid.uuid4().hex}__{safe}"
    path = tdir / stored_name
    with open(path, "wb") as f:
        f.write(data)
    return {
        "storage_path": str(path.relative_to(ROOT)).replace("\\", "/"),
        "sha256": hashlib.sha256(data).hexdigest(),
        "size": len(data),
        "stored_name": stored_name,
    }


def read_file(storage_path: str) -> bytes | None:
    p = ROOT / storage_path
    if not p.exists():
        return None
    return p.read_bytes()


def delete_file(storage_path: str) -> None:
    try:
        (ROOT / storage_path).unlink(missing_ok=True)
    except Exception:
        pass
