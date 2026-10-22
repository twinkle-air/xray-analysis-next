"""Package the complete B delivery into a verified ZIP and browser-safe parts."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import zipfile


HERE = Path(__file__).resolve().parent
SOURCE = HERE.parent / "B-part-20261021"
ARCHIVE = HERE / "B-part-20261021.zip"
PARTS = HERE / "parts"
PART_SIZE = 8 * 1024 * 1024
BUFFER_SIZE = 1024 * 1024


def digest_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(BUFFER_SIZE):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> None:
    if not SOURCE.is_dir():
        raise SystemExit(f"missing source directory: {SOURCE}")
    if ARCHIVE.exists() or PARTS.exists():
        raise SystemExit("transport output exists; refusing to overwrite")
    files = sorted((p for p in SOURCE.rglob("*") if p.is_file()), key=lambda p: p.as_posix())
    if not files:
        raise SystemExit("source directory is empty")
    if any(p.is_symlink() for p in SOURCE.rglob("*")):
        raise SystemExit("source contains symbolic links")
    print(f"Packaging {len(files)} source files", flush=True)
    original_files = []
    with zipfile.ZipFile(ARCHIVE, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6, allowZip64=True) as archive:
        for number, path in enumerate(files, 1):
            rel = path.relative_to(SOURCE).as_posix()
            archive.write(path, f"{SOURCE.name}/{rel}")
            original_files.append({"path": rel, "bytes": path.stat().st_size, "sha256": digest_file(path)})
            if number % 500 == 0:
                print(f"Archived {number}/{len(files)}", flush=True)
    with zipfile.ZipFile(ARCHIVE) as archive:
        if archive.testzip() is not None:
            raise SystemExit("archive CRC verification failed")
        if len(archive.infolist()) != len(files):
            raise SystemExit("archive file count mismatch")
    original_manifest = {
        "source_dir": SOURCE.name,
        "file_count": len(files),
        "source_bytes": sum(item["bytes"] for item in original_files),
        "files": original_files,
    }
    (HERE / "source_manifest.json").write_text(json.dumps(original_manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    PARTS.mkdir()
    parts = []
    with ARCHIVE.open("rb") as source:
        for index, chunk in enumerate(iter(lambda: source.read(PART_SIZE), b""), 1):
            name = f"B-part-20261021.zip.part{index:04d}"
            target = PARTS / name
            target.write_bytes(chunk)
            parts.append({"path": f"parts/{name}", "bytes": len(chunk), "sha256": hashlib.sha256(chunk).hexdigest()})
    transport = {
        "format": "B-part-20261021-zip-parts-v1",
        "source_dir": SOURCE.name,
        "archive": ARCHIVE.name,
        "archive_bytes": ARCHIVE.stat().st_size,
        "archive_sha256": digest_file(ARCHIVE),
        "source_file_count": len(files),
        "source_bytes": original_manifest["source_bytes"],
        "part_size_bytes": PART_SIZE,
        "parts": parts,
    }
    (HERE / "transport_manifest.json").write_text(json.dumps(transport, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (HERE / "B-part-20261021.zip.sha256").write_text(f"{transport['archive_sha256']}  {ARCHIVE.name}\n", encoding="utf-8")
    print(json.dumps({key: transport[key] for key in ("archive_bytes", "archive_sha256", "source_file_count", "source_bytes")}, indent=2), flush=True)
    print(f"parts={len(parts)}", flush=True)


if __name__ == "__main__":
    main()
