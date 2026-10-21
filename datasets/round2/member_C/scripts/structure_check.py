# -*- coding: utf-8 -*-
"""Cross-batch structure check for member C v2 (run after generation)."""
import argparse
import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", required=True, help="v2 directory with batches/")
    ap.add_argument("--samples", required=True, help="C_r2_samples.json")
    ap.add_argument("--profiles", required=True, help="sealed generator profiles dir")
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    base = Path(args.base)
    samples = json.loads(Path(args.samples).read_text(encoding="utf-8"))["samples"]
    sample_ids = [s["id"] for s in samples]
    sample_set = set(sample_ids)
    profile_files = {
        tag: json.loads((Path(args.profiles) / f"{tag}.json").read_text(encoding="utf-8"))
        for tag in ("P1", "P2", "P3")}

    report = {"version": "C-r2-v2", "checks": {}, "batches": {}, "errors": []}
    all_seeds = []
    all_records = []
    split_by_family = {}
    comp_by_sample = {}

    for tag in ("P1", "P2", "P3"):
        ds = base / "batches" / f"C_r2_{tag}"
        truth = [json.loads(line) for line in
                 (ds / "truth.jsonl").read_text(encoding="utf-8").splitlines() if line]
        blind = sorted((ds / "blind_inputs").glob("*.json"))
        full = sorted((ds / "full_results").glob("*.json"))
        ids = [r["id"] for r in truth]
        sample_counts = Counter(r["original_sample_id"] for r in truth)
        repeats = Counter(r["repeat"] for r in truth)
        seeds = [r["seed"] for r in truth]
        splits = Counter(r["split"] for r in truth)
        profiles = {json.dumps(r["profile"], sort_keys=True) for r in truth}
        profile_ok = len(profiles) == 1 and json.loads(next(iter(profiles))) == profile_files[tag]
        fam_splits = defaultdict(set)
        for r in truth:
            fam_splits[r["family"]].add(r["split"])
            split_by_family.setdefault(r["family"], set()).add(r["split"])
            prev = comp_by_sample.setdefault(r["original_sample_id"],
                                             r["composition"])
            if prev != r["composition"]:
                report["errors"].append(
                    f"{tag}: composition differs for {r['original_sample_id']}")

        batch_ok = (
            len(truth) == 500
            and len(blind) == 500 and len(full) == 500
            and len(set(ids)) == 500
            and set(sample_counts) == sample_set
            and set(sample_counts.values()) == {2}
            and set(repeats) == {0, 1}
            and all(v == 2 for v in sample_counts.values())
            and len(set(seeds)) == 500
            and profile_ok
        )
        if not batch_ok:
            report["errors"].append(f"{tag}: batch structure check failed")
        report["batches"][tag] = {
            "truth_records": len(truth),
            "blind_inputs": len(blind),
            "full_results": len(full),
            "unique_ids": len(set(ids)),
            "unique_sample_ids": len(sample_counts),
            "duplicate_sample_ids": sorted(k for k, v in sample_counts.items() if v != 2),
            "repeats": dict(repeats),
            "unique_seeds": len(set(seeds)),
            "profile_matches_common_input": profile_ok,
            "splits": dict(sorted(splits.items())),
            "samples": len(samples),
            "ok": batch_ok,
        }
        all_seeds.extend(seeds)
        all_records.extend((tag, r) for r in truth)

    bad_family = {k: sorted(v) for k, v in split_by_family.items() if len(v) != 1}
    checks = {
        "batches_structural_ok": all(b["ok"] for b in report["batches"].values()),
        "same_sample_set_all_batches": all(
            b["unique_sample_ids"] == len(sample_set) for b in report["batches"].values()),
        "two_replicates_each_condition": all(
            b["repeats"] == {0: 250, 1: 250} for b in report["batches"].values()),
        "sub_seeds_unique_across_batches": len(all_seeds) == len(set(all_seeds)),
        "composition_consistent_per_sample": not any(
            "composition differs" in e for e in report["errors"]),
        "family_split_consistent_across_conditions": not bad_family,
        "total_spectra": sum(b["truth_records"] for b in report["batches"].values()),
    }
    report["checks"] = checks
    report["nominal_split_counts"] = dict(sorted(Counter(
        r["split"] for _tag, r in all_records).items())) if all_records else {}
    report["bad_family_splits"] = bad_family
    report["duplicate_raw_ids_across_batches"] = sorted(
        k for k, v in Counter(r["id"] for _tag, r in all_records).items() if v > 1)
    report["namespace_note"] = (
        "Raw ids S000001... repeat in every condition; the global index must key "
        "on owner/batch/record_id. Sub-seeds are unique across the three batches.")
    report["ok"] = (checks["batches_structural_ok"]
                    and checks["same_sample_set_all_batches"]
                    and checks["two_replicates_each_condition"]
                    and checks["sub_seeds_unique_across_batches"]
                    and checks["composition_consistent_per_sample"]
                    and checks["family_split_consistent_across_conditions"]
                    and checks["total_spectra"] == 1500)
    Path(args.out).write_text(json.dumps(report, ensure_ascii=False, indent=1),
                              encoding="utf-8")
    print(json.dumps({"ok": report["ok"], "checks": checks}, ensure_ascii=False))


if __name__ == "__main__":
    main()
