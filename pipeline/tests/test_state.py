from __future__ import annotations

import json
from pathlib import Path

import pytest

from screener_pipeline.cache import write_json_atomic
from screener_pipeline.state import StateError, pack_state, read_sidecar_sha256, unpack_state


def _seed(state_dir: Path) -> None:
    write_json_atomic(state_dir / "facts" / "0000875320.json", {"cik": "0000875320", "byConcept": {}})
    write_json_atomic(state_dir / "statements" / "0001.json", {"accn": "0001", "rows": []})
    write_json_atomic(state_dir / "sic" / "0000875320.json", {"cik": "0000875320", "code": "2834"})
    write_json_atomic(state_dir / "stray-should-not-pack.json", {"secret": "nope"})


def test_pack_roundtrip_and_integrity(tmp_path: Path):
    state = tmp_path / "state"
    _seed(state)
    archive, sidecar, manifest = pack_state(state, tmp_path / "state.tar.gz", extra={"runId": "abc"})
    assert manifest["fileCount"] == 3
    assert "facts/0000875320.json" in manifest["files"]
    assert "sic/0000875320.json" in manifest["files"]
    digest = read_sidecar_sha256(sidecar)

    dest = tmp_path / "restored"
    unpacked = unpack_state(archive, dest, expected_sha256=digest)
    assert unpacked["fileCount"] == 3
    assert (dest / "facts" / "0000875320.json").exists()
    assert (dest / "sic" / "0000875320.json").exists()
    assert not (dest / "stray-should-not-pack.json").exists()


def test_tampered_file_is_rejected(tmp_path: Path):
    state = tmp_path / "state"
    _seed(state)
    archive, sidecar, _ = pack_state(state, tmp_path / "state.tar.gz")
    dest = tmp_path / "restored"
    unpack_state(archive, dest, expected_sha256=read_sidecar_sha256(sidecar))
    # Tamper after a successful unpack, then re-verify via a second pack of dest? Directly mess the archive.
    raw = bytearray(archive.read_bytes())
    raw[-20] ^= 0xFF
    archive.write_bytes(raw)
    with pytest.raises(StateError, match="SHA-256"):
        unpack_state(archive, tmp_path / "other", expected_sha256=read_sidecar_sha256(sidecar))


def test_recoverable_replace_keeps_destination_complete(tmp_path: Path):
    state = tmp_path / "state"
    _seed(state)
    archive, sidecar, _ = pack_state(state, tmp_path / "state.tar.gz")
    dest = tmp_path / "live"
    dest.mkdir()
    (dest / "stale.txt").write_text("old")
    unpack_state(archive, dest, expected_sha256=read_sidecar_sha256(sidecar))
    assert not (dest / "stale.txt").exists()
    assert json.loads((dest / "facts" / "0000875320.json").read_text())["cik"] == "0000875320"
