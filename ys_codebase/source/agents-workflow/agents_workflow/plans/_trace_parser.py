"""
agents_workflow.plans._trace_parser — 多宿主 .jsonl 對話紀錄串流解析與 Token 效益分析引擎。
"""

import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional, Set, Tuple, Union

from ._trace_renderer import FrictionSignal

MAX_JSONL_LINE_BYTES: int = 2 * 1024 * 1024

EDIT_TOOL_NAMES: Set[str] = {
    "edit_file", "write_file", "edit", "write", "multiedit", "replace",
    "replace_file_content", "multi_replace_file_content",
}
READ_TOOL_NAMES: Set[str] = {
    "read_file", "view_file", "read", "view", "view_file_outline",
}
GATE_COMMANDS: Set[Tuple[str, str]] = {
    ("agents-workflow", "plan verify"),
    ("agents-workflow", "compile"),
    ("dev", "check"),
    ("dev", "test"),
    ("core", "contributes check"),
}
SOURCE_EXTENSIONS = (
    ".py", ".ts", ".tsx", ".js", ".jsx", ".cs", ".java", ".kt", ".c", ".cpp", ".h", ".hpp", ".rs", ".go"
)
MEDIA_EXTENSIONS = (
    ".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".svg", ".mp4", ".pdf"
)


def _parse_ts(ts_str: str) -> Optional[float]:
    """解析 ISO-8601 或 YYYY-MM-DD HH:MM(:SS) 時間字串為 epoch 秒數。"""
    if not ts_str:
        return None
    s = ts_str.strip()
    try:
        if s.endswith("Z"):
            s = s[:-1] + "+00:00"
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.timestamp()
    except Exception:
        pass
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M"):
        try:
            dt = datetime.strptime(s, fmt)
            return dt.timestamp()
        except Exception:
            continue
    return None


def _estimate_tokens(text: str) -> int:
    """估算混合文本 Token 數（ASCII 約每 4 字元 1 Token，CJK/非 ASCII 約每字元 0.65 Token）。"""
    if not text:
        return 0
    total = len(text)
    ascii_cnt = len(text.encode("ascii", errors="ignore"))
    non_ascii_cnt = total - ascii_cnt
    return max(1, int(round(ascii_cnt / 4.0 + non_ascii_cnt * 0.65)))


@dataclass
class _TranscriptParseState:
    """串流解析 .jsonl 過程之累積狀態容器。"""
    first_ts: Optional[str] = None
    last_ts: Optional[str] = None
    topic: str = ""
    signals: List[FrictionSignal] = field(default_factory=list)
    thinking_excerpts: List[Dict[str, Any]] = field(default_factory=list)

    edit_history: Dict[str, List[int]] = field(default_factory=dict)
    read_counts: Dict[str, int] = field(default_factory=dict)
    unique_read_files: Set[str] = field(default_factory=set)
    consecutive_source_reads: int = 0
    max_consecutive_reads: int = 0
    consecutive_read_files: List[str] = field(default_factory=list)
    last_thinking: str = ""

    total_steps: int = 0
    user_turns: int = 0
    model_turns: int = 0
    thinking_steps: int = 0
    truncated_steps: int = 0
    error_steps: int = 0
    total_tool_calls: int = 0
    total_read_ops: int = 0
    total_edit_ops: int = 0
    subagent_calls: int = 0
    tool_dist: Dict[str, int] = field(default_factory=dict)

    tok_user: int = 0
    tok_model: int = 0
    tok_thinking: int = 0
    tok_tool_args: int = 0
    tok_tool_out: int = 0
    api_in_tokens: int = 0
    api_out_tokens: int = 0
    api_cache_read: int = 0
    api_cache_create: int = 0

    last_step_read_keys: List[str] = field(default_factory=list)
    last_step_gate_cmds: List[str] = field(default_factory=list)
    transcript_cli_calls: int = 0
    transcript_cli_failed: int = 0
    transcript_cli_by_module: Dict[str, int] = field(default_factory=dict)
    transcript_gate_bounces: List[FrictionSignal] = field(default_factory=list)

    wasted_dup_reads: int = 0
    wasted_failed_ops: int = 0
    wasted_edit_churn: int = 0
    wasted_blind_reads: int = 0
    has_recent_kdb_query: bool = False
    file_edit_step_tokens: Dict[str, List[Tuple[int, int]]] = field(default_factory=dict)
    tool_token_stats: Dict[str, Dict[str, int]] = field(default_factory=dict)
    heavy_steps_raw: List[Dict[str, Any]] = field(default_factory=list)
    heavy_cli_raw: List[Dict[str, Any]] = field(default_factory=list)
    pending_tool_context: Optional[Dict[str, Any]] = None
    last_planner_thinking_tok: int = 0
    last_planner_args_tok: int = 0


@dataclass
class _StepParseContext:
    """單步 JSONL 紀錄解析上下文容器。"""
    step_no: int
    obj: Dict[str, Any]
    payload_obj: Dict[str, Any]
    payload_type: str
    was_truncated: bool
    is_step_error: bool = False
    content_str: str = ""
    content_tok: int = 0
    is_tool_output_step: bool = False
    tool_result_errors: List[str] = field(default_factory=list)
    step_thinking_tok: int = 0
    tool_calls: List[Dict[str, Any]] = field(default_factory=list)
    current_step_read_keys: List[str] = field(default_factory=list)
    current_step_gate_cmds: List[str] = field(default_factory=list)
    step_total_args_tok: int = 0


def _append_thinking_excerpt_once(
    state: _TranscriptParseState,
    step_no: int,
    context: str = "TOOL_ERROR",
) -> None:
    """依 step_no 去重追加思考鏈摘要，避免單步多重錯誤重複塞爆配額。"""
    if not state.last_thinking or len(state.thinking_excerpts) >= 5:
        return
    if any(item.get("step") == step_no for item in state.thinking_excerpts):
        return
    state.thinking_excerpts.append({
        "step": step_no,
        "context": context,
        "excerpt": state.last_thinking,
    })


def _accumulate_api_usage(obj: Dict[str, Any], state: _TranscriptParseState) -> None:
    """累加原生 API usage Token 欄位（相容 Claude Code / Codex .jsonl 之 usage 物件與頂層欄位）。"""
    usage_obj = obj.get("usage")
    if not isinstance(usage_obj, dict) and isinstance(obj.get("message"), dict):
        usage_obj = obj["message"].get("usage")
    if not isinstance(usage_obj, dict) and isinstance(obj.get("payload"), dict):
        usage_obj = obj["payload"].get("usage")

    src = usage_obj if isinstance(usage_obj, dict) else obj
    state.api_in_tokens += int(src.get("input_tokens") or src.get("prompt_tokens") or 0)
    state.api_out_tokens += int(src.get("output_tokens") or src.get("completion_tokens") or 0)
    state.api_cache_read += int(src.get("cache_read_input_tokens") or src.get("cache_read_tokens") or 0)
    state.api_cache_create += int(src.get("cache_creation_input_tokens") or src.get("cache_creation_tokens") or 0)


def _extract_step_content_and_role(
    ctx_or_obj: Union[_StepParseContext, Dict[str, Any]],
    state_or_payload_obj: Union[_TranscriptParseState, Dict[str, Any]],
    payload_type: str = "",
    state: Optional[_TranscriptParseState] = None,
) -> Tuple[str, int, bool, List[str]]:
    """提取單步文本內容、估算 Token、歸類角色並提取行內 tool_result 錯誤。"""
    if isinstance(ctx_or_obj, _StepParseContext):
        ctx: Optional[_StepParseContext] = ctx_or_obj
        eff_state = state_or_payload_obj if isinstance(state_or_payload_obj, _TranscriptParseState) else state
        assert eff_state is not None
        obj = ctx.obj
        payload_obj = ctx.payload_obj
        eff_payload_type = ctx.payload_type
    else:
        ctx = None
        obj = ctx_or_obj
        payload_obj = state_or_payload_obj if isinstance(state_or_payload_obj, dict) else {}
        eff_payload_type = payload_type
        assert state is not None
        eff_state = state

    step_type = str(obj.get("type") or "").upper()
    step_source = str(obj.get("source") or "").upper()
    msg_role = str(
        obj.get("role")
        or (obj["message"].get("role") if isinstance(obj.get("message"), dict) else "")
        or payload_obj.get("role")
        or ""
    ).lower()

    content_val = obj.get("content") or payload_obj.get("content") or payload_obj.get("output")
    content_str = content_val if isinstance(content_val, str) else ""
    if not content_str and isinstance(content_val, list):
        c_parts = [
            str(blk.get("text") or blk.get("input_text") or blk.get("output_text") or "")
            for blk in content_val if isinstance(blk, dict)
        ]
        content_str = "\n".join(c_parts)

    tool_result_errors: List[str] = []
    step_inline_tool_out_tok = 0
    if not content_str and isinstance(obj.get("message"), dict):
        mc = obj["message"].get("content")
        if isinstance(mc, str):
            content_str = mc
        elif isinstance(mc, list):
            text_parts: List[str] = []
            for blk in mc:
                if not isinstance(blk, dict):
                    continue
                b_type = blk.get("type")
                if b_type in ("text", "input_text", "output_text"):
                    text_parts.append(str(blk.get("text") or blk.get("input_text") or blk.get("output_text") or ""))
                elif b_type == "tool_result":
                    tr_c = blk.get("content")
                    tr_str = json.dumps(tr_c, ensure_ascii=False) if isinstance(tr_c, (list, dict)) else str(tr_c or "")
                    tr_tok = _estimate_tokens(tr_str)
                    eff_state.tok_tool_out += tr_tok
                    step_inline_tool_out_tok += tr_tok
                    if blk.get("is_error") is True:
                        tool_result_errors.append(" ".join(tr_str.split())[:200])
            content_str = "\n".join(text_parts)

    content_tok = _estimate_tokens(content_str)
    is_tool_output_step = False
    if step_type == "GENERIC" or eff_payload_type in ("function_call_output", "custom_tool_call_output"):
        eff_state.tok_tool_out += content_tok
        is_tool_output_step = True
    elif step_type == "USER_INPUT" or step_source == "USER_EXPLICIT" or msg_role == "user":
        if step_inline_tool_out_tok > 0 and not content_str.strip():
            is_tool_output_step = True
            content_tok = step_inline_tool_out_tok
        else:
            eff_state.user_turns += 1
            eff_state.tok_user += content_tok
            if not eff_state.topic and content_str:
                raw_topic = content_str
                if "<USER_REQUEST>" in raw_topic:
                    raw_topic = raw_topic.split("<USER_REQUEST>", 1)[1].split("</USER_REQUEST>", 1)[0].strip()
                clean_topic = " ".join(raw_topic.split())
                if clean_topic and clean_topic.lower() not in ("/context-init", "context-init"):
                    eff_state.topic = clean_topic[:60]
    elif step_type == "PLANNER_RESPONSE" or step_source == "MODEL" or msg_role == "assistant":
        eff_state.model_turns += 1
        eff_state.tok_model += content_tok
    else:
        eff_state.tok_tool_out += content_tok
        is_tool_output_step = True

    if ctx is not None:
        ctx.content_str = content_str
        ctx.content_tok = content_tok
        ctx.is_tool_output_step = is_tool_output_step
        ctx.tool_result_errors = tool_result_errors

    return content_str, content_tok, is_tool_output_step, tool_result_errors


def _attribute_tool_output_tokens(
    ctx_or_step_no: Union[_StepParseContext, int],
    state_or_content_str: Union[_TranscriptParseState, str] = "",
    content_tok: int = 0,
    is_tool_output_step: bool = False,
    is_step_error: bool = False,
    was_truncated: bool = False,
    tool_result_errors: Optional[List[str]] = None,
    state: Optional[_TranscriptParseState] = None,
) -> None:
    """檢查上一步驗證關卡退件，並將工具輸出 Token 歸戶至前一步發起之工具與重度排行。"""
    if isinstance(ctx_or_step_no, _StepParseContext):
        ctx = ctx_or_step_no
        eff_state = state_or_content_str if isinstance(state_or_content_str, _TranscriptParseState) else state
        assert eff_state is not None
        step_no = ctx.step_no
        content_str = ctx.content_str
        eff_content_tok = ctx.content_tok
        eff_is_tool_output = ctx.is_tool_output_step
        eff_is_step_error = ctx.is_step_error
        eff_was_truncated = ctx.was_truncated
        eff_tool_errors = ctx.tool_result_errors
    else:
        step_no = int(ctx_or_step_no)
        content_str = str(state_or_content_str or "")
        eff_content_tok = content_tok
        eff_is_tool_output = is_tool_output_step
        eff_is_step_error = is_step_error
        eff_was_truncated = was_truncated
        eff_tool_errors = tool_result_errors or []
        assert state is not None
        eff_state = state

    has_gate_fail = False
    if eff_state.last_step_gate_cmds and content_str:
        has_gate_fail = any(
            marker in content_str
            for marker in (
                "Exit Code: 1", "Exit Code: 2", "exit code 1",
                "[FAIL]", "[REJECTED]", "[TRIAGE:", " Validation FAILED", " Check FAILED",
            )
        )
        if has_gate_fail:
            eff_state.transcript_cli_failed += 1
            err_snip = " ".join(content_str.split())[:180]
            for g_disp in eff_state.last_step_gate_cmds:
                eff_state.transcript_gate_bounces.append(FrictionSignal(
                    signal_type="GATE_BOUNCE",
                    severity="HIGH",
                    tier_source="Tier 1",
                    target=g_disp,
                    summary=f"驗證關卡 '{g_disp}' 於終端輸出退件 (Step {step_no})：{err_snip}",
                    details={"cmd": g_disp, "step": step_no},
                ))
        eff_state.last_step_gate_cmds = []

    if eff_is_tool_output and eff_state.pending_tool_context is not None and eff_content_tok > 0:
        p_tools = eff_state.pending_tool_context.get("tools", [])
        if p_tools:
            share_tok = max(1, int(round(eff_content_tok / len(p_tools))))
            for pt in p_tools:
                pt_name = pt["name"]
                ts_entry = eff_state.tool_token_stats.setdefault(
                    pt_name, {"calls": 0, "args_tokens": 0, "output_tokens": 0}
                )
                ts_entry["output_tokens"] += share_tok
                if pt.get("is_dup_read") and not eff_is_step_error:
                    eff_state.wasted_dup_reads += share_tok
                if pt.get("is_blind_read") and not eff_is_step_error:
                    eff_state.wasted_blind_reads += share_tok
                if pt.get("cmd_line"):
                    eff_state.heavy_cli_raw.append({
                        "step": step_no,
                        "command": pt["cmd_line"][:120],
                        "tokens": pt["args_tok"] + share_tok,
                        "output_tokens": share_tok,
                        "is_error": bool(eff_is_step_error or has_gate_fail),
                    })
            primary_pt = p_tools[0]
            eff_state.heavy_steps_raw.append({
                "step": step_no,
                "tool": primary_pt["name"],
                "target": primary_pt["target"][:90],
                "tokens": eff_content_tok + eff_state.pending_tool_context.get("total_args_tok", 0),
                "truncated": eff_was_truncated,
            })
        if has_gate_fail and not eff_is_step_error and not eff_tool_errors:
            eff_state.wasted_failed_ops += (
                eff_content_tok
                + eff_state.pending_tool_context.get("total_args_tok", 0)
                + eff_state.pending_tool_context.get("thinking_tok", 0)
            )
        eff_state.pending_tool_context = None


def _extract_step_thinking(
    ctx_or_obj: Union[_StepParseContext, Dict[str, Any]],
    state_or_payload_obj: Union[_TranscriptParseState, Dict[str, Any]],
    payload_type: str = "",
    state: Optional[_TranscriptParseState] = None,
) -> int:
    """提取單步 thinking 文本（相容 Antigravity, Claude Code thinking block 與 Codex reasoning summary）。"""
    if isinstance(ctx_or_obj, _StepParseContext):
        ctx: Optional[_StepParseContext] = ctx_or_obj
        eff_state = state_or_payload_obj if isinstance(state_or_payload_obj, _TranscriptParseState) else state
        assert eff_state is not None
        obj = ctx.obj
        payload_obj = ctx.payload_obj
        eff_payload_type = ctx.payload_type
    else:
        ctx = None
        obj = ctx_or_obj
        payload_obj = state_or_payload_obj if isinstance(state_or_payload_obj, dict) else {}
        eff_payload_type = payload_type
        assert state is not None
        eff_state = state

    step_type = str(obj.get("type") or "").upper()
    thinking_str = obj.get("thinking")
    if not thinking_str and isinstance(obj.get("message"), dict):
        msg_content = obj["message"].get("content")
        if isinstance(msg_content, list):
            for blk in msg_content:
                if isinstance(blk, dict) and blk.get("type") == "thinking":
                    thinking_str = blk.get("thinking") or blk.get("text")
                    break
    if not thinking_str and (step_type == "REASONING" or eff_payload_type == "reasoning"):
        summary_list = payload_obj.get("summary") or obj.get("summary")
        if isinstance(summary_list, list):
            thinking_str = " ".join(str(s.get("text") or "") for s in summary_list if isinstance(s, dict))
        elif isinstance(summary_list, str):
            thinking_str = summary_list

    step_thinking_tok = 0
    if isinstance(thinking_str, str) and thinking_str.strip():
        eff_state.thinking_steps += 1
        step_thinking_tok = _estimate_tokens(thinking_str)
        eff_state.tok_thinking += step_thinking_tok
        eff_state.last_thinking = " ".join(thinking_str.strip().split())[:300]

    if ctx is not None:
        ctx.step_thinking_tok = step_thinking_tok
    return step_thinking_tok


def _extract_step_tool_calls(
    ctx_or_obj: Union[_StepParseContext, Dict[str, Any]],
    payload_obj: Optional[Dict[str, Any]] = None,
    payload_type: str = "",
) -> List[Dict[str, Any]]:
    """提取單步 tool_calls 清單（相容 Antigravity, Claude tool_use 與 Codex function_call）。"""
    if isinstance(ctx_or_obj, _StepParseContext):
        ctx: Optional[_StepParseContext] = ctx_or_obj
        obj = ctx.obj
        eff_payload_obj = ctx.payload_obj
        eff_payload_type = ctx.payload_type
    else:
        ctx = None
        obj = ctx_or_obj
        eff_payload_obj = payload_obj or {}
        eff_payload_type = payload_type

    step_type = str(obj.get("type") or "").upper()
    tool_calls: List[Dict[str, Any]] = []

    def _parse_args(raw_a: Any) -> Dict[str, Any]:
        if isinstance(raw_a, str):
            try:
                parsed = json.loads(raw_a)
                return parsed if isinstance(parsed, dict) else {"raw": raw_a}
            except Exception:
                return {"raw": raw_a}
        return raw_a if isinstance(raw_a, dict) else {}

    raw_tcs = obj.get("tool_calls")
    if isinstance(raw_tcs, list):
        for tc in raw_tcs:
            if isinstance(tc, dict):
                raw_a = tc.get("args") or tc.get("arguments") or tc.get("input") or {}
                tool_calls.append({
                    "name": str(tc.get("name") or tc.get("tool_name") or "").lower(),
                    "args": _parse_args(raw_a),
                })
    elif isinstance(obj.get("message"), dict):
        msg_content = obj["message"].get("content")
        if isinstance(msg_content, list):
            for blk in msg_content:
                if isinstance(blk, dict) and blk.get("type") in ("tool_use", "function_call"):
                    raw_a = blk.get("input") or blk.get("arguments") or {}
                    tool_calls.append({
                        "name": str(blk.get("name") or "").lower(),
                        "args": _parse_args(raw_a),
                    })
    elif step_type in ("FUNCTION_CALL", "TOOL_CALL") or eff_payload_type in ("function_call", "custom_tool_call"):
        src_tc = eff_payload_obj if eff_payload_type in ("function_call", "custom_tool_call") else obj
        raw_a = src_tc.get("arguments") or src_tc.get("input") or src_tc.get("args") or {}
        tool_calls.append({
            "name": str(src_tc.get("name") or "").lower(),
            "args": _parse_args(raw_a),
        })

    if ctx is not None:
        ctx.tool_calls = tool_calls
    return tool_calls


def _handle_read_tool_call(
    step_no: int,
    target_file: str,
    t_args: Dict[str, Any],
    single_arg_tok: int,
    current_step_read_keys: List[str],
    state: _TranscriptParseState,
) -> Tuple[str, bool, bool]:
    """處理讀取類工具調用，偵測超長暫存檔污染、重複讀取與未檢索連續盲讀。"""
    state.total_read_ops += 1
    state.unique_read_files.add(target_file)
    lower_tf = target_file.lower().replace("\\", "/")
    is_media = lower_tf.endswith(MEDIA_EXTENSIONS)
    is_overflow_scratch = (
        ("/steps/" in lower_tf and lower_tf.endswith("/output.txt"))
        or "tool-results" in lower_tf
        or lower_tf.endswith("/transcript_full.jsonl")
    )
    start_ln = t_args.get("StartLine") or t_args.get("StartLineNumber") or t_args.get("offset") or ""
    end_ln = t_args.get("EndLine") or t_args.get("EndLineNumber") or t_args.get("limit") or ""
    byte_off = t_args.get("ByteOffset")
    byte_suffix = f"@{byte_off}" if byte_off is not None and str(byte_off) != "" else ""
    read_key = f"{target_file}:{start_ln}-{end_ln}{byte_suffix}"
    disp_target = f"{Path(target_file).name}:{start_ln}-{end_ln}{byte_suffix}"

    is_dup_read_call = False
    is_blind_read_call = False

    if is_overflow_scratch:
        is_dup_read_call = True
        state.wasted_dup_reads += single_arg_tok
        state.signals.append(FrictionSignal(
            signal_type="CONTEXT_WASTE",
            severity="HIGH",
            tier_source="Tier 1",
            target=Path(target_file).name,
            summary=f"讀取宿主超長截斷暫存檔或會話歷史日誌 '{disp_target}' (Step {step_no})，造成巨量 JSON/歷史日誌污染 Context",
            details={"subtype": "JSON_SNIPPET_OVERFLOW", "step": step_no, "path": target_file},
        ))
    elif not is_media:
        state.read_counts[read_key] = state.read_counts.get(read_key, 0) + 1
        current_step_read_keys.append(read_key)
        if state.read_counts[read_key] >= 2:
            is_dup_read_call = True
            state.wasted_dup_reads += single_arg_tok

    is_targeted_range_read = False
    if state.has_recent_kdb_query and start_ln != "" and end_ln != "":
        try:
            if 0 < (int(end_ln) - int(start_ln) + 1) <= 160:
                is_targeted_range_read = True
        except (ValueError, TypeError):
            pass

    if lower_tf.endswith(SOURCE_EXTENSIONS) and not is_targeted_range_read:
        state.consecutive_source_reads += 1
        if target_file not in state.consecutive_read_files:
            state.consecutive_read_files.append(target_file)
        if state.consecutive_source_reads > state.max_consecutive_reads:
            state.max_consecutive_reads = state.consecutive_source_reads
        if state.consecutive_source_reads >= 4 and not is_dup_read_call:
            is_blind_read_call = True
            state.wasted_blind_reads += single_arg_tok

    return disp_target, is_dup_read_call, is_blind_read_call


def _process_tool_calls_in_step(
    ctx_or_step_no: Union[_StepParseContext, int, None] = None,
    state_or_tool_calls: Union[_TranscriptParseState, List[Dict[str, Any]], None] = None,
    step_thinking_tok: int = 0,
    content_tok: int = 0,
    was_truncated: bool = False,
    state: Optional[_TranscriptParseState] = None,
    *,
    step_no: Optional[int] = None,
    tool_calls: Optional[List[Dict[str, Any]]] = None,
) -> Tuple[List[str], List[str], int]:
    """處理單步內所有 tool_calls，更新讀寫與 CLI 統計。"""
    if isinstance(ctx_or_step_no, _StepParseContext):
        ctx: Optional[_StepParseContext] = ctx_or_step_no
        eff_state = state_or_tool_calls if isinstance(state_or_tool_calls, _TranscriptParseState) else state
        assert eff_state is not None
        eff_step_no = ctx.step_no
        eff_tool_calls = ctx.tool_calls
        eff_thinking_tok = ctx.step_thinking_tok
        eff_content_tok = ctx.content_tok
        eff_was_truncated = ctx.was_truncated
    else:
        ctx = None
        eff_step_no = int(step_no if step_no is not None else (ctx_or_step_no or 0))
        eff_tool_calls = (
            tool_calls
            if tool_calls is not None
            else (state_or_tool_calls if isinstance(state_or_tool_calls, list) else [])
        )
        eff_thinking_tok = step_thinking_tok
        eff_content_tok = content_tok
        eff_was_truncated = was_truncated
        assert state is not None
        eff_state = state

    current_step_read_keys: List[str] = []
    current_step_gate_cmds: List[str] = []
    step_tools_meta: List[Dict[str, Any]] = []
    step_total_args_tok = 0

    for tc in eff_tool_calls:
        t_name = tc["name"].split(":")[-1] or "unknown"
        eff_state.total_tool_calls += 1
        eff_state.tool_dist[t_name] = eff_state.tool_dist.get(t_name, 0) + 1
        if "subagent" in t_name or t_name in ("task", "dispatch_agent"):
            eff_state.subagent_calls += 1

        t_args = tc["args"] if isinstance(tc["args"], dict) else {}
        try:
            single_arg_tok = _estimate_tokens(json.dumps(t_args, ensure_ascii=False))
        except Exception:
            single_arg_tok = _estimate_tokens(str(t_args))
        eff_state.tok_tool_args += single_arg_tok
        step_total_args_tok += single_arg_tok

        ts_entry = eff_state.tool_token_stats.setdefault(
            t_name, {"calls": 0, "args_tokens": 0, "output_tokens": 0}
        )
        ts_entry["calls"] += 1
        ts_entry["args_tokens"] += single_arg_tok

        target_file = str(
            t_args.get("Path") or t_args.get("AbsolutePath") or t_args.get("file_path")
            or t_args.get("path") or t_args.get("TargetFile") or t_args.get("filename") or ""
        ).strip().strip('"').strip("'")
        cmd_line = str(t_args.get("CommandLine") or t_args.get("command") or t_args.get("cmd") or "").strip()

        if (
            (any(m in cmd_line for m in ("knowledge-db", "kdb")) and any(k in cmd_line for k in ("search", "callers", "callees", "impact")))
            or ("ast" in cmd_line and any(k in cmd_line for k in ("outline", "callers", "callees", "impact")))
        ):
            eff_state.consecutive_source_reads = 0
            eff_state.has_recent_kdb_query = True

        if "yscb.py" in cmd_line:
            for m_cli in re.finditer(r"yscb\.py[\"\']?\s+([a-zA-Z0-9_-]+)(?:\s+([a-zA-Z0-9_-]+))?(?:\s+([a-zA-Z0-9_-]+))?", cmd_line):
                raw_mod_tok, sub1, sub2 = m_cli.group(1), m_cli.group(2) or "", m_cli.group(3) or ""
                mod_tok = "knowledge-db" if raw_mod_tok == "kdb" else raw_mod_tok
                eff_state.transcript_cli_calls += 1
                eff_state.transcript_cli_by_module[mod_tok] = eff_state.transcript_cli_by_module.get(mod_tok, 0) + 1
                sub_pair = f"{sub1} {sub2}".strip()
                for g_mod, g_cmd in GATE_COMMANDS:
                    if mod_tok == g_mod and (sub_pair.startswith(g_cmd) or sub1 == g_cmd):
                        current_step_gate_cmds.append(f"{g_mod} {g_cmd}")

        is_dup_read_call = False
        is_blind_read_call = False
        disp_target = Path(target_file).name if target_file else (cmd_line[:60] if cmd_line else t_name)

        if t_name in EDIT_TOOL_NAMES and target_file:
            eff_state.total_edit_ops += 1
            file_steps = eff_state.edit_history.setdefault(target_file, [])
            if not file_steps or file_steps[-1] != int(eff_step_no):
                file_steps.append(int(eff_step_no))
            edit_tok_list = eff_state.file_edit_step_tokens.setdefault(target_file, [])
            if edit_tok_list and edit_tok_list[-1][0] == int(eff_step_no):
                edit_tok_list[-1] = (int(eff_step_no), edit_tok_list[-1][1] + single_arg_tok)
            else:
                edit_tok_list.append((int(eff_step_no), single_arg_tok))
            for rk in list(eff_state.read_counts.keys()):
                if rk.startswith(f"{target_file}:"):
                    eff_state.read_counts[rk] = 0
            eff_state.consecutive_source_reads = 0
        elif t_name in READ_TOOL_NAMES and target_file:
            disp_target, is_dup_read_call, is_blind_read_call = _handle_read_tool_call(
                eff_step_no, target_file, t_args, single_arg_tok, current_step_read_keys, eff_state
            )

        step_tools_meta.append({
            "name": t_name,
            "target": disp_target,
            "cmd_line": cmd_line,
            "args_tok": single_arg_tok,
            "is_dup_read": is_dup_read_call,
            "is_blind_read": is_blind_read_call,
        })

    if step_tools_meta:
        eff_state.pending_tool_context = {
            "step": eff_step_no,
            "tools": step_tools_meta,
            "total_args_tok": step_total_args_tok,
            "thinking_tok": eff_thinking_tok,
        }
        eff_state.last_planner_thinking_tok = eff_thinking_tok
        eff_state.last_planner_args_tok = step_total_args_tok
        if step_total_args_tok >= 250:
            p_t = step_tools_meta[0]
            eff_state.heavy_steps_raw.append({
                "step": eff_step_no,
                "tool": p_t["name"],
                "target": p_t["target"][:90],
                "tokens": step_total_args_tok + eff_thinking_tok + eff_content_tok,
                "truncated": eff_was_truncated,
            })

    if ctx is not None:
        ctx.current_step_read_keys = current_step_read_keys
        ctx.current_step_gate_cmds = current_step_gate_cmds
        ctx.step_total_args_tok = step_total_args_tok

    return current_step_read_keys, current_step_gate_cmds, step_total_args_tok


def _record_step_error_signals(
    ctx_or_step_no: Union[_StepParseContext, int],
    state_or_obj: Union[_TranscriptParseState, Dict[str, Any], None] = None,
    payload_obj: Optional[Dict[str, Any]] = None,
    content_str: str = "",
    content_tok: int = 0,
    step_thinking_tok: int = 0,
    step_total_args_tok: int = 0,
    is_step_error: bool = False,
    is_tool_output_step: bool = False,
    tool_result_errors: Optional[List[str]] = None,
    tool_calls: Optional[List[Dict[str, Any]]] = None,
    current_step_read_keys: Optional[List[str]] = None,
    current_step_gate_cmds: Optional[List[str]] = None,
    state: Optional[_TranscriptParseState] = None,
) -> None:
    """處理單步錯誤狀態、讀檔失敗計數回滾與 TOOL_MISS_AND_RETRY 訊號記錄。"""
    if isinstance(ctx_or_step_no, _StepParseContext):
        ctx = ctx_or_step_no
        eff_state = state_or_obj if isinstance(state_or_obj, _TranscriptParseState) else state
        assert eff_state is not None
        step_no = ctx.step_no
        obj = ctx.obj
        eff_payload_obj = ctx.payload_obj
        eff_content_str = ctx.content_str
        eff_content_tok = ctx.content_tok
        eff_thinking_tok = ctx.step_thinking_tok
        eff_args_tok = ctx.step_total_args_tok
        eff_is_step_error = ctx.is_step_error
        eff_is_tool_output = ctx.is_tool_output_step
        eff_tool_errors = ctx.tool_result_errors
        eff_tool_calls = ctx.tool_calls
        eff_read_keys = ctx.current_step_read_keys
        eff_gate_cmds = ctx.current_step_gate_cmds
    else:
        step_no = int(ctx_or_step_no)
        obj = state_or_obj if isinstance(state_or_obj, dict) else {}
        eff_payload_obj = payload_obj or {}
        eff_content_str = content_str
        eff_content_tok = content_tok
        eff_thinking_tok = step_thinking_tok
        eff_args_tok = step_total_args_tok
        eff_is_step_error = is_step_error
        eff_is_tool_output = is_tool_output_step
        eff_tool_errors = tool_result_errors or []
        eff_tool_calls = tool_calls or []
        eff_read_keys = current_step_read_keys or []
        eff_gate_cmds = current_step_gate_cmds or []
        assert state is not None
        eff_state = state

    step_type = str(obj.get("type") or "").upper()
    if eff_is_step_error or eff_tool_errors:
        eff_state.wasted_failed_ops += eff_content_tok + eff_thinking_tok + eff_args_tok
        if eff_is_tool_output:
            eff_state.wasted_failed_ops += eff_state.last_planner_thinking_tok + eff_state.last_planner_args_tok
            eff_state.last_planner_thinking_tok = 0
            eff_state.last_planner_args_tok = 0

        raw_err_text = " ".join([
            str(eff_content_str or ""),
            str(obj.get("error") or ""),
            str(eff_payload_obj.get("error") or ""),
            *eff_tool_errors,
        ]).lower()
        is_read_err = any(
            k in raw_err_text
            for k in (
                "does not exist", "no such file", "not found:", "file not found",
                "cannot read", "is a directory", "permission denied",
            )
        )
        if is_read_err:
            keys_to_rollback = eff_state.last_step_read_keys if not eff_read_keys else eff_read_keys
            for rk in keys_to_rollback:
                if eff_state.read_counts.get(rk, 0) > 0:
                    eff_state.read_counts[rk] -= 1
        eff_state.last_step_read_keys = eff_read_keys
    else:
        if eff_tool_calls:
            eff_state.last_step_read_keys = eff_read_keys
        elif step_type == "GENERIC":
            eff_state.last_step_read_keys = []
            eff_state.last_planner_thinking_tok = 0
            eff_state.last_planner_args_tok = 0

    if eff_gate_cmds:
        eff_state.last_step_gate_cmds = eff_gate_cmds

    if eff_is_step_error:
        eff_state.error_steps += 1
        err_content = " ".join(str(eff_content_str or obj.get("error") or eff_payload_obj.get("error") or "").split())[:200]
        eff_state.signals.append(FrictionSignal(
            signal_type="TOOL_MISS_AND_RETRY",
            severity="MEDIUM",
            tier_source="Tier 1",
            target=f"Step {step_no}",
            summary=f"工具調用返回 ERROR 狀態：{err_content or 'Unknown error'}",
            details={"step": step_no},
        ))
        _append_thinking_excerpt_once(eff_state, step_no, "TOOL_ERROR")

    for tr_err in eff_tool_errors:
        eff_state.error_steps += 1
        eff_state.signals.append(FrictionSignal(
            signal_type="TOOL_MISS_AND_RETRY",
            severity="MEDIUM",
            tier_source="Tier 1",
            target=f"Step {step_no}",
            summary=f"工具調用返回 is_error=True：{tr_err or 'Tool execution error'}",
            details={"step": step_no},
        ))
        _append_thinking_excerpt_once(eff_state, step_no, "TOOL_ERROR")


def _build_churn_and_waste_signals(state: _TranscriptParseState) -> None:
    """掃描完成後彙整 MULTI_EDIT_CHURN 與 CONTEXT_WASTE 摩擦訊號。"""
    exempt_churn_files = {"changelog.md", "revision_log.md", "umbrella_overview.md"}
    multi_stage_sop_files = {"p00_discuss.md", "p06_test_plan.md", "fast_track_plan.md"}
    for fpath, steps in state.edit_history.items():
        short_name = Path(fpath).name
        lower_short = short_name.lower()
        if lower_short in exempt_churn_files:
            continue
        non_adjacent_edits = 1
        for i in range(1, len(steps)):
            if steps[i] - steps[i - 1] > 1:
                non_adjacent_edits += 1
        if lower_short in multi_stage_sop_files:
            is_churn = non_adjacent_edits >= 4 or len(steps) >= 5
        else:
            is_churn = non_adjacent_edits >= 2 or len(steps) >= 4
        if is_churn:
            edit_toks = state.file_edit_step_tokens.get(fpath, [])
            if len(edit_toks) >= 2:
                rework_slice = edit_toks[1:-1] if len(edit_toks) >= 3 else edit_toks[:-1]
                state.wasted_edit_churn += sum(t for _, t in rework_slice)
            state.signals.append(FrictionSignal(
                signal_type="MULTI_EDIT_CHURN",
                severity="HIGH" if non_adjacent_edits >= 3 else "MEDIUM",
                tier_source="Tier 1",
                target=short_name,
                summary=f"檔案 '{short_name}' 於單次對話中跨步驟修改 {len(steps)} 次 (橫跨 {non_adjacent_edits} 個非連續回合: Steps {steps})",
                details={"file_path": fpath, "edit_count": len(steps), "steps": steps},
            ))

    for read_key, count in state.read_counts.items():
        if count >= 2:
            short_name = Path(read_key.split(":")[0]).name
            state.signals.append(FrictionSignal(
                signal_type="CONTEXT_WASTE",
                severity="MEDIUM",
                tier_source="Tier 1",
                target=short_name,
                summary=f"相同檔案區段 '{read_key}' 被重複讀取 {count} 次",
                details={"read_key": read_key, "count": count},
            ))

    if state.max_consecutive_reads >= 4:
        sample_files = ", ".join(Path(p).name for p in state.consecutive_read_files[:4])
        state.signals.append(FrictionSignal(
            signal_type="CONTEXT_WASTE",
            severity="MEDIUM",
            tier_source="Tier 1",
            target="source_exploration",
            summary=f"未呼叫 knowledge-db search 或 ast outline 即連續原生翻讀 {state.max_consecutive_reads} 次源碼檔案 ({sample_files}...)",
            details={"max_consecutive_reads": state.max_consecutive_reads},
        ))


def _compile_tier1_stats(
    transcript_path: Path,
    full_path: Path,
    has_full_sibling: bool,
    state: _TranscriptParseState,
) -> Dict[str, Any]:
    """計算檔案大小補償、Token 效益與重度耗能排行並組裝 t1_stats 字典。"""
    try:
        compact_bytes = transcript_path.stat().st_size
    except OSError:
        compact_bytes = 0

    full_bytes = compact_bytes
    if has_full_sibling:
        try:
            full_bytes = max(compact_bytes, full_path.stat().st_size)
        except OSError:
            full_bytes = compact_bytes

    est_parsed = state.tok_user + state.tok_model + state.tok_thinking + state.tok_tool_args + state.tok_tool_out
    if has_full_sibling:
        extra_truncated_tokens = 0
        est_full = est_parsed
        untruncated_ratio = max(0.1, compact_bytes / float(full_bytes)) if full_bytes > 0 else 1.0
        est_compact = int(round(est_parsed * untruncated_ratio))
    else:
        extra_truncated_bytes = max(0, full_bytes - compact_bytes)
        extra_truncated_tokens = int(round(extra_truncated_bytes / 4.2))
        est_compact = est_parsed
        est_full = est_compact + extra_truncated_tokens

    raw_wasted = state.wasted_dup_reads + state.wasted_failed_ops + state.wasted_edit_churn + state.wasted_blind_reads
    total_for_eff = max(1, est_full)
    capped_wasted = min(est_full, raw_wasted)
    effective_tok = max(0, est_full - capped_wasted)
    eff_pct = round((effective_tok / float(total_for_eff)) * 100.0, 1) if est_full > 0 else 100.0
    waste_pct = round(100.0 - eff_pct, 1) if est_full > 0 else 0.0

    by_tool_list: List[Dict[str, Any]] = []
    for t_k, t_v in state.tool_token_stats.items():
        calls_c = max(1, t_v["calls"])
        t_tot = t_v["args_tokens"] + t_v["output_tokens"]
        by_tool_list.append({
            "tool": t_k,
            "calls": t_v["calls"],
            "args_tokens": t_v["args_tokens"],
            "output_tokens": t_v["output_tokens"],
            "total_tokens": t_tot,
            "avg_tokens": int(round(t_tot / float(calls_c))),
            "share_pct": round((t_tot / float(total_for_eff)) * 100.0, 1),
        })
    by_tool_list.sort(key=lambda x: x["total_tokens"], reverse=True)

    dedup_steps: Dict[int, Dict[str, Any]] = {}
    for hs in state.heavy_steps_raw:
        s_id = int(hs["step"])
        if s_id not in dedup_steps or hs["tokens"] > dedup_steps[s_id]["tokens"]:
            dedup_steps[s_id] = hs
    top_heavy_steps = sorted(dedup_steps.values(), key=lambda x: x["tokens"], reverse=True)[:5]
    top_heavy_cli = sorted(state.heavy_cli_raw, key=lambda x: x["tokens"], reverse=True)[:5]
    sorted_tools = dict(sorted(state.tool_dist.items(), key=lambda x: x[1], reverse=True)[:15])

    return {
        "first_ts": state.first_ts,
        "last_ts": state.last_ts,
        "tokens": {
            "estimated_compact_tokens": est_compact,
            "estimated_full_tokens": est_full,
            "exact_full_parsed": has_full_sibling,
            "by_category": {
                "user_input": state.tok_user,
                "model_output": state.tok_model,
                "thinking": state.tok_thinking,
                "tool_call_args": state.tok_tool_args,
                "tool_outputs": state.tok_tool_out + extra_truncated_tokens,
            },
            "reported_api_usage": {
                "input_tokens": state.api_in_tokens,
                "output_tokens": state.api_out_tokens,
                "cache_read_tokens": state.api_cache_read,
                "cache_creation_tokens": state.api_cache_create,
                "total_tokens": state.api_in_tokens + state.api_out_tokens + state.api_cache_read + state.api_cache_create,
            },
            "transcript_compact_kb": round(compact_bytes / 1024.0, 2),
            "transcript_full_kb": round(full_bytes / 1024.0, 2),
        },
        "token_efficiency": {
            "total_tokens": est_full,
            "effective_tokens": effective_tok,
            "wasted_tokens": capped_wasted,
            "efficiency_pct": eff_pct,
            "waste_pct": waste_pct,
            "wasted_breakdown": {
                "duplicate_reads": state.wasted_dup_reads,
                "failed_tool_steps": state.wasted_failed_ops,
                "edit_churn_rework": state.wasted_edit_churn,
                "unindexed_blind_reads": state.wasted_blind_reads,
            },
        },
        "top_consumers": {
            "by_tool": by_tool_list[:10],
            "heavy_steps": top_heavy_steps,
            "heavy_cli_commands": top_heavy_cli,
        },
        "steps_and_tools": {
            "total_steps": state.total_steps,
            "user_turns": state.user_turns,
            "model_turns": state.model_turns,
            "thinking_steps": state.thinking_steps,
            "truncated_steps": state.truncated_steps,
            "error_steps": state.error_steps,
            "total_tool_calls": state.total_tool_calls,
            "tool_distribution": sorted_tools,
            "subagent_calls": state.subagent_calls,
            "total_read_ops": state.total_read_ops,
            "unique_files_read": len(state.unique_read_files),
            "total_edit_ops": state.total_edit_ops,
            "unique_files_edited": len(state.edit_history),
        },
        "transcript_cli": {
            "cli_total_calls": state.transcript_cli_calls,
            "cli_failed_calls": state.transcript_cli_failed,
            "cli_by_module": state.transcript_cli_by_module,
            "gate_bounces": state.transcript_gate_bounces,
        },
        "topic": state.topic,
    }


def _iter_jsonl_records(
    transcript_path: Path,
    full_path: Path,
    has_full_sibling: bool,
    state: _TranscriptParseState,
) -> Iterator[Tuple[int, Dict[str, Any], bool]]:
    """
    Streams JSONL records line-by-line with a bounded per-line read cap (`MAX_JSONL_LINE_BYTES`),
    preventing multi-megabyte single-line tool payloads from spiking process memory.
    """
    with open(transcript_path, "r", encoding="utf-8", errors="replace") as f:
        full_f = open(full_path, "r", encoding="utf-8", errors="replace") if has_full_sibling else None
        try:
            line_idx = 0
            while True:
                line = f.readline(MAX_JSONL_LINE_BYTES)
                if not line:
                    break
                if len(line) == MAX_JSONL_LINE_BYTES and not line.endswith("\n"):
                    while True:
                        rem = f.readline(MAX_JSONL_LINE_BYTES)
                        if not rem or rem.endswith("\n"):
                            break

                full_line = ""
                if full_f is not None:
                    full_line = full_f.readline(MAX_JSONL_LINE_BYTES)
                    if len(full_line) == MAX_JSONL_LINE_BYTES and not full_line.endswith("\n"):
                        while True:
                            rem_full = full_f.readline(MAX_JSONL_LINE_BYTES)
                            if not rem_full or rem_full.endswith("\n"):
                                break

                line_idx += 1
                s = line.strip()
                if not s:
                    continue
                try:
                    obj = json.loads(s)
                    if not isinstance(obj, dict):
                        continue
                except Exception:
                    continue

                state.total_steps += 1
                step_no = obj.get("step_index", line_idx)
                was_truncated = bool(obj.get("truncated_fields"))
                if was_truncated:
                    state.truncated_steps += 1
                    if full_line:
                        try:
                            full_obj = json.loads(full_line.strip())
                            if isinstance(full_obj, dict):
                                obj = full_obj
                        except Exception:
                            pass
                yield step_no, obj, was_truncated
        finally:
            if full_f is not None:
                full_f.close()


def parse_transcript_file(
    transcript_path: Path,
) -> Tuple[Optional[str], List[FrictionSignal], List[Dict[str, Any]], Dict[str, Any]]:
    """
    串流解析鎖定之 .jsonl 對話紀錄，提取：
    1. 首筆時間戳 first_ts
    2. MULTI_EDIT_CHURN、CONTEXT_WASTE、TOOL_MISS_AND_RETRY
    3. 事發前後之 <thinking> 摘要（強制截斷 <= 300 字元）
    4. 會話基礎統計與 Token 消耗估算 (t1_stats)
    """
    state = _TranscriptParseState()
    full_path = transcript_path.parent / "transcript_full.jsonl"
    has_full_sibling = full_path.is_file() and full_path != transcript_path

    try:
        for step_no, obj, was_truncated in _iter_jsonl_records(transcript_path, full_path, has_full_sibling, state):
            ts_val = obj.get("created_at") or obj.get("timestamp") or obj.get("ts")
            if isinstance(ts_val, str) and ts_val.strip():
                clean_ts = ts_val.strip()
                if state.first_ts is None:
                    state.first_ts = clean_ts
                state.last_ts = clean_ts

            _accumulate_api_usage(obj, state)

            payload_obj = obj.get("payload") if isinstance(obj.get("payload"), dict) else {}
            payload_type = str(payload_obj.get("type") or "").lower()
            status_str = str(obj.get("status") or payload_obj.get("status") or "").upper()
            is_step_error = (
                status_str in ("ERROR", "FAILED")
                or obj.get("is_error") is True
                or payload_obj.get("is_error") is True
            )

            ctx = _StepParseContext(
                step_no=step_no,
                obj=obj,
                payload_obj=payload_obj,
                payload_type=payload_type,
                was_truncated=was_truncated,
                is_step_error=is_step_error,
            )

            _extract_step_content_and_role(ctx, state)
            _attribute_tool_output_tokens(ctx, state)
            _extract_step_thinking(ctx, state)
            _extract_step_tool_calls(ctx)
            _process_tool_calls_in_step(ctx, state)
            _record_step_error_signals(ctx, state)
    except (OSError, PermissionError):
        return None, [], [], {}

    _build_churn_and_waste_signals(state)
    t1_stats = _compile_tier1_stats(transcript_path, full_path, has_full_sibling, state)
    return state.first_ts, state.signals, state.thinking_excerpts, t1_stats
