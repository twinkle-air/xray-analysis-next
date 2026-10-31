"""Strict five-field input contract. Nothing here guesses or repairs a user file."""
from __future__ import annotations
import json, math, pathlib
from .paths import write_json, sha256_hex

REQUIRED_KEYS = ("axis", "signal_unit", "synthetic", "x", "counts")
N_CHANNELS = 2048
BANNED_EXTRA_KEYS = ("truth", "ground_truth", "reference", "seed", "instrument", "measurement_time",
                     "live_time", "distance", "container", "energy_calibration", "smoothed",
                     "background_subtracted", "normalized")


class ContractError(Exception):
    def __init__(self, code: str, message: str, detail: dict | None = None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.detail = detail or {}


def _is_int_like(v) -> bool:
    return isinstance(v, int) and not isinstance(v, bool)


def validate(task_file: pathlib.Path) -> dict:
    """Validate the task file against the five-field contract. Returns the parsed record."""
    try:
        with task_file.open(encoding="utf-8-sig") as f:
            raw = json.load(f)
    except json.JSONDecodeError as exc:
        raise ContractError("UNSUPPORTED_FORMAT", f"Input is not valid JSON: {exc}")
    except (OSError, UnicodeDecodeError) as exc:
        raise ContractError("UNSUPPORTED_FORMAT", f"Input cannot be read: {exc}")

    if not isinstance(raw, dict):
        raise ContractError("UNSUPPORTED_FORMAT", "Top-level input must be a JSON object")

    missing = [k for k in REQUIRED_KEYS if k not in raw]
    if missing:
        raise ContractError("INVALID_COUNTS", f"Missing required field(s): {', '.join(missing)}",
                            {"missing": missing})

    extra = [k for k in raw if k not in REQUIRED_KEYS]
    if extra:
        banned = [k for k in extra if k in BANNED_EXTRA_KEYS]
        raise ContractError("INVALID_COUNTS",
                            f"Input must contain exactly the five fields {list(REQUIRED_KEYS)}; "
                            f"found extra field(s): {', '.join(extra)}."
                            + (f" Banned fields (not forwarded to the model): {', '.join(banned)}"
                               if banned else ""),
                            {"extra": extra, "banned": banned})

    if raw["axis"] != "channel":
        raise ContractError("INVALID_COUNTS", f"axis must be 'channel', got {raw['axis']!r}")
    if raw["signal_unit"] != "counts":
        raise ContractError("INVALID_COUNTS", f"signal_unit must be 'counts', got {raw['signal_unit']!r}")
    if raw["synthetic"] is not True:
        raise ContractError("INVALID_COUNTS", f"synthetic must be true, got {raw['synthetic']!r}")

    x = raw["x"]
    counts = raw["counts"]

    if not isinstance(x, list) or not isinstance(counts, list):
        raise ContractError("INVALID_COUNTS", "'x' and 'counts' must be arrays")
    if len(counts) != N_CHANNELS:
        raise ContractError("INVALID_COUNTS", f"counts must have {N_CHANNELS} channels, got {len(counts)}")
    if len(x) != N_CHANNELS:
        raise ContractError("INVALID_COUNTS", f"x must have {N_CHANNELS} entries, got {len(x)}")

    if not all(_is_int_like(c) for c in counts):
        bad = [i for i, c in enumerate(counts) if not _is_int_like(c)]
        raise ContractError("INVALID_COUNTS", "counts must be non-negative integers (booleans are not accepted)",
                            {"non_integer_indices": bad[:10], "n_non_integer": len(bad)})
    if any(c < 0 for c in counts):
        bad = [i for i, c in enumerate(counts) if c < 0]
        raise ContractError("INVALID_COUNTS", "counts must be non-negative",
                            {"negative_indices": bad[:10], "n_negative": len(bad)})
    if any(c != c or math.isinf(c) for c in counts):  # counts are ints, keep the guard explicit
        raise ContractError("INVALID_COUNTS", "counts must be finite")
    total = sum(counts)
    if total <= 0:
        raise ContractError("INVALID_COUNTS", "counts must sum to a positive value")

    if not all(_is_int_like(i) for i in x):
        bad = [i for i, v in enumerate(x) if not _is_int_like(v)]
        raise ContractError("INVALID_COUNTS", "x entries must be integers",
                            {"bad_indices": bad[:10]})
    if min(x) != 0 or max(x) != N_CHANNELS - 1:
        raise ContractError("INVALID_COUNTS", f"x must span 0..{N_CHANNELS - 1}, got {min(x)}..{max(x)}")
    if list(x) != list(range(N_CHANNELS)):
        raise ContractError("INVALID_COUNTS", "x must be the consecutive channel indices 0..2047")

    return {"axis": "channel", "signal_unit": "counts", "synthetic": True,
            "x": list(range(N_CHANNELS)), "counts": [int(c) for c in counts],
            "n_channels": N_CHANNELS, "total_counts": total,
            "min_count": min(counts), "max_count": max(counts),
            "source_file": str(task_file)}


def parse_and_save(task_file: pathlib.Path, out_parsed: pathlib.Path, original_notes: str = "") -> dict:
    """Validate, copy the immutable original alongside, and write the parsed result."""
    record = validate(task_file)
    record["original_notes"] = original_notes
    record["input_sha256"] = sha256_hex(task_file)
    write_json(out_parsed, record)
    return record


def describe(record: dict) -> str:
    return (f"{record['n_channels']} channels, axis={record['axis']}, "
            f"total_counts={record['total_counts']}, "
            f"min={record['min_count']}, max={record['max_count']}")