"""Strict five-field input contract. Nothing here guesses or repairs a user file."""
from __future__ import annotations
import json, math, pathlib
from .paths import write_json, sha256_hex

REQUIRED_KEYS = ("axis", "signal_unit", "synthetic", "x", "counts")
N_CHANNELS = 2048
# Counts are accepted as plain integers and handed to the model unchanged. Anything wider
# than an exact float risks overflowing the C math used downstream (math.isinf on 10**400
# raises OverflowError), so this is a hard structural limit, not a quality gate.
MAX_COUNT = 2**53 - 1
BANNED_EXTRA_KEYS = ("truth", "ground_truth", "reference", "seed", "instrument", "measurement_time",
                     "live_time", "distance", "container", "energy_calibration", "smoothed",
                     "background_subtracted", "normalized")


class ContractError(Exception):
    def __init__(self, code: str, message: str, detail: dict | None = None, *,
                 reason_code: str | None = None, user_message: str | None = None,
                 expected=None, actual=None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.detail = detail or {}
        # F03: the machine code and the English debug text stay as they were; a rejection
        # also carries a stable reason_code + Chinese user_message with expected/actual so a
        # user who only reads the answer line still learns what was wrong and why.
        self.reason_code = reason_code
        self.user_message = user_message
        self.expected = expected
        self.actual = actual


# Chinese user-facing messages, keyed by a stable reason_code so callers can be routed
# without parsing text. The debug English strings stay in ContractError.message; these
# templates only restate the same fact for a human reader.
REASON_USER_MESSAGES = {
    "NOT_JSON": "无法分析：输入文件不是有效的 JSON。请核对原始导出文件，本程序不会自动修复格式。",
    "NOT_OBJECT": "无法分析：输入的 JSON 顶层必须是对象，且只含五个固定字段"
                  "（axis、signal_unit、synthetic、x、counts）。",
    "MISSING_FIELDS": "无法分析：缺少必填字段{missing}。要求字段为 axis、signal_unit、synthetic、x、counts。",
    "EXTRA_FIELDS": "无法分析：输入只能含五个固定字段，多出的{extra}不被接受{banned}。",
    "BAD_AXIS": "无法分析：axis 必须为 'channel'，实际为 {actual}。",
    "BAD_SIGNAL_UNIT": "无法分析：signal_unit 必须为 'counts'，实际为 {actual}。",
    "BAD_SYNTHETIC": "无法分析：synthetic 必须为 true，实际为 {actual}。",
    "NOT_ARRAYS": "无法分析：'x' 和 'counts' 必须是数组。",
    "BAD_CHANNEL_COUNT": "无法分析：当前文件为 {actual} 道，要求 {expected} 道。"
                         "请核对原始导出文件，本程序不会自动插值或补道。",
    "BAD_X_LENGTH": "无法分析：x 需要 {expected} 个元素，实际为 {actual} 个。",
    "NON_INTEGER_COUNTS": "无法分析：counts 必须是非负整数（布尔值不被接受）。",
    "NEGATIVE_COUNTS": "无法分析：counts 不能含有负值。",
    "OVERSIZE_COUNTS": "无法分析：单个计数不能超过 {expected}，实际最大值为 {actual}。",
    "ZERO_TOTAL": "无法分析：总计数为 0，请提供总计数大于 0 的原始计数谱。",
    "NON_INTEGER_X": "无法分析：x 的元素必须是整数。",
    "BAD_X_SPAN": "无法分析：x 必须覆盖 0 到 {expected}，实际为 {actual}。",
    "BAD_X_SEQUENCE": "无法分析：x 必须是连续的通道序号 0..2047。",
}


def _cn(reason_code: str, **values) -> str:
    template = REASON_USER_MESSAGES.get(reason_code)
    if template is None:
        return "无法分析：输入不符合本程序的数据契约。"
    try:
        return template.format(**values)
    except (KeyError, IndexError):
        return template


def _reject(code: str, reason_code: str, debug: str, detail: dict | None = None,
            **cn_values) -> ContractError:
    """One rejection mechanism for every contract failure: machine code, English debug text
    and detail stay unchanged, and a Chinese user_message joins them."""
    return ContractError(
        code, debug, detail,
        reason_code=reason_code,
        user_message=_cn(reason_code, **cn_values),
        expected=cn_values.get("expected"),
        actual=cn_values.get("actual"))



def _is_int_like(v) -> bool:
    return isinstance(v, int) and not isinstance(v, bool)


def _is_valid_count(v) -> bool:
    """A count the contract will forward: a bounded finite integer, never a float or NaN."""
    return isinstance(v, int) and not isinstance(v, bool) and abs(v) <= MAX_COUNT and math.isfinite(v)


def validate(task_file: pathlib.Path) -> dict:
    """Validate the task file against the five-field contract. Returns the parsed record."""
    try:
        with task_file.open(encoding="utf-8-sig") as f:
            raw = json.load(f)
    except json.JSONDecodeError as exc:
        raise _reject("UNSUPPORTED_FORMAT", "NOT_JSON", f"Input is not valid JSON: {exc}")
    except (OSError, UnicodeDecodeError) as exc:
        raise _reject("UNSUPPORTED_FORMAT", "NOT_JSON", f"Input cannot be read: {exc}")

    if not isinstance(raw, dict):
        raise _reject("UNSUPPORTED_FORMAT", "NOT_OBJECT",
                      f"Top-level input must be a JSON object, got {type(raw).__name__}")

    missing = [k for k in REQUIRED_KEYS if k not in raw]
    if missing:
        raise _reject("INVALID_COUNTS", "MISSING_FIELDS",
                      f"Missing required field(s): {', '.join(missing)}",
                      {"missing": missing},
                      missing="、".join(missing))

    extra = [k for k in raw if k not in REQUIRED_KEYS]
    if extra:
        banned = [k for k in extra if k in BANNED_EXTRA_KEYS]
        raise _reject(
            "INVALID_COUNTS", "EXTRA_FIELDS",
            f"Input must contain exactly the five fields {list(REQUIRED_KEYS)}; "
            f"found extra field(s): {', '.join(extra)}."
            + (f" Banned fields (not forwarded to the model): {', '.join(banned)}"
               if banned else ""),
            {"extra": extra, "banned": banned},
            extra="、".join(extra),
            banned=("（其中包含禁止字段，不会被转发给模型）" if banned else ""))

    if raw["axis"] != "channel":
        raise _reject("INVALID_COUNTS", "BAD_AXIS",
                      f"axis must be 'channel', got {raw['axis']!r}",
                      actual=repr(raw["axis"]))
    if raw["signal_unit"] != "counts":
        raise _reject("INVALID_COUNTS", "BAD_SIGNAL_UNIT",
                      f"signal_unit must be 'counts', got {raw['signal_unit']!r}",
                      actual=repr(raw["signal_unit"]))
    if raw["synthetic"] is not True:
        raise _reject("INVALID_COUNTS", "BAD_SYNTHETIC",
                      f"synthetic must be true, got {raw['synthetic']!r}",
                      actual=repr(raw["synthetic"]))

    x = raw["x"]
    counts = raw["counts"]

    if not isinstance(x, list) or not isinstance(counts, list):
        raise _reject("INVALID_COUNTS", "NOT_ARRAYS", "'x' and 'counts' must be arrays")
    if len(counts) != N_CHANNELS:
        raise _reject("INVALID_COUNTS", "BAD_CHANNEL_COUNT",
                      f"counts must have {N_CHANNELS} channels, got {len(counts)}",
                      expected=N_CHANNELS, actual=len(counts))
    if len(x) != N_CHANNELS:
        raise _reject("INVALID_COUNTS", "BAD_X_LENGTH",
                      f"x must have {N_CHANNELS} entries, got {len(x)}",
                      expected=N_CHANNELS, actual=len(x))

    if not all(_is_int_like(c) for c in counts):
        bad = [i for i, c in enumerate(counts) if not _is_int_like(c)]
        raise _reject("INVALID_COUNTS", "NON_INTEGER_COUNTS",
                      "counts must be non-negative integers (booleans are not accepted)",
                      {"non_integer_indices": bad[:10], "n_non_integer": len(bad)})
    if any(c < 0 for c in counts):
        bad = [i for i, c in enumerate(counts) if c < 0]
        raise _reject("INVALID_COUNTS", "NEGATIVE_COUNTS", "counts must be non-negative",
                      {"negative_indices": bad[:10], "n_negative": len(bad)})
    if any(not _is_valid_count(c) for c in counts):
        bad = [i for i, c in enumerate(counts) if not _is_valid_count(c)]
        raise _reject("INVALID_COUNTS", "OVERSIZE_COUNTS",
                      f"counts must be finite integers not larger than {MAX_COUNT} in magnitude",
                      {"max_count": MAX_COUNT, "bad_indices": bad[:10], "n_bad": len(bad)},
                      expected=MAX_COUNT, actual=max(counts))
    total = sum(counts)
    if total <= 0:
        raise _reject("INVALID_COUNTS", "ZERO_TOTAL", "counts must sum to a positive value")

    if not all(_is_int_like(i) for i in x):
        bad = [i for i, v in enumerate(x) if not _is_int_like(v)]
        raise _reject("INVALID_COUNTS", "NON_INTEGER_X", "x entries must be integers",
                      {"bad_indices": bad[:10]})
    if min(x) != 0 or max(x) != N_CHANNELS - 1:
        raise _reject("INVALID_COUNTS", "BAD_X_SPAN",
                      f"x must span 0..{N_CHANNELS - 1}, got {min(x)}..{max(x)}",
                      expected=f"0..{N_CHANNELS - 1}", actual=f"{min(x)}..{max(x)}")
    if list(x) != list(range(N_CHANNELS)):
        raise _reject("INVALID_COUNTS", "BAD_X_SEQUENCE",
                      "x must be the consecutive channel indices 0..2047")

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