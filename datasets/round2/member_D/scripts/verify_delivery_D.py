"""Independently verify the assembled member_D delivery tree."""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import zipfile
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]
DEFAULT_ROOT = (HERE if (HERE / "index_D.json").is_file()
                else HERE / "delivery" / "datasets" / "round2" / "member_D")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=DEFAULT_ROOT)
    args = parser.parse_args()
    root = args.root.resolve()
    errors: list[str] = []
    checked_hashes = 0

    sums = root / "SHA256SUMS"
    if not sums.is_file():
        print(f"Missing {sums}", file=sys.stderr)
        return 2
    listed = set()
    for number, line in enumerate(sums.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            digest, relative = line.split("  ", 1)
        except ValueError:
            errors.append(f"SHA256SUMS line {number} is malformed")
            continue
        listed.add(relative)
        path = root / relative
        if not path.is_file():
            errors.append(f"SHA256SUMS references missing file: {relative}")
        elif sha256(path) != digest:
            errors.append(f"SHA256SUMS hash mismatch: {relative}")
        else:
            checked_hashes += 1

    on_disk = {path.relative_to(root).as_posix() for path in root.rglob("*")
               if path.is_file() and path.name != "SHA256SUMS"}
    for missing in sorted(on_disk - listed):
        errors.append(f"File not covered by SHA256SUMS: {missing}")

    index = read_json(root / "index_D.json")
    rows = index.get("batches", [])
    if len(rows) != 30:
        errors.append(f"Index has {len(rows)} batches, expected 30")
    if sum(row.get("spectra", 0) for row in rows) != 1500:
        errors.append("Index spectra do not total 1500")
    if index.get("counts", {}).get("spectra") != 1500:
        errors.append("Index counts.spectra is not 1500")

    zip_spectra = 0
    for row in rows:
        batch_id = row["batch_id"]
        archive = root / row["sealed_dataset"]
        sidecar = archive.with_suffix(archive.suffix + ".sha256")
        if not archive.is_file() or not sidecar.is_file():
            errors.append(f"{batch_id}: archive or sidecar missing")
            continue
        digest = sha256(archive)
        if digest != row["zip_sha256"]:
            errors.append(f"{batch_id}: archive hash differs from index")
        if sidecar.read_text(encoding="ascii").split()[0] != digest:
            errors.append(f"{batch_id}: sidecar hash differs from archive")
        try:
            with zipfile.ZipFile(archive) as zf:
                if zf.testzip() is not None:
                    errors.append(f"{batch_id}: ZIP CRC failure")
                names = zf.namelist()
                manifest = json.loads(zf.read("manifest.json").decode("utf-8"))
                truth = [line for line in zf.read("truth.jsonl").decode("utf-8").splitlines()
                         if line.strip()]
                blind = sum(1 for name in names if name.startswith("blind_inputs/")
                            and name.endswith(".json"))
                full = sum(1 for name in names if name.startswith("full_results/")
                           and name.endswith(".json"))
                if manifest.get("status") != "complete":
                    errors.append(f"{batch_id}: archived manifest is not complete")
                if manifest.get("spectrum_count") != 50:
                    errors.append(f"{batch_id}: archived spectrum_count is not 50")
                if len(truth) != 50 or blind != 50 or full != 50:
                    errors.append(f"{batch_id}: archived truth/blind/full counts differ from 50")
                if "integrity.json" not in names or "README_dataset.md" not in names:
                    errors.append(f"{batch_id}: archive lacks integrity/readme files")
                zip_spectra += manifest.get("spectrum_count", 0)
        except (OSError, KeyError, ValueError, zipfile.BadZipFile) as exc:
            errors.append(f"{batch_id}: cannot read archive: {exc}")

        audit = read_json(root / row["audit"])
        replay = read_json(root / row["replay"])
        if audit.get("status") != "passed" or audit.get("spectra_checked") != 50:
            errors.append(f"{batch_id}: audit is not a clean 50-spectrum pass")
        if (replay.get("status") not in ("passed", "passed_with_environment_differences")
                or replay.get("scope") != "all_records"
                or replay.get("spectra_recalculated") != 50
                or replay.get("errors")):
            errors.append(f"{batch_id}: replay is not a clean full replay")

    if zip_spectra != 1500:
        errors.append(f"Archives contain {zip_spectra} spectra, expected 1500")

    production = read_json(root / "reports" / "production_D.json")
    if production.get("spectra") != 1500:
        errors.append("Production report spectra is not 1500")
    code = read_json(root / "code_verification.json")
    if code.get("unit_tests", {}).get("status") != "passed":
        errors.append("Generator unit tests are not recorded as passed")
    if any(item.get("status") != "passed" for item in code.get("compile", {}).values()):
        errors.append("A compile check did not pass")

    result = {
        "status": "passed" if not errors else "failed",
        "root": str(root),
        "batches": len(rows),
        "spectra": zip_spectra,
        "hashes_verified": checked_hashes,
        "files_on_disk": len(on_disk) + 1,
        "unit_tests": code.get("unit_tests"),
        "errors": errors,
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
