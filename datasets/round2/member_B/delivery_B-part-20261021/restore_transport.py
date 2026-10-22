"""Verify transport parts and reconstruct the complete B delivery ZIP."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import zipfile


HERE = Path(__file__).resolve().parent
BUFFER_SIZE = 1024 * 1024


def digest_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(BUFFER_SIZE):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--extract", action="store_true", help="also extract and check every original file")
    args = parser.parse_args()
    manifest = json.loads((HERE / "transport_manifest.json").read_text(encoding="utf-8"))
    archive_path = HERE / manifest["archive"]
    combined = hashlib.sha256()
    combined_bytes = 0
    for part in manifest["parts"]:
        path = HERE / part["path"]
        if not path.is_file() or path.stat().st_size != part["bytes"]:
            raise SystemExit(f"missing or wrong-sized part: {part['path']}")
        if digest_file(path) != part["sha256"]:
            raise SystemExit(f"part hash mismatch: {part['path']}")
        with path.open("rb") as source:
            while chunk := source.read(BUFFER_SIZE):
                combined.update(chunk)
                combined_bytes += len(chunk)
    if combined_bytes != manifest["archive_bytes"] or combined.hexdigest() != manifest["archive_sha256"]:
        raise SystemExit("combined parts do not match archive manifest")
    print(f"Verified {len(manifest['parts'])} transport parts")
    if archive_path.exists():
        if digest_file(archive_path) != manifest["archive_sha256"]:
            raise SystemExit("existing ZIP conflicts with manifest; refusing to overwrite")
        print("Existing ZIP verified")
    else:
        temp_path = archive_path.with_suffix(".zip.partial")
        if temp_path.exists():
            raise SystemExit("partial ZIP exists; refusing to overwrite")
        digest = hashlib.sha256()
        total = 0
        with temp_path.open("xb") as output:
            for part in manifest["parts"]:
                path = HERE / part["path"]
                with path.open("rb") as source:
                    while chunk := source.read(BUFFER_SIZE):
                        output.write(chunk)
                        digest.update(chunk)
                        total += len(chunk)
        if total != manifest["archive_bytes"] or digest.hexdigest() != manifest["archive_sha256"]:
            raise SystemExit("reconstructed ZIP hash or size mismatch; partial file retained")
        temp_path.replace(archive_path)
        print("ZIP reconstructed and SHA-256 verified")
    with zipfile.ZipFile(archive_path) as archive:
        if archive.testzip() is not None:
            raise SystemExit("ZIP CRC verification failed")
        if len(archive.infolist()) != manifest["source_file_count"]:
            raise SystemExit("ZIP file count mismatch")
        print(f"ZIP CRC and {len(archive.infolist())} entries verified")
        if args.extract:
            output_dir = HERE / manifest["source_dir"]
            if output_dir.exists():
                raise SystemExit("target folder exists; refusing to overwrite")
            source_manifest = json.loads((HERE / "source_manifest.json").read_text(encoding="utf-8"))
            expected = {item["path"]: item for item in source_manifest["files"]}
            for info in archive.infolist():
                internal = PurePosixPath(info.filename)
                if internal.is_absolute() or ".." in internal.parts or internal.parts[0] != manifest["source_dir"]:
                    raise SystemExit(f"unsafe ZIP path: {info.filename}")
                rel = PurePosixPath(*internal.parts[1:]).as_posix()
                if rel not in expected or info.file_size != expected[rel]["bytes"]:
                    raise SystemExit(f"ZIP entry conflicts with source manifest: {info.filename}")
            archive.extractall(HERE)
            for rel, item in expected.items():
                path = output_dir / Path(rel)
                if digest_file(path) != item["sha256"]:
                    raise SystemExit(f"extracted file hash mismatch: {rel}")
            print(f"Extracted and SHA-256 verified {len(expected)} source files")


if __name__ == "__main__":
    main()
