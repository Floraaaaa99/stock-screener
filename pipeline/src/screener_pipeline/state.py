"""Pack, verify and unpack compact pipeline state for a rolling GitHub Release asset.

Only SEC-derived compact facts, parsed statements, SIC records, and recent periodic filings are stored.
"""

from __future__ import annotations

import json
import shutil
import tarfile
import tempfile
from datetime import UTC, datetime
from pathlib import Path

from . import config
from .cache import sha256_file, write_json_atomic, write_text_atomic

INCLUDED_DIRS = ("facts", "statements", "sic", "periodic")
MANIFEST_NAME = "manifest.json"


class StateError(RuntimeError):
    pass


def _now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()


def write_manifest(state_dir: Path, extra: dict | None = None) -> dict:
    files: dict[str, str] = {}
    for rel in INCLUDED_DIRS:
        folder = state_dir / rel
        if not folder.exists():
            continue
        for path in sorted(folder.rglob("*.json")):
            files[str(path.relative_to(state_dir))] = sha256_file(path)
    manifest = {
        "version": config.STATE_VERSION,
        "createdAt": _now(),
        "fileCount": len(files),
        **{k: v for k, v in (extra or {}).items() if k not in {"version", "files"}},
        "files": files,
    }
    write_json_atomic(state_dir / MANIFEST_NAME, manifest)
    return manifest


def verify_unpacked(state_dir: Path) -> dict:
    path = state_dir / MANIFEST_NAME
    if not path.exists():
        raise StateError("State archive is missing manifest.json")
    manifest = json.loads(path.read_text(encoding="utf-8"))
    if manifest.get("version") != config.STATE_VERSION:
        raise StateError(f"Unsupported state version {manifest.get('version')}; expected {config.STATE_VERSION}")
    for rel, digest in (manifest.get("files") or {}).items():
        file_path = state_dir / rel
        if not file_path.exists():
            raise StateError(f"Missing state file {rel}")
        if sha256_file(file_path) != digest:
            raise StateError(f"Checksum mismatch for {rel}")
    return manifest


def pack_state(state_dir: Path, dest: Path, extra: dict | None = None) -> tuple[Path, Path, dict]:
    """Write dest and dest.sha256. Returns (archive, sidecar, manifest)."""
    manifest = write_manifest(state_dir, extra)
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_name(dest.name + ".partial")
    with tarfile.open(tmp, "w:gz") as tar:
        tar.add(state_dir / MANIFEST_NAME, arcname=MANIFEST_NAME)
        for rel in INCLUDED_DIRS:
            folder = state_dir / rel
            if folder.exists():
                tar.add(folder, arcname=rel)
    tmp.replace(dest)
    digest = sha256_file(dest)
    write_text_atomic(Path(str(dest) + ".sha256"), f"{digest}  {dest.name}\n")
    return dest, Path(str(dest) + ".sha256"), manifest


def unpack_state(archive: Path, dest_dir: Path, *, expected_sha256: str | None = None) -> dict:
    """Replace dest_dir with the archive contents after checksum verification.

    Recoverable: the new tree is fully verified as dest_dir.new before dest_dir is swapped.
    If the swap is interrupted, dest_dir.old or dest_dir.new can be used to recover.
    """
    if expected_sha256 and sha256_file(archive) != expected_sha256:
        raise StateError("Archive SHA-256 does not match the sidecar checksum")
    dest_dir.parent.mkdir(parents=True, exist_ok=True)
    new = dest_dir.with_name(dest_dir.name + ".new")
    old = dest_dir.with_name(dest_dir.name + ".old")
    if new.exists():
        shutil.rmtree(new)
    new.mkdir(parents=True)
    with tempfile.TemporaryDirectory(dir=dest_dir.parent) as tmp:
        tmp_path = Path(tmp)
        with tarfile.open(archive, "r:gz") as tar:
            try:
                tar.extractall(tmp_path, filter="data")
            except TypeError:
                tar.extractall(tmp_path)
        verify_unpacked(tmp_path)
        for item in tmp_path.iterdir():
            shutil.move(str(item), str(new / item.name))
    verify_unpacked(new)
    if old.exists():
        shutil.rmtree(old)
    if dest_dir.exists():
        dest_dir.replace(old)
    new.replace(dest_dir)
    if old.exists():
        shutil.rmtree(old)
    return verify_unpacked(dest_dir)


def read_sidecar_sha256(path: Path) -> str:
    text = path.read_text(encoding="utf-8").strip().split()[0]
    if len(text) != 64:
        raise StateError(f"Malformed SHA-256 sidecar {path}")
    return text
