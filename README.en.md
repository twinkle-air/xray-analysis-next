English | [简体中文](README.md)

# General-Purpose X-Ray Spectrum Analysis Agent V1.0

An evidence-driven analysis agent for 2048-channel synthetic X-ray energy spectra: given one spectrum plus a sample description, the V10 primary model produces candidate elements and mass percentages, a V9 comparison is triggered according to registered rules, and the pipeline finally outputs a Markdown research draft and a structured evidence package. Only four registered tools may be called throughout the entire workflow, and the artifacts of every step are persisted to disk for traceability.

## Current Version

Public name: **V1.0**; machine version: `1.0.0`. This release applies unified naming to the existing finished version and carries forward the improvements already merged from the former v0.4.0; the V10/V9 numerical models, the report component `1.1.0`, and the report schema `1.0` are each retained.

The current source entry point is `agent/` at the repository root, and the release snapshot is `.publish/agent/v1.0-20261107/`. The older `.publish/agent/v0.3.1-20261106/` and legacy logs are kept as historical identifiers and are not the current release entry point. After extracting the complete companion package, run commands from the root directory of `XRF作品提交包`, keeping its frozen models and examples under `deliverables/`.

## Repository Layout

| Path | Contents |
|---|---|
| `agent/` | Runnable code: four-tool entry points, orchestration and host, and the registry (`agent/registry/`) |
| `agent-workspace/` | P0 baseline measurement results and debugging probe scripts |
| `verify_p1.py` / `verify_p2.py` / `verify_p3.py` | Automated verification suites |
| `jobs/` | Per-job artifacts: input, parsing, inference, comparison, audit trail, and report |
| `智能体构建情况与使用指南.md` | Build status, tool contracts, verification results, and known limitations |

## Quick Start

Dependencies: Python ≥ 3.12.14, numpy 2.4.6, scipy 1.17.1, xraylib 4.3.0 (see the guide §1 and §5).

```bash
python -m agent.cli agent \
  --task-file deliverables/智能体功能测试谱集-20261031/01_正常输入/T01.json \
  --sample-description "合金合成计数谱，原始计数"
```

Before each analysis, the agent first verifies whether **the interpreter of the subprocess that actually runs the model** (not the parent process) satisfies the version policy declared in `agent/registry/runtime_policy.json`, and writes the fingerprint into the job status, the JSON, and the report. If the environment does not match, the run is rejected with `RUNTIME_MISMATCH` (no silent fallback); missing dependencies are rejected with `DEPENDENCY_MISSING`. When a temporary override is needed, the only entry point is `--allow-unverified-runtime` (the result is truthfully marked as unverified). Old results are not reused across environments: the deduplication key is bound to the runtime-environment fingerprint.

The four tools can also be driven individually: `analyze_spectrum`, `get_job_status`, `compare_models`, and `export_report`; for their parameters and return values, see `agent/registry/tool_contracts.json` and the guide §3.

For multi-turn follow-ups, use `--interactive`: the session records the current spectrum, the primary job, and the comparison job (`audit/session.json`); follow-ups read the existing results directly without re-running inference, and each turn in the trail is tagged with `answer_source` (`model` / `program_fallback`). For a real host, use `--host-mode api` together with the `XRF_AGENT_LLM_*` environment variables; the verifiable model identifier in the requests/responses is `Sage-A1.5`.

## Boundaries

- `formal_report_eligible=false`, `hardware_validated=false`: the report is a research draft and does not constitute a quantitative acceptance conclusion; neither model version meets the relative-error ≤5% target.
- V9 is not ground truth; even when the two versions agree they may share the same bias, so no averaging or per-element cherry-picking is done. The comparison strategy is documented centrally in Section 7 of the report, with rules taken from `agent/registry/comparison_policy.json`.
- Only 2048-channel counting JSON with `synthetic: true` is accepted; rejection reasons are provided in a Chinese `user_message` (machine codes and English debug information are retained), and onboarding measured spectra requires separate acceptance.
- For remaining limitations, see [智能体构建情况与使用指南.md](智能体构建情况与使用指南.md) §8.