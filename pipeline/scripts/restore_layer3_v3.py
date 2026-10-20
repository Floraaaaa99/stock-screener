#!/usr/bin/env python3
"""Restore the Layer 3 v3 issuer set from the committed pre-publish archive.

A plain ``tar -xzf`` overlay is not enough. The v4 tree has files the archive
does not contain (``0001790169.json``, ``0000759828.json``). Those must be
removed so the restored directory is the original 5,542-file v3 set plus the
v3 ``layer3.json`` index.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import tarfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_ARCHIVE = REPO_ROOT / "docs" / "validation" / "layer3-v3-pre-publish.tar.gz"
DEFAULT_MANIFEST = REPO_ROOT / "docs" / "validation" / "layer3-v3-pre-publish.manifest.json"
EXPECTED_FILES = 5542
EXPECTED_FINGERPRINT = "8d77cb1275f942b4"


def _fingerprint(cik_dir: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(cik_dir.glob("*.json")):
        digest.update(path.name.encode())
        digest.update(b"\0")
        digest.update(str(path.stat().st_size).encode())
        digest.update(b"\n")
    return digest.hexdigest()[:16]


def restore_layer3_v3(data_dir: Path, archive: Path, *, manifest: Path | None = None) -> dict:
    data_dir = Path(data_dir)
    archive = Path(archive)
    if not archive.is_file():
        raise FileNotFoundError(f"v3 archive not found: {archive}")

    cik_dir = data_dir / "layer3" / "cik"
    cik_dir.mkdir(parents=True, exist_ok=True)
    for path in cik_dir.glob("*.json"):
        path.unlink()

    with tarfile.open(archive, "r:gz") as tf:
        names = tf.getnames()
        if any(name.startswith("/") or ".." in Path(name).parts for name in names):
            raise ValueError("refusing archive with absolute or parent paths")
        extract_kwargs = {"filter": "data"} if hasattr(tarfile, "data_filter") else {}
        tf.extractall(data_dir, **extract_kwargs)

    files = list(cik_dir.glob("*.json"))
    fingerprint = _fingerprint(cik_dir)
    index = json.loads((data_dir / "layer3.json").read_text()) if (data_dir / "layer3.json").exists() else {}
    report = {
        "dataDir": str(data_dir),
        "issuerFiles": len(files),
        "fingerprint": fingerprint,
        "zeroFilePresent": (cik_dir / "0000000000.json").exists(),
        "canonicalZstkPresent": (cik_dir / "0001790169.json").exists(),
        "jhiPresent": (cik_dir / "0000759828.json").exists(),
        "indexSchemaVersion": index.get("schemaVersion"),
        "indexExtractionVersion": index.get("extractionVersion"),
        "indexBytes": (data_dir / "layer3.json").stat().st_size if (data_dir / "layer3.json").exists() else 0,
    }
    expected_fp = EXPECTED_FINGERPRINT
    expected_n = EXPECTED_FILES
    if manifest and Path(manifest).is_file():
        meta = json.loads(Path(manifest).read_text())
        expected_fp = meta.get("nameSizeFingerprint") or expected_fp
        expected_n = int(meta.get("issuerFiles") or expected_n)
        report["archiveSha256"] = meta.get("archiveSha256")
    errors = []
    if report["issuerFiles"] != expected_n:
        errors.append(f"issuer file count {report['issuerFiles']} != {expected_n}")
    if report["fingerprint"] != expected_fp:
        errors.append(f"fingerprint {report['fingerprint']} != {expected_fp}")
    if not report["zeroFilePresent"]:
        errors.append("0000000000.json missing after restore")
    if report["canonicalZstkPresent"] or report["jhiPresent"]:
        errors.append("v4-only ZSTK/JHI files still present")
    if report["indexSchemaVersion"] != 2 or report["indexExtractionVersion"] != 3:
        errors.append(
            f"index versions {report['indexSchemaVersion']}/{report['indexExtractionVersion']} != 2/3"
        )
    report["ok"] = not errors
    report["errors"] = errors
    return report


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--data-dir",
        required=True,
        help="Directory that contains layer3.json and layer3/cik (e.g. web/public/data)",
    )
    ap.add_argument("--archive", default=str(DEFAULT_ARCHIVE))
    ap.add_argument("--manifest", default=str(DEFAULT_MANIFEST))
    args = ap.parse_args(argv)
    report = restore_layer3_v3(Path(args.data_dir), Path(args.archive), manifest=Path(args.manifest))
    print(json.dumps(report, indent=2))
    return 0 if report["ok"] else 2


if __name__ == "__main__":
    sys.exit(main())
