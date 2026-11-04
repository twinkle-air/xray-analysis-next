"""P1 functional verification: drive the four documented tools over the 6-file test set.

Usage: python verify_p1.py   (run from the repository root)
Exit code 0 only when every fixed case behaves as specified in 03_验收参考/任务清单.csv.
"""
from __future__ import annotations

import hashlib
import json
import math
import pathlib
import sys

import verify_common
# agent sits directly here (flat layout) or under agent-workspace/ (repository layout);
# it must be importable before the package imports below.
sys.path.insert(0, str(verify_common.PACKAGE_PARENT))
from agent.core.reporting import _between, _parse_number, _table_rows
from agent.core.paths import write_json

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE
SPECTRA = ROOT / "deliverables" / "智能体功能测试谱集-20261031"
REF = SPECTRA / "03_验收参考"
JOBS = ROOT / "jobs"

CASES = [
    ("T01", "01_正常输入/T01.json", "V10", "03_验收参考/T01_V10.json"),
    ("T02", "01_正常输入/T02.json", "V10", "03_验收参考/T02_V10.json"),
    ("T03", "01_正常输入/T03.json", "V10", "03_验收参考/T03_V10.json"),
    ("T04", "01_正常输入/T04_重复上传.json", "V10", "03_验收参考/T01_V10.json"),
    ("T05", "02_异常输入/T05_全零计数.json", None, None),
    ("T06", "02_异常输入/T06_错误道数.json", None, None),
]

RTOL, ATOL = 1e-9, 1e-10

failures = []


def check(name, condition, detail=""):
    if condition:
        print(f"  PASS {name}")
    else:
        failures.append((name, detail))
        print(f"  FAIL {name}: {detail}")


def run(args):
    obj, rc, err = verify_common.run(args)
    return obj, rc, err


def state_of(job_id):
    return json.loads((JOBS / job_id / "audit" / "state.json").read_text(encoding="utf-8"))


def sha(path):
    return hashlib.file_digest(open(path, "rb"), "sha256").hexdigest()


def close(a, b):
    if a == b:
        return True
    if not (math.isfinite(a) and math.isfinite(b)):
        return False
    return abs(a - b) <= ATOL + RTOL * max(abs(a), abs(b))


def main():
    if JOBS.exists():
        verify_common.rmtree(JOBS)
    print(f"workspace root: {ROOT}\n")

    job_ids = {}
    for case_id, rel, model, ref_rel in CASES:
        path = SPECTRA / rel
        print(f"--- {case_id} ({path.name})")
        obj, rc, err = run(["analyze", "--task-file", str(path)])
        status, error_code = obj.get("status"), obj.get("error_code")
        print(f"     status={status} error_code={error_code} job={obj.get('job_id')} rc={rc}")

        if case_id in ("T05", "T06"):
            check("rejected", status == "failed", f"status={status}")
            check("explicit error code", error_code == "INVALID_COUNTS", f"error_code={error_code}")
            check("no inference artifact",
                  not (JOBS / obj["job_id"] / "inference" / "result.json").exists(),
                  "inference file published for a rejected input")
            check("no report artifact",
                  not (JOBS / obj["job_id"] / "report").exists(),
                  "report dir created for bad input")
            if err:
                print(f"     stderr: {err.strip().splitlines()[-1][:160]}")
            continue

        check("succeeded", status == "succeeded", f"status={status}")
        check("no error", error_code is None, f"error_code={error_code}")
        check("model locked to V10", obj.get("model_version") == "V10")
        job_ids[case_id] = obj["job_id"]

        ref = json.loads((REF / ref_rel.split("/")[-1]).read_text(encoding="utf-8"))
        got = json.loads((JOBS / obj["job_id"] / "inference" / "result.json").read_text(encoding="utf-8"))
        meta = {k: got[k] for k in got if k != "predicted_element_percent"}
        meta_ref = {k: ref[k] for k in ref if k != "predicted_element_percent"}
        check("metadata matches reference", meta == meta_ref,
              f"diff={sorted(set(meta) ^ set(meta_ref))}")
        nz = sorted(((k, v) for k, v in got["predicted_element_percent"].items() if v > 0),
                    key=lambda kv: -kv[1])
        ref_nz = sorted(((k, v) for k, v in ref["predicted_element_percent"].items() if v > 0),
                        key=lambda kv: -kv[1])
        check("nonzero elements match reference", nz == ref_nz,
              f"got {[e for e, _ in nz]} vs ref {[e for e, _ in ref_nz]}")
        check("all 32 values within rtol=1e-9/atol=1e-10",
              all(close(got["predicted_element_percent"][e], ref["predicted_element_percent"][e])
                  for e in ref["predicted_element_percent"]))
        check("input hash matches file hash", obj["input_sha256"] == sha(path),
              f"{obj['input_sha256'][:12]} vs {sha(path)[:12]}")
        print()

    print("--- T04 dedup / no overwrite of T01")
    t4 = state_of(job_ids["T04"])
    t1 = state_of(job_ids["T01"])
    check("distinct job ids", job_ids["T04"] != job_ids["T01"],
          f"t4={job_ids['T04']} t1={job_ids['T01']}")
    check("same input hash", t4["input_sha256"] == t1["input_sha256"])
    check("reuse recorded", t4.get("reused_from") == job_ids["T01"],
          f"reused_from={t4.get('reused_from')}")
    g4 = json.loads((JOBS / job_ids["T04"] / "inference" / "result.json").read_text(encoding="utf-8"))
    g1 = json.loads((JOBS / job_ids["T01"] / "inference" / "result.json").read_text(encoding="utf-8"))
    check("identical predictions", g4["predicted_element_percent"] == g1["predicted_element_percent"])
    g1_again = json.loads((JOBS / job_ids["T01"] / "inference" / "result.json").read_text(encoding="utf-8"))
    check("T01 result untouched", g1_again == g1)
    print()

    print("--- input immutability")
    original = JOBS / job_ids["T01"] / "input" / "T01.json"
    check("original bytes preserved", sha(original) == sha(SPECTRA / "01_正常输入" / "T01.json"))
    try:
        original.write_text("tampered", encoding="utf-8")
        check("read-only enforced", False, "original was overwritten")
        original.write_text("repaired", encoding="utf-8")
    except (OSError, PermissionError):
        check("read-only enforced", True)
    print()

    print("--- F01 damaged dedup cache must not be trusted")
    cached = JOBS / job_ids["T01"] / "inference" / "result.json"
    backup = cached.read_text(encoding="utf-8")
    corrupted = json.loads(backup)
    corrupted["predicted_element_percent"]["Fe"] = 12345.0
    write_json(cached, corrupted)
    obj, rc, err = run(["analyze", "--task-file", str(SPECTRA / "01_正常输入" / "T04_重复上传.json")])
    cached.write_text(backup, encoding="utf-8")
    print(f"     rc={rc} status={obj.get('status')} reused_from={obj.get('reused_from')}")
    check("corrupted cache rejected instead of reused", obj.get("status") == "succeeded",
          f"status={obj.get('status')}")
    check("Fe restored to the real model value",
          json.loads((JOBS / obj["job_id"] / "inference" / "result.json").read_text(encoding="utf-8"))
          ["predicted_element_percent"]["Fe"] == g1["predicted_element_percent"]["Fe"])
    print()

    print("--- huge integer counts are rejected structurally, not via a math error")
    huge = json.loads((SPECTRA / "01_正常输入" / "T01.json").read_text(encoding="utf-8"))
    huge["counts"][0] = 10**400
    huge_path = ROOT / "jobs" / ".tmp-huge.json"
    write_json(huge_path, huge)
    obj, rc, err = run(["analyze", "--task-file", str(huge_path)])
    huge_path.unlink()
    print(f"     rc={rc} status={obj.get('status')} error={obj.get('error_code')}")
    check("rejected with INVALID_COUNTS", obj.get("error_code") == "INVALID_COUNTS",
          f"error_code={obj.get('error_code')}")
    check("no OverflowError surfaced", "OverflowError" not in err, err[:200])
    print()

    print("--- compare_models on T01")
    obj, rc, err = run(["compare", "--job-id", job_ids["T01"]])
    print(f"     rc={rc} v9_job={obj.get('v9_job_id')} note={obj.get('note')[:100]}")
    check("compare succeeded", rc == 0 and obj.get("error_code") is None,
          f"rc={rc} error_code={obj.get('error_code')} {err[:200]}")
    check("separate v9 job", bool(obj.get("v9_job_id")) and obj["v9_job_id"] != job_ids["T01"])
    v9 = json.loads((JOBS / obj["v9_job_id"] / "inference" / "result.json").read_text(encoding="utf-8"))
    check("V9 preserved separately", v9.get("version") == "V9")
    ref_v9 = json.loads((REF / "T01_V9.json").read_text(encoding="utf-8"))
    check("V9 matches reference", v9["predicted_element_percent"] == ref_v9["predicted_element_percent"],
          f"got {sum(1 for v in v9['predicted_element_percent'].values() if v > 0)} nonzero")
    check("V10 unchanged",
          json.loads((JOBS / job_ids["T01"] / "inference" / "result.json").read_text(encoding="utf-8"))
          ["predicted_element_percent"] == g1["predicted_element_percent"])
    check("differing elements reported", len(obj["differing_elements"]) > 0,
          f"{len(obj['differing_elements'])}")
    check("abs_diff_ppm is the true signed gap",
          all(abs(d["abs_diff_ppm"] - abs(d["v10_mass_percent"] - d["v9_mass_percent"]) * 10000) <= 1e-6
              for d in obj["differing_elements"]))
    print()

    print("--- export_report on T01 (with comparison)")
    obj, rc, err = run(["export", "--job-id", job_ids["T01"], "--include-comparison"])
    print(f"     rc={rc} consistency={obj.get('consistency_check')} md={obj.get('markdown_path')}")
    v9_job_id = json.loads((JOBS / job_ids["T01"] / "inference" / "comparison.json").read_text(encoding="utf-8"))["v9_job_id"]
    check("export succeeded", obj.get("status") == "exported",
          f"status={obj.get('status')} {err[:200]}")
    check("consistency passed", obj.get("consistency_check") is True,
          f"consistency_check={obj.get('consistency_check')}")
    md_path = pathlib.Path(obj["markdown_path"])
    check("markdown written", md_path.exists())
    json_path = pathlib.Path(obj["json_path"])
    check("json written", json_path.exists())
    md = md_path.read_text(encoding="utf-8")
    check("declares research draft", "formal_report_eligible=false" in md
          and "hardware_validated=false" in md)
    check("carries job id", job_ids["T01"] in md)
    check("carries the research-draft disclaimer", "不构成定量验收结论" in md)
    check("renders non-reported as '本模型未报出'", "本模型未报出" in md)
    data_rows = [r for r in _table_rows(_between(md, "## 2.", "## 3.")) if r[1] in ("报出", "未报出")]
    check("non-reported rows render 本模型未报出",
          all(r[2] == "本模型未报出" and r[3] == "本模型未报出"
              for r in data_rows if r[1] == "未报出"))
    check("reported rows carry numeric values",
          all(_parse_number(r[2]) is not None and _parse_number(r[3]) is not None
              for r in data_rows if r[1] == "报出"))
    envelope = json.loads(json_path.read_text(encoding="utf-8"))
    check("envelope has 32 elements", len(envelope["elements"]) == 32,
          f"{len(envelope['elements'])}")
    threshold = envelope["elements"][0]["threshold"]
    check("reported flag follows the threshold rule for every element",
          all(((e["classification_probability"] is not None
                and e["classification_probability"] >= threshold and e["mass_percent"] > 0)
               == e["reported"]) for e in envelope["elements"]))
    check("ppm equals percent*10000",
          all(abs(e["mass_percent_ppm"] - e["mass_percent"] * 10000) <= 1e-9
              for e in envelope["elements"]))
    check("comparison carried into report",
          envelope.get("comparison", {}).get("v9_job_id") == v9_job_id)
    print()

    print("--- get_job_status unknown id must not enumerate")
    obj, rc, _ = run(["status", "--job-id", "does-not-exist-0000"])
    check("unknown job reported absent", obj.get("exists") is False, f"exists={obj.get('exists')}")
    check("clean exit", rc in (0, 1), f"rc={rc}")
    print()

    print("--- scratch and temp cleanup")
    leftovers = [str(p) for p in sorted(ROOT.glob("**/.tmp-*")) if p.is_dir()]
    check("no leftover .tmp-* scratch dirs", not leftovers, leftovers)
    xtmp = [str(p) for p in sorted((ROOT / "deliverables" / "xrf-models-v9-v10-20261030")
                                   .glob("**/.xrf-job-*"))]
    check("model wrapper cleaned its tmp dirs", not xtmp, xtmp)
    print()

    print("=" * 70)
    if failures:
        print(f"{len(failures)} FAILED:")
        for name, detail in failures:
            print(f"  - {name}: {detail}")
        return 1
    print("ALL CASES PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())