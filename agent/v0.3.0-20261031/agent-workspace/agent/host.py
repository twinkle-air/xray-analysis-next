"""Compliant LLM host abstraction.

The host is only allowed to pick which documented tool to call next and to explain the
evidence the tools return. It cannot change the model version, rewrite the input contract
or invent a spectrum.

Two backends are supported:
  * api        -- an OpenAI-compatible /v1/chat/completions endpoint, configured through
                  XRF_AGENT_LLM_*.
  * local_simulation -- a deterministic local fallback used only when no compliant host is
                  configured. Every trajectory produced by it carries simulated=true and is
                  never presented as a real model call.
"""
from __future__ import annotations

import dataclasses
import json
import os
import pathlib
import urllib.error
import urllib.request
from typing import Optional

from .core.paths import read_json

TOOL_CONTRACTS = "registry/tool_contracts.json"


class HostError(Exception):
    """The host itself is unavailable or misconfigured, not a tool failure."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


@dataclasses.dataclass
class ToolCall:
    id: str
    name: str
    arguments: dict


@dataclasses.dataclass
class ToolResult:
    tool_call_id: str
    name: str
    content: str
    arguments: dict = dataclasses.field(default_factory=dict)


@dataclasses.dataclass
class HostResult:
    text: str
    tool_calls: list[ToolCall]
    finish_reason: Optional[str]
    usage: Optional[dict]
    host_label: str
    simulated: bool


@dataclasses.dataclass
class HostConfig:
    host: str
    api_base: Optional[str]
    api_key: Optional[str]
    model: Optional[str]
    max_tokens: int
    timeout: float
    temperature: Optional[float]
    simulated: bool


def detect_config(explicit_host: Optional[str] = None) -> HostConfig:
    """Read the host configuration from the environment. Raises HostError if an API host is
    asked for but not configured."""
    host = explicit_host or os.environ.get("XRF_AGENT_LLM_HOST", "local_simulation")
    if host not in ("api", "local_simulation"):
        raise HostError("UNSUPPORTED_HOST", f"unsupported XRF_AGENT_LLM_HOST={host!r}; use api or local_simulation")

    api_base = os.environ.get("XRF_AGENT_LLM_API_BASE") or os.environ.get("XRF_AGENT_LLM_API_URL")
    api_key = os.environ.get("XRF_AGENT_LLM_API_KEY") or os.environ.get("XRF_AGENT_LLM_KEY")
    model = os.environ.get("XRF_AGENT_LLM_MODEL")

    if host == "api":
        if not api_base:
            raise HostError("MISSING_HOST_CONFIG", "XRF_AGENT_LLM_API_BASE is required for an API host")
        if not api_key:
            raise HostError("MISSING_HOST_CONFIG", "XRF_AGENT_LLM_API_KEY is required for an API host")
        if not model:
            raise HostError("MISSING_HOST_CONFIG", "XRF_AGENT_LLM_MODEL is required for an API host")

    return HostConfig(
        host=host,
        api_base=api_base.rstrip("/") if api_base else None,
        api_key=api_key,
        model=model,
        max_tokens=int(os.environ.get("XRF_AGENT_LLM_MAX_TOKENS", "2048")),
        timeout=float(os.environ.get("XRF_AGENT_LLM_TIMEOUT", "120")),
        temperature=_maybe_float("XRF_AGENT_LLM_TEMPERATURE"),
        simulated=host != "api",
    )


def _maybe_float(name: str) -> Optional[float]:
    raw = os.environ.get(name)
    if raw is None:
        return None
    try:
        return float(raw)
    except ValueError:
        return None


def _tool_schemas(workspace_root: pathlib.Path) -> list[dict]:
    contracts = read_json(workspace_root / TOOL_CONTRACTS)
    out = []
    for name, spec in contracts.get("tools", {}).items():
        out.append({
            "name": name,
            "description": spec.get("description", ""),
            "parameters": spec.get("parameters", {"type": "object", "properties": {}}),
        })
    return out


# ------------------------------------------------------------------ API backend


def _post_json(url: str, payload: dict, api_key: str, timeout: float) -> dict:
    request = urllib.request.Request(
        url,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        },
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        body = response.read().decode("utf-8", errors="replace")
    try:
        return json.loads(body)
    except json.JSONDecodeError as exc:
        raise HostError("HOST_UNREADABLE", f"host returned non-JSON: {exc}") from exc


def _parse_tool_calls(message: dict) -> list[ToolCall]:
    calls = []
    for raw in message.get("tool_calls") or []:
        function = raw.get("function") or {}
        try:
            arguments = json.loads(function.get("arguments") or "{}")
        except json.JSONDecodeError:
            arguments = {}
        calls.append(ToolCall(id=raw.get("id") or "", name=function.get("name", ""), arguments=arguments))
    legacy = message.get("function_call")
    if isinstance(legacy, dict) and legacy.get("name"):
        try:
            arguments = json.loads(legacy.get("arguments") or "{}")
        except json.JSONDecodeError:
            arguments = {}
        calls.append(ToolCall(id="function-call-1", name=legacy["name"], arguments=arguments))
    return calls


def api_chat(messages: list[dict], functions: list[dict], config: HostConfig) -> HostResult:
    if config.api_base is None:
        raise HostError("MISSING_HOST_CONFIG", "no api_base configured")
    payload = {
        "model": config.model,
        "messages": messages,
        "max_tokens": config.max_tokens,
    }
    if functions:
        # The function spec itself is unchanged; only the envelope differs. The InternLM
        # endpoint silently ignores the legacy `functions` field (verified against
        # Atria-Dawn: no call is made and the model answers in prose), so the modern
        # `tools` wrapper is what gets sent.
        payload["tools"] = [{"type": "function", "function": f} for f in functions]
        payload["tool_choice"] = "auto"
    if config.temperature is not None:
        payload["temperature"] = config.temperature

    try:
        data = _post_json(f"{config.api_base}/v1/chat/completions", payload, config.api_key, config.timeout)
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")[:600]
        raise HostError("HOST_HTTP_ERROR", f"host HTTP {exc.code}: {body}") from exc
    except urllib.error.URLError as exc:
        raise HostError("HOST_UNREACHABLE", f"cannot reach {config.api_base}: {exc}") from exc

    choices = data.get("choices") or []
    message = (choices[0].get("message") if choices else {}) or {}
    return HostResult(
        text=message.get("content", ""),
        tool_calls=_parse_tool_calls(message),
        finish_reason=(choices[0].get("finish_reason") if choices else None),
        usage=data.get("usage"),
        host_label=f"{config.model} at {config.api_base}",
        simulated=False,
    )


# ------------------------------------------------------------------ local simulation backend


def _spectrum_path_in(messages: list[dict]) -> Optional[str]:
    """Return an existing spectrum path mentioned in a user message, if any.

    The simulator never invents a file name; if the user did not name one, there is nothing
    to analyze.
    """
    for message in messages:
        if message.get("role") != "user":
            continue
        text = message.get("content", "")
        for token in str(text).split():
            candidate = token.strip(".,;:;'\"()")
            if candidate.endswith(".json") and pathlib.Path(candidate).is_file():
                return candidate
    return None


# The orchestrator forwards tool results back to the host as user-role messages so the host
# sees what happened. They are not user input, and scanning them for intent would make every
# completed turn look like a request for whatever tool just ran.
FORWARDED_PREFIXES = ("报告导出返回。", "V9 对照返回。", "收到请求，但没有找到可分析的谱文件。")


def _real_user_text(messages: list[dict]) -> str:
    """The user's own words, excluding forwarded tool results."""
    return "\n".join(
        str(message.get("content", "")) for message in messages
        if message.get("role") == "user"
        and not str(message.get("content", "")).lstrip().startswith(FORWARDED_PREFIXES))


def _last_user_text(messages: list[dict]) -> str:
    """The current user question only.

    Intent is decided from what was just asked, not from the words the user used several
    turns ago. Scanning the whole history would make a request for a comparison keep
    exporting, and a request for an export keep comparing, forever.
    """
    for message in reversed(messages):
        if message.get("role") != "user":
            continue
        text = str(message.get("content", ""))
        if text.lstrip().startswith(FORWARDED_PREFIXES):
            continue
        return text
    return ""


def _user_wants_comparison(text: str) -> bool:
    return any(word in text for word in ("对照", "compare", "V9", "差异复核"))


def _wants_comparison(messages: list[dict]) -> bool:
    return _user_wants_comparison(_last_user_text(messages))


def _wants_export(messages: list[dict]) -> bool:
    return any(word in _last_user_text(messages) for word in ("导出", "报告", "export report", "出报告"))


def _compare_completed(messages: list[dict]) -> bool:
    """A comparison has run *after* the most recent explicit request for one.

    A comparison that ran earlier (for example automatically by a review rule, or on an
    earlier turn) must not satisfy a request that arrived later, otherwise the agent would
    export the moment the user asks for a comparison.
    """
    last_request = -1
    for i, message in enumerate(messages):
        if message.get("role") != "user":
            continue
        text = str(message.get("content", ""))
        if text.lstrip().startswith(FORWARDED_PREFIXES):
            continue
        if _user_wants_comparison(text):
            last_request = i
    for i, message in enumerate(messages):
        if message.get("role") != "tool" or i <= last_request:
            continue
        try:
            result = json.loads(message.get("content", "{}"))
        except json.JSONDecodeError:
            continue
        if result.get("name") == "compare_models" and result.get("body", {}).get("error_code") is None:
            return True
    return False


def _analysis_succeeded(messages: list[dict]) -> bool:
    for message in messages:
        if message.get("role") != "tool":
            continue
        try:
            result = json.loads(message.get("content", "{}"))
        except json.JSONDecodeError:
            continue
        return result.get("body", {}).get("status") == "succeeded"
    return False


def _analysis_done(messages: list[dict]) -> bool:
    """A documented tool has already been executed in this conversation."""
    for message in messages:
        if message.get("role") != "tool":
            continue
        try:
            result = json.loads(message.get("content", "{}"))
        except json.JSONDecodeError:
            continue
        if isinstance(result, dict) and result.get("name"):
            return True
    return False


def local_simulation_chat(messages: list[dict], functions: list[dict]) -> HostResult:
    """Deterministic fallback that only selects a documented tool.

    It does not read the spectrum, does not run the model and never writes content. It is a
    wiring stand-in: every trajectory using it records simulated=true. Once a tool has run,
    further questions are answered only with an explicit request for the next tool.
    """
    if _compare_completed(messages):
        calls = [ToolCall(id="call-export", name="export_report", arguments={"job_id": "_pending_", "include_comparison": True})]
    elif _wants_export(messages) and _analysis_succeeded(messages):
        calls = [ToolCall(id="call-export", name="export_report", arguments={"job_id": "_pending_", "include_comparison": False})]
    elif _wants_comparison(messages) and _analysis_succeeded(messages):
        calls = [ToolCall(id="call-compare", name="compare_models", arguments={"job_id": "_pending_"})]
    elif _spectrum_path_in(messages) and not _analysis_done(messages):
        text = "\n".join(str(m.get("content", "")) for m in messages if m.get("role") == "user")
        calls = [ToolCall(
            id="call-analyze",
            name="analyze_spectrum",
            arguments={
                "task_file": _spectrum_path_in(messages),
                "sample_description": text,
            },
        )]
    else:
        return HostResult(
            text="收到请求，但没有找到可分析的谱文件。请上传一个五字段 JSON 能谱（axis、signal_unit、synthetic、x、counts），或提供一个已存在的文件路径。",
            tool_calls=[],
            finish_reason="stop",
            usage=None,
            host_label="local_simulation",
            simulated=True,
        )

    return HostResult(
        text="已选择下一步工具。工具的实际返回值由数值程序决定，不由本宿主生成。",
        tool_calls=calls,
        finish_reason="tool_calls",
        usage=None,
        host_label="local_simulation",
        simulated=True,
    )


# ------------------------------------------------------------------ public entry


def chat(
    workspace_root: pathlib.Path,
    messages: list[dict],
    config: HostConfig,
) -> HostResult:
    """Run one host turn. `messages` must be a valid OpenAI-style message list."""
    functions = _tool_schemas(workspace_root)
    if config.host == "api":
        return api_chat(messages, functions, config)
    return local_simulation_chat(messages, functions)


def config_summary(config: HostConfig) -> dict:
    """Safe, credential-free summary of the active host configuration."""
    return {
        "host": config.host,
        "api_base": config.api_base if not config.simulated else None,
        "model": config.model if not config.simulated else None,
        "max_tokens": config.max_tokens,
        "timeout_s": config.timeout,
        "temperature": config.temperature,
        "simulated": config.simulated,
        "note": (
            "No compliant LLM host is configured. The trajectory below is a deterministic local "
            "stand-in that only records which tool would be called; it is not a real model call."
            if config.simulated else "Compliant LLM host in use."
        ),
    }