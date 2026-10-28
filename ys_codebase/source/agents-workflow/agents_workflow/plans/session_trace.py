"""
Session Trace & Friction Signal Extraction Engine (3-Tier Progressive Fallback).
100% Python Standard Library.
"""
import json
import os
import re
import subprocess
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

from .scanner import PlanScanner
from .status import PlanStatusResolver


def _resolve_uri_safe(uri_str: str, default_rel: str = "") -> Path:
    """安全解析語意 URI，失敗時回退至相對路徑。"""
    try:
        from core import uri  # type: ignore
        res = uri.resolve(uri_str, interactive=False)
        if res and not str(res).startswith("!"):
            return Path(res).resolve()
    except Exception:
        pass
    host_dir = os.environ.get("YSCB_HOST_DIR", os.getcwd())
    return (Path(host_dir) / default_rel).resolve() if default_rel else Path(host_dir).resolve()


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


def _format_duration(seconds: float) -> str:
    """格式化秒數為人類易讀字串 (如 1h 23m 45s)。"""
    if seconds <= 0:
        return "0s"
    sec = int(round(seconds))
    h, rem = divmod(sec, 3600)
    m, s = divmod(rem, 60)
    if h > 0:
        return f"{h}h {m}m {s}s"
    if m > 0:
        return f"{m}m {s}s"
    return f"{s}s"



@dataclass
class FrictionSignal:
    """單筆硬性摩擦訊號結構。"""
    signal_type: str          # MULTI_EDIT_CHURN | TOOL_MISS_AND_RETRY | SILENT_BACKPATCH | GATE_BOUNCE | CONTEXT_WASTE | VALIDATED_BACKPROP
    severity: str             # HIGH | MEDIUM | INFO
    tier_source: str          # Tier 1 | Tier 2
    target: str               # 檔案路徑、CLI 指令或階段檔名
    summary: str              # 摩擦證據簡述
    details: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "signal_type": self.signal_type,
            "severity": self.severity,
            "tier_source": self.tier_source,
            "target": self.target,
            "summary": self.summary,
            "details": self.details,
        }


@dataclass
class SessionTraceReport:
    """三級軌跡提取與摩擦訊號分析完整報告。"""
    active_tier: str
    transcript_path: Optional[str] = None
    transcript_candidates: List[Dict[str, Any]] = field(default_factory=list)
    target_plan: Optional[str] = None
    plan_resolution_note: str = ""
    session_start_ts: Optional[str] = None
    telemetry_count: int = 0
    git_changed_files: List[str] = field(default_factory=list)
    session_stats: Dict[str, Any] = field(default_factory=dict)
    signals: List[FrictionSignal] = field(default_factory=list)
    thinking_excerpts: List[Dict[str, Any]] = field(default_factory=list)
    fallback_checklist: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "active_tier": self.active_tier,
            "transcript_path": self.transcript_path,
            "transcript_candidates": self.transcript_candidates,
            "target_plan": self.target_plan,
            "plan_resolution_note": self.plan_resolution_note,
            "session_start_ts": self.session_start_ts,
            "telemetry_count": self.telemetry_count,
            "git_changed_files": self.git_changed_files,
            "session_stats": self.session_stats,
            "signals": [s.to_dict() for s in self.signals],
            "thinking_excerpts": self.thinking_excerpts,
            "fallback_checklist": self.fallback_checklist,
        }

    def render_text(self) -> str:
        lines: List[str] = []
        lines.append("=" * 72)
        lines.append("YS-Codebase Session Trace & Friction Diagnostic Report")
        lines.append("=" * 72)
        lines.append(f"Active Tier       : {self.active_tier}")
        lines.append(f"Transcript Source : {self.transcript_path or 'None (Tier 2/3 Mode)'}")
        lines.append(f"Target Plan       : {self.target_plan or 'None'}")
        if self.plan_resolution_note:
            lines.append(f"Plan Note         : {self.plan_resolution_note}")
        lines.append(f"Session Start     : {self.session_start_ts or 'Full Window'}")
        lines.append(f"CLI Telemetry     : {self.telemetry_count} event(s) in window")
        if self.git_changed_files:
            lines.append(f"Git Changed Files : {len(self.git_changed_files)} file(s)")
        lines.append("-" * 72)

        if self.session_stats:
            tok = self.session_stats.get("tokens", {})
            st = self.session_stats.get("steps_and_tools", {})
            tc = self.session_stats.get("time_and_cli", {})
            cat = tok.get("by_category", {})
            lines.append("Session Baseline Metrics:")
            lines.append(
                f"  * Duration & Turns : {tc.get('session_duration_human', '0s')} "
                f"| Steps: {st.get('total_steps', 0)} (User: {st.get('user_turns', 0)}, "
                f"Model: {st.get('model_turns', 0)}, Thinking: {st.get('thinking_steps', 0)}, "
                f"Truncated: {st.get('truncated_steps', 0)}, Errors: {st.get('error_steps', 0)})"
            )
            lines.append(
                f"  * Estimated Tokens : ~{tok.get('estimated_full_tokens', 0):,} full / "
                f"~{tok.get('estimated_compact_tokens', 0):,} compact "
                f"(User: {cat.get('user_input', 0):,}, Model: {cat.get('model_output', 0):,}, "
                f"Thinking: {cat.get('thinking', 0):,}, ToolArgs: {cat.get('tool_call_args', 0):,}, "
                f"ToolOut: {cat.get('tool_outputs', 0):,})"
            )
            rep_usage = tok.get("reported_api_usage", {})
            if rep_usage.get("total_tokens", 0) > 0:
                lines.append(
                    f"  * Native API Usage : Total {rep_usage.get('total_tokens', 0):,} "
                    f"(In: {rep_usage.get('input_tokens', 0):,}, Out: {rep_usage.get('output_tokens', 0):,}, "
                    f"CacheRead: {rep_usage.get('cache_read_tokens', 0):,})"
                )
            lines.append(
                f"  * Tool & File Ops  : {st.get('total_tool_calls', 0)} call(s), "
                f"Read: {st.get('total_read_ops', 0)} ops ({st.get('unique_files_read', 0)} files), "
                f"Edit: {st.get('total_edit_ops', 0)} ops ({st.get('unique_files_edited', 0)} files), "
                f"Subagents: {st.get('subagent_calls', 0)}"
            )
            lines.append(
                f"  * CLI Telemetry    : {tc.get('cli_total_calls', 0)} call(s), "
                f"Failed: {tc.get('cli_failed_calls', 0)}, "
                f"Time: {tc.get('cli_total_duration_ms', 0)} ms (avg {tc.get('cli_avg_duration_ms', 0)} ms), "
                f"Modes: {tc.get('cli_by_mode', {})}"
            )
            eff = self.session_stats.get("token_efficiency", {})
            if eff and eff.get("total_tokens", 0) > 0:
                wb = eff.get("wasted_breakdown", {})
                lines.append(
                    f"  * Token Efficiency : Effective ~{eff.get('effective_tokens', 0):,} ({eff.get('efficiency_pct', 100.0)}%) "
                    f"| Wasted ~{eff.get('wasted_tokens', 0):,} ({eff.get('waste_pct', 0.0)}%: "
                    f"DupReads={wb.get('duplicate_reads', 0):,}, FailedOps={wb.get('failed_tool_steps', 0):,}, "
                    f"ChurnRework={wb.get('edit_churn_rework', 0):,}, BlindReads={wb.get('unindexed_blind_reads', 0):,})"
                )
            tc_prof = self.session_stats.get("top_consumers", {})
            if tc_prof:
                by_t = tc_prof.get("by_tool", [])[:3]
                if by_t:
                    t_str = ", ".join(
                        f"{x['tool']}={x['total_tokens']:,}({x['share_pct']}%, avg {x['avg_tokens']:,})"
                        for x in by_t
                    )
                    lines.append(f"  * Top Tool Tokens  : {t_str}")
                h_steps = tc_prof.get("heavy_steps", [])[:3]
                if h_steps:
                    hs_str = ", ".join(
                        f"Step {x['step']}[{x['tool']}->{x['target']}]({x['tokens']:,})"
                        for x in h_steps
                    )
                    lines.append(f"  * Heavy Steps Top3 : {hs_str}")
                h_clis = tc_prof.get("heavy_cli_commands", [])[:3]
                if h_clis:
                    hc_str = ", ".join(
                        f"Step {x['step']}[{x['command'][:40]}]({x['tokens']:,})"
                        for x in h_clis
                    )
                    lines.append(f"  * Heavy CLI Top3   : {hc_str}")
            lines.append("-" * 72)

        if self.transcript_candidates:
            lines.append("[WARN] 偵測到多份工作區候選 Transcript 且無尾行自指信標，依零臆測原則拒絕盲猜：")
            for idx, cand in enumerate(self.transcript_candidates, 1):
                lines.append(f"  {idx}. [{cand.get('target')}] {cand.get('path')} (mtime: {cand.get('mtime_iso')})")
            lines.append("  -> 請以 '--transcript <path>' 明確指定目標對話紀錄。")
            lines.append("-" * 72)

        if self.signals:
            lines.append(f"Detected Friction Signals ({len(self.signals)}):")
            for idx, sig in enumerate(self.signals, 1):
                lines.append(
                    f"  [{idx:02d}] [{sig.severity}] ({sig.tier_source}) {sig.signal_type} @ {sig.target}"
                )
                lines.append(f"       |-- {sig.summary}")
        else:
            lines.append("Detected Friction Signals (0): 未偵測到顯著硬性摩擦訊號。")

        if self.thinking_excerpts:
            lines.append("-" * 72)
            lines.append(f"Incident Thinking Excerpts ({len(self.thinking_excerpts)}):")
            for ex in self.thinking_excerpts:
                lines.append(f"  * [Step {ex.get('step')}] ({ex.get('context')}): {ex.get('excerpt')}")

        if self.fallback_checklist:
            lines.append("-" * 72)
            lines.append("[Fallback: In-Context Mode] 強制回合逆向審訊檢核表：")
            for item in self.fallback_checklist:
                lines.append(f"  - [ ] {item}")

        lines.append("=" * 72)
        return "\n".join(lines)


class SessionTraceEngine:
    """
    三級漸進式軌跡提取與五大硬性摩擦訊號偵測引擎：
    - Tier 1: 多宿主 release_targets 本地 .jsonl 三層信標定錨與思考鏈提取
    - Tier 2: core.telemetry (cache://core/telemetry.jsonl) 時間窗切片 + 計畫 mtime 回寫消歧
    - Tier 3: In-Context 結構化逆向審訊保底
    """

    EDIT_TOOL_NAMES = {
        "edit_file", "write_file", "edit", "write", "multiedit", "replace",
        "replace_file_content", "multi_replace_file_content",
    }
    READ_TOOL_NAMES = {
        "read_file", "view_file", "read", "view", "view_file_outline",
    }
    GATE_COMMANDS = {
        ("agents-workflow", "plan verify"),
        ("agents-workflow", "plan check"),
        ("agents-workflow", "compile"),
        ("dev", "check"),
        ("dev", "test"),
        ("core", "contributes check"),
    }

    def __init__(
        self,
        plans_dir: Optional[Union[str, Path]] = None,
        archive_dir: Optional[Union[str, Path]] = None,
        project_root: Optional[Union[str, Path]] = None,
        telemetry_path: Optional[Union[str, Path]] = None,
        custom_transcript_dirs: Optional[Dict[str, List[Path]]] = None,
    ) -> None:
        self.plans_dir = Path(plans_dir).resolve() if plans_dir else _resolve_uri_safe("workflow.plans://", "plans")
        self.archive_dir = (
            Path(archive_dir).resolve() if archive_dir else _resolve_uri_safe("workflow.archived://", "plans/archived")
        )
        self.project_root = (
            Path(project_root).resolve() if project_root else _resolve_uri_safe("project://", "")
        )
        self.telemetry_path = Path(telemetry_path).resolve() if telemetry_path else None
        self.custom_transcript_dirs = custom_transcript_dirs

    def _get_configured_release_targets(self) -> List[str]:
        """讀取當前專案配置之 release_targets 清單。"""
        targets: List[str] = []
        try:
            from core import config  # type: ignore
            val = config.get("agents-workflow", "release_targets")
            if isinstance(val, list) and val:
                targets = [str(x).strip().lower() for x in val if str(x).strip()]
        except Exception:
            pass
        if not targets:
            cfg_file = _resolve_uri_safe("config://agents-workflow/config.project.json", "ys_codebase/config/agents-workflow/config.project.json")
            if cfg_file.is_file():
                try:
                    data = json.loads(cfg_file.read_text(encoding="utf-8"))
                    raw_t = data.get("release_targets", [])
                    if isinstance(raw_t, list):
                        targets = [str(x).strip().lower() for x in raw_t if str(x).strip()]
                except Exception:
                    pass
        return targets or ["antigravity", "claude", "codex"]

    def _collect_candidate_jsonls(
        self, release_targets: List[str], max_files: int = 30
    ) -> List[Tuple[str, Path, float]]:
        """
        依啟用之 release_targets 收集本機近期活躍之 .jsonl 候選檔案。
        全程防護 PermissionError / OSError (EC-05)。
        回傳 [(target_name, path, mtime), ...] 按 mtime 降序排列。
        """
        candidates: List[Tuple[str, Path, float]] = []
        home = Path.home()

        # 支援環境變數覆寫供測試或容器掛載
        env_dirs = os.environ.get("YSCB_TRANSCRIPT_DIRS", "").strip()
        search_map: Dict[str, List[Path]] = {}
        if self.custom_transcript_dirs is not None:
            search_map = self.custom_transcript_dirs
        elif env_dirs:
            search_map["custom"] = [Path(p.strip()) for p in env_dirs.split(os.pathsep) if p.strip()]
        else:
            search_map = {
                "antigravity": [home / ".gemini" / "antigravity" / "brain"],
                "claude": [home / ".claude" / "projects"],
                "codex": [home / ".codex" / "sessions"],
            }

        ordered_targets = list(release_targets)
        for t in search_map:
            if t not in ordered_targets:
                ordered_targets.append(t)

        seen_paths = set()
        for target in ordered_targets:
            roots = search_map.get(target, [])
            for root in roots:
                try:
                    if not root.exists() or not root.is_dir():
                        continue
                    if target == "antigravity":
                        for conv_dir in root.iterdir():
                            if not conv_dir.is_dir():
                                continue
                            t_file = conv_dir / ".system_generated" / "logs" / "transcript.jsonl"
                            if t_file.is_file() and t_file not in seen_paths:
                                seen_paths.add(t_file)
                                candidates.append((target, t_file, t_file.stat().st_mtime))
                    else:
                        for j_file in root.rglob("*.jsonl"):
                            if j_file.name == "transcript_full.jsonl":
                                continue
                            if j_file.is_file() and j_file not in seen_paths:
                                seen_paths.add(j_file)
                                candidates.append((target, j_file, j_file.stat().st_mtime))
                except (OSError, PermissionError):
                    continue

        candidates.sort(key=lambda x: x[2], reverse=True)
        return candidates[:max_files] if max_files > 0 else candidates

    def _inspect_candidate_beacon(self, file_path: Path) -> Dict[str, Any]:
        """
        讀取候選 .jsonl 頭中尾切片（首 64KB + 中段 64KB + 尾 64KB），檢查：
        1. 是否精確匹配當前 project_root 工作區指紋（支援偵測主導工作區，避免跨專案關鍵字誤認）
        2. 尾端是否包含當前正在執行之 session-trace / /session-audit 自指信標
        3. 是否為唯讀審查或無 USER_INPUT 之 Subagent 對話
        """
        info: Dict[str, Any] = {
            "matches_workspace": False,
            "detected_workspace": "",
            "has_self_beacon": False,
            "is_subagent": False,
        }
        proj_str = str(self.project_root).replace("\\", "/").rstrip("/")
        proj_name = self.project_root.name

        try:
            size = file_path.stat().st_size
            with open(file_path, "rb") as f:
                head_bytes = f.read(min(65536, size))
                mid_bytes = b""
                if size > 196608:
                    f.seek(size // 2 - 32768)
                    mid_bytes = f.read(65536)
                if size > 65536:
                    f.seek(max(0, size - 65536))
                    tail_bytes = f.read(65536)
                else:
                    tail_bytes = b""

            head_text = head_bytes.decode("utf-8", errors="ignore").replace("\\", "/")
            mid_text = mid_bytes.decode("utf-8", errors="ignore").replace("\\", "/")
            tail_text = tail_bytes.decode("utf-8", errors="ignore").replace("\\", "/")
            combined = head_text + "\n" + mid_text + "\n" + tail_text

            # 統計 /workspace/<name> 出現頻次以判定主導工作區（防範在 A 專案中僅文字提及 B 專案）
            ws_hits = re.findall(r"/workspace/([A-Za-z0-9_.\-]+)", combined)
            dominant_ws = ""
            if ws_hits:
                ws_counts: Dict[str, int] = {}
                for w in ws_hits:
                    ws_counts[w] = ws_counts.get(w, 0) + 1
                dominant_ws = max(ws_counts.items(), key=lambda x: x[1])[0]
                info["detected_workspace"] = f"/workspace/{dominant_ws}"

            encoded_proj = proj_str.replace("/", "-").lstrip("-")
            if dominant_ws:
                if dominant_ws == proj_name or proj_str.endswith(f"/{dominant_ws}"):
                    info["matches_workspace"] = True
            elif (
                proj_str in combined
                or (proj_name and f"/{proj_name}/" in combined)
                or (encoded_proj and encoded_proj in str(file_path))
            ):
                info["matches_workspace"] = True

            # 檢查尾端最後幾筆紀錄是否出現 session-trace 或 /session-audit 自指信標
            tail_last_chunk = (tail_text if tail_text else head_text)[-16384:]
            if "session-trace" in tail_last_chunk or "/session-audit" in tail_last_chunk:
                info["has_self_beacon"] = True

            # 識別是否為 Subagent 對話：
            # (a) 審查員提示詞特徵，或 (b) 首筆為 <SYSTEM_MESSAGE> 且全切片無 USER_INPUT / USER_EXPLICIT
            if "REVIEW_STATUS:" in head_text or "你是一個無歷史包袱的獨立" in head_text:
                info["is_subagent"] = True
            else:
                first_line = head_text.splitlines()[0] if head_text else ""
                has_user_turn = (
                    '"USER_INPUT"' in combined
                    or '"USER_EXPLICIT"' in combined
                    or '"role": "user"' in combined
                    or '"role":"user"' in combined
                )
                if "<SYSTEM_MESSAGE>" in first_line and not has_user_turn:
                    info["is_subagent"] = True
        except (OSError, PermissionError):
            pass

        return info

    def locate_transcript(
        self,
        explicit_path: Optional[str] = None,
        release_targets: Optional[List[str]] = None,
    ) -> Tuple[Optional[Path], List[Dict[str, Any]]]:
        """
        三層信標定錨：
        1. 優先級 1：顯式傳入 --transcript <path>
        2. 優先級 2：掃描啟用之 release_targets，以「工作區指紋 + 尾行自指信標」鎖定主視窗
        3. 優先級 3：若無自指信標且匹配多份工作區 .jsonl，拒絕盲猜並回傳候選清單 (EC-01)
        """
        if explicit_path:
            p = Path(explicit_path).expanduser().resolve()
            if p.is_file():
                return p, []
            return None, []

        targets = release_targets or self._get_configured_release_targets()
        raw_candidates = self._collect_candidate_jsonls(targets)
        if not raw_candidates:
            return None, []

        workspace_matched: List[Dict[str, Any]] = []
        beacon_matched: List[Path] = []

        for target_name, fpath, mtime in raw_candidates:
            beacon = self._inspect_candidate_beacon(fpath)
            if not beacon["matches_workspace"]:
                continue
            mtime_iso = datetime.fromtimestamp(mtime, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
            if beacon["has_self_beacon"] and not beacon["is_subagent"]:
                beacon_matched.append(fpath)
            if not beacon["is_subagent"]:
                workspace_matched.append({
                    "target": target_name,
                    "path": str(fpath),
                    "mtime": mtime,
                    "mtime_iso": mtime_iso,
                    "has_self_beacon": beacon["has_self_beacon"],
                })

        # 命中尾行自指信標之最新主視窗
        if beacon_matched:
            return beacon_matched[0], []

        # 若僅有唯一一份屬於本工作區的主對話 .jsonl
        if len(workspace_matched) == 1:
            return Path(workspace_matched[0]["path"]), []

        # 多份工作區候選但無尾行自指信標：依零臆測原則回傳候選清單 (EC-01)
        if len(workspace_matched) > 1:
            return None, workspace_matched[:5]

        return None, []

    def _parse_transcript_file(
        self, transcript_path: Path
    ) -> Tuple[Optional[str], List[FrictionSignal], List[Dict[str, Any]], Dict[str, Any]]:
        """
        串流解析鎖定之 .jsonl 對話紀錄，提取：
        1. 首筆時間戳 first_ts
        2. MULTI_EDIT_CHURN（同檔多次修改震盪）、CONTEXT_WASTE（重複讀取或未檢索連續翻讀）、TOOL_MISS_AND_RETRY
        3. 事發前後之 <thinking> 摘要（強制截斷 <= 300 字元，NFR-02）
        4. 會話基礎統計與 Token 消耗估算 (t1_stats)
        """
        first_ts: Optional[str] = None
        last_ts: Optional[str] = None
        signals: List[FrictionSignal] = []
        thinking_excerpts: List[Dict[str, Any]] = []

        edit_history: Dict[str, List[int]] = {}
        read_counts: Dict[str, int] = {}
        unique_read_files: set[str] = set()
        consecutive_source_reads = 0
        max_consecutive_reads = 0
        consecutive_read_files: List[str] = []
        last_thinking: str = ""

        total_steps = 0
        user_turns = 0
        model_turns = 0
        thinking_steps = 0
        truncated_steps = 0
        error_steps = 0
        total_tool_calls = 0
        total_read_ops = 0
        total_edit_ops = 0
        subagent_calls = 0
        tool_dist: Dict[str, int] = {}

        tok_user = 0
        tok_model = 0
        tok_thinking = 0
        tok_tool_args = 0
        tok_tool_out = 0
        api_in_tokens = 0
        api_out_tokens = 0
        api_cache_read = 0
        api_cache_create = 0

        last_step_read_keys: List[str] = []
        last_step_gate_cmds: List[str] = []
        transcript_cli_calls = 0
        transcript_cli_failed = 0
        transcript_cli_by_module: Dict[str, int] = {}
        transcript_gate_bounces: List[FrictionSignal] = []

        # Token 效益與高耗能追蹤結構 (REV-05 / REV-06)
        wasted_dup_reads = 0
        wasted_failed_ops = 0
        wasted_edit_churn = 0
        wasted_blind_reads = 0
        has_recent_kdb_query = False
        file_edit_step_tokens: Dict[str, List[Tuple[int, int]]] = {}
        tool_token_stats: Dict[str, Dict[str, int]] = {}
        heavy_steps_raw: List[Dict[str, Any]] = []
        heavy_cli_raw: List[Dict[str, Any]] = []
        pending_tool_context: Optional[Dict[str, Any]] = None
        last_planner_thinking_tok: int = 0
        last_planner_args_tok: int = 0

        full_path = transcript_path.parent / "transcript_full.jsonl"
        has_full_sibling = full_path.is_file() and full_path != transcript_path

        try:
            with open(transcript_path, "r", encoding="utf-8", errors="replace") as f:
                full_f = (
                    open(full_path, "r", encoding="utf-8", errors="replace")
                    if has_full_sibling
                    else None
                )
                try:
                    for line_idx, line in enumerate(f, 1):
                        full_line = full_f.readline() if full_f is not None else ""
                        s = line.strip()
                        if not s:
                            continue
                        try:
                            obj = json.loads(s)
                            if not isinstance(obj, dict):
                                continue
                        except Exception:
                            continue

                        total_steps += 1
                        step_no = obj.get("step_index", line_idx)
                        was_truncated = bool(obj.get("truncated_fields"))
                        if was_truncated:
                            truncated_steps += 1
                            if full_line:
                                try:
                                    full_obj = json.loads(full_line.strip())
                                    if isinstance(full_obj, dict):
                                        obj = full_obj
                                except Exception:
                                    pass

                        ts_val = obj.get("created_at") or obj.get("timestamp") or obj.get("ts")
                        if isinstance(ts_val, str) and ts_val.strip():
                            clean_ts = ts_val.strip()
                            if first_ts is None:
                                first_ts = clean_ts
                            last_ts = clean_ts

                        # 原生 API usage 累計（相容 Claude Code / Codex .jsonl 之 usage 物件與頂層欄位）
                        usage_obj = obj.get("usage")
                        if not isinstance(usage_obj, dict) and isinstance(obj.get("message"), dict):
                            usage_obj = obj["message"].get("usage")
                        if not isinstance(usage_obj, dict) and isinstance(obj.get("payload"), dict):
                            usage_obj = obj["payload"].get("usage")
                        if isinstance(usage_obj, dict):
                            api_in_tokens += int(usage_obj.get("input_tokens") or usage_obj.get("prompt_tokens") or 0)
                            api_out_tokens += int(usage_obj.get("output_tokens") or usage_obj.get("completion_tokens") or 0)
                            api_cache_read += int(
                                usage_obj.get("cache_read_input_tokens") or usage_obj.get("cache_read_tokens") or 0
                            )
                            api_cache_create += int(
                                usage_obj.get("cache_creation_input_tokens") or usage_obj.get("cache_creation_tokens") or 0
                            )
                        else:
                            api_in_tokens += int(obj.get("input_tokens") or obj.get("prompt_tokens") or 0)
                            api_out_tokens += int(obj.get("output_tokens") or obj.get("completion_tokens") or 0)
                            api_cache_read += int(
                                obj.get("cache_read_input_tokens") or obj.get("cache_read_tokens") or 0
                            )
                            api_cache_create += int(
                                obj.get("cache_creation_input_tokens") or obj.get("cache_creation_tokens") or 0
                            )

                        # 相容 OpenAI Codex payload 封裝層
                        payload_obj = obj.get("payload") if isinstance(obj.get("payload"), dict) else {}
                        payload_type = str(payload_obj.get("type") or "").lower()

                        # 角色與內容 Token 分類統計
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
                            c_parts: List[str] = []
                            for blk in content_val:
                                if isinstance(blk, dict):
                                    c_parts.append(str(blk.get("text") or blk.get("input_text") or blk.get("output_text") or ""))
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
                                    if isinstance(blk, dict):
                                        b_type = blk.get("type")
                                        if b_type in ("text", "input_text", "output_text"):
                                            text_parts.append(str(blk.get("text") or blk.get("input_text") or blk.get("output_text") or ""))
                                        elif b_type == "tool_result":
                                            tr_c = blk.get("content")
                                            tr_str = json.dumps(tr_c, ensure_ascii=False) if isinstance(tr_c, (list, dict)) else str(tr_c or "")
                                            tr_tok = _estimate_tokens(tr_str)
                                            tok_tool_out += tr_tok
                                            step_inline_tool_out_tok += tr_tok
                                            if blk.get("is_error") is True:
                                                tool_result_errors.append(" ".join(tr_str.split())[:200])
                                content_str = "\n".join(text_parts)

                        content_tok = _estimate_tokens(content_str)
                        is_tool_output_step = False
                        if step_type == "GENERIC" or payload_type in ("function_call_output", "custom_tool_call_output"):
                            tok_tool_out += content_tok
                            is_tool_output_step = True
                        elif step_type == "USER_INPUT" or step_source == "USER_EXPLICIT" or msg_role == "user":
                            if step_inline_tool_out_tok > 0 and not content_str.strip():
                                is_tool_output_step = True
                                content_tok = step_inline_tool_out_tok
                            else:
                                user_turns += 1
                                tok_user += content_tok
                        elif step_type == "PLANNER_RESPONSE" or step_source == "MODEL" or msg_role == "assistant":
                            model_turns += 1
                            tok_model += content_tok
                        else:
                            tok_tool_out += content_tok
                            is_tool_output_step = True

                        # 若當前為工具輸出步驟，將輸出 Token 歸戶至前一步發起之工具與重度排行
                        status_str = str(obj.get("status") or payload_obj.get("status") or "").upper()
                        is_step_error = (
                            status_str in ("ERROR", "FAILED")
                            or obj.get("is_error") is True
                            or payload_obj.get("is_error") is True
                        )
                        has_gate_fail = False
                        if last_step_gate_cmds and content_str:
                            has_gate_fail = any(
                                marker in content_str
                                for marker in (
                                    "Exit Code: 1",
                                    "Exit Code: 2",
                                    "exit code 1",
                                    "[FAIL]",
                                    "[REJECTED]",
                                    "[TRIAGE:",
                                    " Validation FAILED",
                                    " Check FAILED",
                                )
                            )
                            if has_gate_fail:
                                transcript_cli_failed += 1
                                err_snip = " ".join(content_str.split())[:180]
                                for g_disp in last_step_gate_cmds:
                                    transcript_gate_bounces.append(FrictionSignal(
                                        signal_type="GATE_BOUNCE",
                                        severity="HIGH",
                                        tier_source="Tier 1",
                                        target=g_disp,
                                        summary=f"驗證關卡 '{g_disp}' 於終端輸出退件 (Step {step_no})：{err_snip}",
                                        details={"cmd": g_disp, "step": step_no},
                                    ))
                            last_step_gate_cmds = []

                        if is_tool_output_step and pending_tool_context is not None and content_tok > 0:
                            p_tools = pending_tool_context.get("tools", [])
                            if p_tools:
                                share_tok = max(1, int(round(content_tok / len(p_tools))))
                                for pt in p_tools:
                                    pt_name = pt["name"]
                                    ts_entry = tool_token_stats.setdefault(
                                        pt_name, {"calls": 0, "args_tokens": 0, "output_tokens": 0}
                                    )
                                    ts_entry["output_tokens"] += share_tok
                                    if pt.get("is_dup_read") and not is_step_error:
                                        wasted_dup_reads += share_tok
                                    if pt.get("is_blind_read") and not is_step_error:
                                        wasted_blind_reads += share_tok
                                    if pt.get("cmd_line"):
                                        heavy_cli_raw.append({
                                            "step": step_no,
                                            "command": pt["cmd_line"][:120],
                                            "tokens": pt["args_tok"] + share_tok,
                                            "output_tokens": share_tok,
                                            "is_error": bool(is_step_error or has_gate_fail),
                                        })
                                primary_pt = p_tools[0]
                                heavy_steps_raw.append({
                                    "step": step_no,
                                    "tool": primary_pt["name"],
                                    "target": primary_pt["target"][:90],
                                    "tokens": content_tok + pending_tool_context.get("total_args_tok", 0),
                                    "truncated": was_truncated,
                                })
                            if has_gate_fail and not is_step_error and not tool_result_errors:
                                wasted_failed_ops += (
                                    content_tok
                                    + pending_tool_context.get("total_args_tok", 0)
                                    + pending_tool_context.get("thinking_tok", 0)
                                )
                            pending_tool_context = None

                        # 提取 thinking（相容 Antigravity, Claude Code thinking block 與 Codex reasoning summary）
                        thinking_str = obj.get("thinking")
                        if not thinking_str and isinstance(obj.get("message"), dict):
                            msg_content = obj["message"].get("content")
                            if isinstance(msg_content, list):
                                for blk in msg_content:
                                    if isinstance(blk, dict) and blk.get("type") == "thinking":
                                        thinking_str = blk.get("thinking") or blk.get("text")
                                        break
                        if not thinking_str and (step_type == "REASONING" or payload_type == "reasoning"):
                            summary_list = payload_obj.get("summary") or obj.get("summary")
                            if isinstance(summary_list, list):
                                thinking_str = " ".join(
                                    str(s.get("text") or "") for s in summary_list if isinstance(s, dict)
                                )
                            elif isinstance(summary_list, str):
                                thinking_str = summary_list
                        step_thinking_tok = 0
                        if isinstance(thinking_str, str) and thinking_str.strip():
                            thinking_steps += 1
                            step_thinking_tok = _estimate_tokens(thinking_str)
                            tok_thinking += step_thinking_tok
                            last_thinking = " ".join(thinking_str.strip().split())[:300]

                        # 提取 tool_calls（相容 Antigravity tool_calls, Claude tool_use 與 Codex function_call）
                        tool_calls: List[Dict[str, Any]] = []
                        raw_tcs = obj.get("tool_calls")
                        if isinstance(raw_tcs, list):
                            for tc in raw_tcs:
                                if isinstance(tc, dict):
                                    raw_a = tc.get("args") or tc.get("arguments") or tc.get("input") or {}
                                    if isinstance(raw_a, str):
                                        try:
                                            raw_a = json.loads(raw_a)
                                        except Exception:
                                            raw_a = {"raw": raw_a}
                                    tool_calls.append({
                                        "name": str(tc.get("name") or tc.get("tool_name") or "").lower(),
                                        "args": raw_a if isinstance(raw_a, dict) else {},
                                    })
                        elif isinstance(obj.get("message"), dict):
                            msg_content = obj["message"].get("content")
                            if isinstance(msg_content, list):
                                for blk in msg_content:
                                    if isinstance(blk, dict) and blk.get("type") in ("tool_use", "function_call"):
                                        raw_a = blk.get("input") or blk.get("arguments") or {}
                                        if isinstance(raw_a, str):
                                            try:
                                                raw_a = json.loads(raw_a)
                                            except Exception:
                                                raw_a = {"raw": raw_a}
                                        tool_calls.append({
                                            "name": str(blk.get("name") or "").lower(),
                                            "args": raw_a if isinstance(raw_a, dict) else {},
                                        })
                        elif step_type in ("FUNCTION_CALL", "TOOL_CALL") or payload_type in ("function_call", "custom_tool_call"):
                            src_tc = payload_obj if payload_type in ("function_call", "custom_tool_call") else obj
                            raw_a = src_tc.get("arguments") or src_tc.get("input") or src_tc.get("args") or {}
                            if isinstance(raw_a, str):
                                try:
                                    raw_a = json.loads(raw_a)
                                except Exception:
                                    raw_a = {"raw": raw_a}
                            tool_calls.append({
                                "name": str(src_tc.get("name") or "").lower(),
                                "args": raw_a if isinstance(raw_a, dict) else {},
                            })

                        current_step_read_keys: List[str] = []
                        current_step_gate_cmds: List[str] = []
                        step_tools_meta: List[Dict[str, Any]] = []
                        step_total_args_tok = 0
                        for tc in tool_calls:
                            t_name = tc["name"].split(":")[-1] or "unknown"
                            total_tool_calls += 1
                            tool_dist[t_name] = tool_dist.get(t_name, 0) + 1
                            if "subagent" in t_name or t_name in ("task", "dispatch_agent"):
                                subagent_calls += 1

                            t_args = tc["args"] if isinstance(tc["args"], dict) else {}
                            try:
                                single_arg_tok = _estimate_tokens(json.dumps(t_args, ensure_ascii=False))
                            except Exception:
                                single_arg_tok = _estimate_tokens(str(t_args))
                            tok_tool_args += single_arg_tok
                            step_total_args_tok += single_arg_tok

                            ts_entry = tool_token_stats.setdefault(
                                t_name, {"calls": 0, "args_tokens": 0, "output_tokens": 0}
                            )
                            ts_entry["calls"] += 1
                            ts_entry["args_tokens"] += single_arg_tok

                            target_file = str(
                                t_args.get("Path")
                                or t_args.get("AbsolutePath")
                                or t_args.get("file_path")
                                or t_args.get("path")
                                or t_args.get("TargetFile")
                                or t_args.get("filename")
                                or ""
                            ).strip().strip('"').strip("'")

                            cmd_line = str(
                                t_args.get("CommandLine")
                                or t_args.get("command")
                                or t_args.get("cmd")
                                or ""
                            ).strip()
                            if "knowledge-db" in cmd_line and (
                                "search" in cmd_line or "callers" in cmd_line or "callees" in cmd_line or "impact" in cmd_line
                            ):
                                consecutive_source_reads = 0
                                has_recent_kdb_query = True

                            if "yscb.py" in cmd_line:
                                for m_cli in re.finditer(r"yscb\.py[\"\']?\s+([a-zA-Z0-9_-]+)(?:\s+([a-zA-Z0-9_-]+))?(?:\s+([a-zA-Z0-9_-]+))?", cmd_line):
                                    mod_tok = m_cli.group(1)
                                    sub1 = m_cli.group(2) or ""
                                    sub2 = m_cli.group(3) or ""
                                    transcript_cli_calls += 1
                                    transcript_cli_by_module[mod_tok] = transcript_cli_by_module.get(mod_tok, 0) + 1
                                    sub_pair = f"{sub1} {sub2}".strip()
                                    for g_mod, g_cmd in self.GATE_COMMANDS:
                                        if mod_tok == g_mod and (sub_pair.startswith(g_cmd) or sub1 == g_cmd):
                                            current_step_gate_cmds.append(f"{g_mod} {g_cmd}")

                            is_dup_read_call = False
                            is_blind_read_call = False
                            disp_target = Path(target_file).name if target_file else (cmd_line[:60] if cmd_line else t_name)

                            if t_name in self.EDIT_TOOL_NAMES and target_file:
                                total_edit_ops += 1
                                file_steps = edit_history.setdefault(target_file, [])
                                if not file_steps or file_steps[-1] != int(step_no):
                                    file_steps.append(int(step_no))
                                edit_tok_list = file_edit_step_tokens.setdefault(target_file, [])
                                if edit_tok_list and edit_tok_list[-1][0] == int(step_no):
                                    edit_tok_list[-1] = (int(step_no), edit_tok_list[-1][1] + single_arg_tok)
                                else:
                                    edit_tok_list.append((int(step_no), single_arg_tok))
                                for rk in list(read_counts.keys()):
                                    if rk.startswith(f"{target_file}:"):
                                        read_counts[rk] = 0
                                consecutive_source_reads = 0
                            elif t_name in self.READ_TOOL_NAMES and target_file:
                                total_read_ops += 1
                                unique_read_files.add(target_file)
                                lower_tf = target_file.lower().replace("\\", "/")
                                is_media = any(
                                    lower_tf.endswith(m_ext)
                                    for m_ext in (".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".svg", ".mp4", ".pdf")
                                )
                                is_overflow_scratch = (
                                    ("/steps/" in lower_tf and lower_tf.endswith("/output.txt"))
                                    or "tool-results" in lower_tf
                                    or lower_tf.endswith("/transcript_full.jsonl")
                                )
                                start_ln = (
                                    t_args.get("StartLine")
                                    or t_args.get("StartLineNumber")
                                    or t_args.get("offset")
                                    or ""
                                )
                                end_ln = (
                                    t_args.get("EndLine")
                                    or t_args.get("EndLineNumber")
                                    or t_args.get("limit")
                                    or ""
                                )
                                byte_off = t_args.get("ByteOffset")
                                byte_suffix = f"@{byte_off}" if byte_off is not None and str(byte_off) != "" else ""
                                read_key = f"{target_file}:{start_ln}-{end_ln}{byte_suffix}"
                                disp_target = f"{Path(target_file).name}:{start_ln}-{end_ln}{byte_suffix}"

                                if is_overflow_scratch:
                                    is_dup_read_call = True
                                    wasted_dup_reads += single_arg_tok
                                    signals.append(FrictionSignal(
                                        signal_type="CONTEXT_WASTE",
                                        severity="HIGH",
                                        tier_source="Tier 1",
                                        target=Path(target_file).name,
                                        summary=f"讀取宿主超長截斷暫存檔或會話歷史日誌 '{disp_target}' (Step {step_no})，造成巨量 JSON/歷史日誌污染 Context",
                                        details={"subtype": "JSON_SNIPPET_OVERFLOW", "step": step_no, "path": target_file},
                                    ))
                                elif not is_media:
                                    read_counts[read_key] = read_counts.get(read_key, 0) + 1
                                    current_step_read_keys.append(read_key)
                                    if read_counts[read_key] >= 2:
                                        is_dup_read_call = True
                                        wasted_dup_reads += single_arg_tok

                                is_targeted_range_read = False
                                if has_recent_kdb_query and start_ln != "" and end_ln != "":
                                    try:
                                        s_i = int(start_ln)
                                        e_i = int(end_ln)
                                        if 0 < (e_i - s_i + 1) <= 160:
                                            is_targeted_range_read = True
                                    except (ValueError, TypeError):
                                        pass

                                if (
                                    any(
                                        lower_tf.endswith(ext)
                                        for ext in (".py", ".ts", ".tsx", ".js", ".jsx", ".cs", ".java", ".kt", ".c", ".cpp", ".h", ".hpp", ".rs", ".go")
                                    )
                                    and not is_targeted_range_read
                                ):
                                    consecutive_source_reads += 1
                                    if target_file not in consecutive_read_files:
                                        consecutive_read_files.append(target_file)
                                    if consecutive_source_reads > max_consecutive_reads:
                                        max_consecutive_reads = consecutive_source_reads
                                    if consecutive_source_reads >= 4 and not is_dup_read_call:
                                        is_blind_read_call = True
                                        wasted_blind_reads += single_arg_tok

                            step_tools_meta.append({
                                "name": t_name,
                                "target": disp_target,
                                "cmd_line": cmd_line,
                                "args_tok": single_arg_tok,
                                "is_dup_read": is_dup_read_call,
                                "is_blind_read": is_blind_read_call,
                            })

                        if step_tools_meta:
                            pending_tool_context = {
                                "step": step_no,
                                "tools": step_tools_meta,
                                "total_args_tok": step_total_args_tok,
                                "thinking_tok": step_thinking_tok,
                            }
                            last_planner_thinking_tok = step_thinking_tok
                            last_planner_args_tok = step_total_args_tok
                            # 若單步參數自身極大（如 write_file/edit_file 大塊寫入），亦納入重度步驟候選
                            if step_total_args_tok >= 250:
                                p_t = step_tools_meta[0]
                                heavy_steps_raw.append({
                                    "step": step_no,
                                    "tool": p_t["name"],
                                    "target": p_t["target"][:90],
                                    "tokens": step_total_args_tok + step_thinking_tok + content_tok,
                                    "truncated": was_truncated,
                                })

                        # 檢查步驟錯誤狀態（相容 Antigravity status=="ERROR"、Claude tool_result is_error 與 Codex error）
                        if is_step_error or tool_result_errors:
                            wasted_failed_ops += content_tok + step_thinking_tok + step_total_args_tok
                            if is_tool_output_step:
                                wasted_failed_ops += last_planner_thinking_tok + last_planner_args_tok
                                last_planner_thinking_tok = 0
                                last_planner_args_tok = 0
                            # 若錯誤屬於讀檔失敗（如檔案不存在或權限拒絕），扣除剛才計入之 read_counts，避免盲猜路徑被雙重誤判為 CONTEXT_WASTE
                            raw_err_text = " ".join([
                                str(content_str or ""),
                                str(obj.get("error") or ""),
                                str(payload_obj.get("error") or ""),
                                *tool_result_errors,
                            ]).lower()
                            is_read_err = any(
                                k in raw_err_text
                                for k in (
                                    "does not exist",
                                    "no such file",
                                    "not found:",
                                    "file not found",
                                    "cannot read",
                                    "is a directory",
                                    "permission denied",
                                )
                            )
                            if is_read_err:
                                keys_to_rollback = last_step_read_keys if not current_step_read_keys else current_step_read_keys
                                for rk in keys_to_rollback:
                                    if read_counts.get(rk, 0) > 0:
                                        read_counts[rk] -= 1
                            last_step_read_keys = current_step_read_keys
                        else:
                            if tool_calls:
                                last_step_read_keys = current_step_read_keys
                            elif step_type == "GENERIC":
                                last_step_read_keys = []
                                last_planner_thinking_tok = 0
                                last_planner_args_tok = 0

                        if current_step_gate_cmds:
                            last_step_gate_cmds = current_step_gate_cmds

                        if is_step_error:
                            error_steps += 1
                            err_content = " ".join(str(content_str or obj.get("error") or payload_obj.get("error") or "").split())[:200]
                            signals.append(FrictionSignal(
                                signal_type="TOOL_MISS_AND_RETRY",
                                severity="MEDIUM",
                                tier_source="Tier 1",
                                target=f"Step {step_no}",
                                summary=f"工具調用返回 ERROR 狀態：{err_content or 'Unknown error'}",
                                details={"step": step_no},
                            ))
                            if last_thinking and len(thinking_excerpts) < 5:
                                thinking_excerpts.append({
                                    "step": step_no,
                                    "context": "TOOL_ERROR",
                                    "excerpt": last_thinking,
                                })
                        for tr_err in tool_result_errors:
                            error_steps += 1
                            signals.append(FrictionSignal(
                                signal_type="TOOL_MISS_AND_RETRY",
                                severity="MEDIUM",
                                tier_source="Tier 1",
                                target=f"Step {step_no}",
                                summary=f"工具調用返回 is_error=True：{tr_err or 'Tool execution error'}",
                                details={"step": step_no},
                            ))
                            if last_thinking and len(thinking_excerpts) < 5:
                                thinking_excerpts.append({
                                    "step": step_no,
                                    "context": "TOOL_ERROR",
                                    "excerpt": last_thinking,
                                })
                finally:
                    if full_f is not None:
                        full_f.close()
        except (OSError, PermissionError):
            return None, [], [], {}

        # 彙整 MULTI_EDIT_CHURN（豁免合規逐階段追加之日誌/總覽檔，並放寬雙階段生命週期文件閾值）
        exempt_churn_files = {"changelog.md", "revision_log.md", "umbrella_overview.md"}
        multi_stage_sop_files = {"p00_discuss.md", "p06_test_plan.md", "fast_track_plan.md"}
        for fpath, steps in edit_history.items():
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
                edit_toks = file_edit_step_tokens.get(fpath, [])
                if len(edit_toks) >= 2:
                    # 扣除首次建立與最後一次定稿後，中間返工覆寫步驟消耗之參數 Token（若僅 2 次非連續修改則計第 1 次被推翻之修補）
                    rework_slice = edit_toks[1:-1] if len(edit_toks) >= 3 else edit_toks[:-1]
                    wasted_edit_churn += sum(t for _, t in rework_slice)
                signals.append(FrictionSignal(
                    signal_type="MULTI_EDIT_CHURN",
                    severity="HIGH" if non_adjacent_edits >= 3 else "MEDIUM",
                    tier_source="Tier 1",
                    target=short_name,
                    summary=f"檔案 '{short_name}' 於單次對話中跨步驟修改 {len(steps)} 次 (橫跨 {non_adjacent_edits} 個非連續回合: Steps {steps})",
                    details={"file_path": fpath, "edit_count": len(steps), "steps": steps},
                ))

        # 彙整 CONTEXT_WASTE（同範圍重複讀取 >= 2 次，或未檢索連續翻讀 >= 4 個源碼檔）
        for read_key, count in read_counts.items():
            if count >= 2:
                fpath_part = read_key.split(":")[0]
                short_name = Path(fpath_part).name
                signals.append(FrictionSignal(
                    signal_type="CONTEXT_WASTE",
                    severity="MEDIUM",
                    tier_source="Tier 1",
                    target=short_name,
                    summary=f"相同檔案區段 '{read_key}' 被重複讀取 {count} 次",
                    details={"read_key": read_key, "count": count},
                ))

        if max_consecutive_reads >= 4:
            sample_files = ", ".join(Path(p).name for p in consecutive_read_files[:4])
            signals.append(FrictionSignal(
                signal_type="CONTEXT_WASTE",
                severity="MEDIUM",
                tier_source="Tier 1",
                target="source_exploration",
                summary=f"未呼叫 knowledge-db search 即連續原生翻讀 {max_consecutive_reads} 次源碼檔案 ({sample_files}...)",
                details={"max_consecutive_reads": max_consecutive_reads},
            ))

        # 計算檔案大小與 transcript_full.jsonl 完整 Token 補償（若已聯集讀取 has_full_sibling，則 tok_* 已是 100% 精確完整值）
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

        est_parsed = tok_user + tok_model + tok_thinking + tok_tool_args + tok_tool_out
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

        # 彙整有效 Token vs 無效（摩擦浪費）Token 與高耗能排行 (REV-05)
        raw_wasted = wasted_dup_reads + wasted_failed_ops + wasted_edit_churn + wasted_blind_reads
        total_for_eff = max(1, est_full)
        capped_wasted = min(est_full, raw_wasted)
        effective_tok = max(0, est_full - capped_wasted)
        eff_pct = round((effective_tok / float(total_for_eff)) * 100.0, 1) if est_full > 0 else 100.0
        waste_pct = round(100.0 - eff_pct, 1) if est_full > 0 else 0.0

        by_tool_list: List[Dict[str, Any]] = []
        for t_k, t_v in tool_token_stats.items():
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

        # 去重並排序單步重度操作 Top 5 與 CLI 指令重度排行 Top 5
        dedup_steps: Dict[int, Dict[str, Any]] = {}
        for hs in heavy_steps_raw:
            s_id = int(hs["step"])
            if s_id not in dedup_steps or hs["tokens"] > dedup_steps[s_id]["tokens"]:
                dedup_steps[s_id] = hs
        top_heavy_steps = sorted(dedup_steps.values(), key=lambda x: x["tokens"], reverse=True)[:5]
        top_heavy_cli = sorted(heavy_cli_raw, key=lambda x: x["tokens"], reverse=True)[:5]

        sorted_tools = dict(sorted(tool_dist.items(), key=lambda x: x[1], reverse=True)[:15])
        t1_stats: Dict[str, Any] = {
            "first_ts": first_ts,
            "last_ts": last_ts,
            "tokens": {
                "estimated_compact_tokens": est_compact,
                "estimated_full_tokens": est_full,
                "exact_full_parsed": has_full_sibling,
                "by_category": {
                    "user_input": tok_user,
                    "model_output": tok_model,
                    "thinking": tok_thinking,
                    "tool_call_args": tok_tool_args,
                    "tool_outputs": tok_tool_out + extra_truncated_tokens,
                },
                "reported_api_usage": {
                    "input_tokens": api_in_tokens,
                    "output_tokens": api_out_tokens,
                    "cache_read_tokens": api_cache_read,
                    "cache_creation_tokens": api_cache_create,
                    "total_tokens": api_in_tokens + api_out_tokens + api_cache_read + api_cache_create,
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
                    "duplicate_reads": wasted_dup_reads,
                    "failed_tool_steps": wasted_failed_ops,
                    "edit_churn_rework": wasted_edit_churn,
                    "unindexed_blind_reads": wasted_blind_reads,
                },
            },
            "top_consumers": {
                "by_tool": by_tool_list[:10],
                "heavy_steps": top_heavy_steps,
                "heavy_cli_commands": top_heavy_cli,
            },
            "steps_and_tools": {
                "total_steps": total_steps,
                "user_turns": user_turns,
                "model_turns": model_turns,
                "thinking_steps": thinking_steps,
                "truncated_steps": truncated_steps,
                "error_steps": error_steps,
                "total_tool_calls": total_tool_calls,
                "tool_distribution": sorted_tools,
                "subagent_calls": subagent_calls,
                "total_read_ops": total_read_ops,
                "unique_files_read": len(unique_read_files),
                "total_edit_ops": total_edit_ops,
                "unique_files_edited": len(edit_history),
            },
            "transcript_cli": {
                "cli_total_calls": transcript_cli_calls,
                "cli_failed_calls": transcript_cli_failed,
                "cli_by_module": transcript_cli_by_module,
                "gate_bounces": transcript_gate_bounces,
            },
        }

        return first_ts, signals, thinking_excerpts, t1_stats

    def _resolve_plan_for_audit(
        self, plan_name_or_subpath: Optional[str] = None
    ) -> Tuple[Optional[Path], str]:
        """
        定位待審計之計畫目錄 (EC-02)：
        1. 若指定 --plan：直接定位（若不存在則回傳 None 與錯誤訊息）。
        2. 若未指定且僅有 1 個活躍計畫：自動綁定。
        3. 若有多個活躍計畫：回傳 None 與多計畫提示（不中斷 CLI 分析）。
        4. 若有 0 個活躍計畫：自動檢查 workflow.archived:// 下最近 30 分鐘內剛歸檔之計畫。
        """
        scanner = PlanScanner(plans_dir=self.plans_dir)
        target_dir, err_msg = scanner.resolve_target_plan_dir(plan_name_or_subpath)
        if target_dir is not None:
            return target_dir, ""

        if plan_name_or_subpath:
            return None, err_msg or f"找不到指定的計畫目錄：'{plan_name_or_subpath}'。"

        # 若無活躍計畫，探測最近 30 分鐘內剛歸檔於 workflow.archived:// 之計畫
        if err_msg and "目前無進行中的開發計畫" in err_msg:
            recent_archived = self._find_recently_archived_plan(within_seconds=1800.0)
            if recent_archived is not None:
                return recent_archived, f"[Auto-Resolved Recently Archived Plan] {recent_archived.name}"
            return None, "目前無進行中計畫，僅執行 CLI 與對話軌跡分析。"

        return None, err_msg or ""

    def _find_recently_archived_plan(self, within_seconds: float = 1800.0) -> Optional[Path]:
        """搜尋 workflow.archived:// 下最近 within_seconds 秒內修改/歸檔之計畫目錄。"""
        if not self.archive_dir.is_dir():
            return None
        now = time.time()
        best_dir: Optional[Path] = None
        best_mtime: float = 0.0
        try:
            for root, dirs, _ in os.walk(self.archive_dir):
                for d in dirs:
                    if re.match(r"^\d{4}_\d{2}_\d{2}", d):
                        cand = Path(root) / d
                        mtime = cand.stat().st_mtime
                        if (now - mtime) <= within_seconds and mtime > best_mtime:
                            best_mtime = mtime
                            best_dir = cand
        except OSError:
            return None
        return best_dir

    def _parse_changelog_metadata(self, plan_dir: Path) -> Tuple[Optional[str], Dict[str, float], List[Dict[str, str]]]:
        """
        解析計畫 changelog.md：
        回傳 (最早紀錄時間字串, {階段代碼: 最早完成時間epoch}, 變更紀錄清單)
        """
        cl_path = plan_dir / "changelog.md"
        if not cl_path.is_file():
            return None, {}, []

        earliest_ts: Optional[str] = None
        earliest_epoch: Optional[float] = None
        phase_epochs: Dict[str, float] = {}
        entries: List[Dict[str, str]] = []

        try:
            for line in cl_path.read_text(encoding="utf-8", errors="replace").splitlines():
                s = line.strip()
                if not s.startswith("|") or "---" in s or "時間" in s:
                    continue
                parts = [p.strip() for p in s.strip("|").split("|")]
                if len(parts) < 3:
                    continue
                ts_str, l_type, summary = parts[0], parts[1].upper(), parts[2]
                ep = _parse_ts(ts_str)
                if ep is None:
                    continue
                if earliest_epoch is None or ep < earliest_epoch:
                    earliest_epoch = ep
                    earliest_ts = ts_str

                entries.append({"ts": ts_str, "type": l_type, "summary": summary})
                for p_code in ("P00", "P01", "P02", "P03", "P04", "P05", "P06", "P07"):
                    if p_code in summary:
                        if p_code not in phase_epochs or ep < phase_epochs[p_code]:
                            phase_epochs[p_code] = ep
        except Exception:
            pass

        return earliest_ts, phase_epochs, entries

    def audit_plan_mtimes(self, plan_dir: Path) -> List[FrictionSignal]:
        """
        掃描目標計畫目錄下 P00~P07 之 mtime 逆序修改，並對照 changelog.md 與 revision_log.md
        消歧「合規規格反向回寫 (VALIDATED_BACKPROP)」與「未申報之跨階段暗中偷改 (SILENT_BACKPATCH)」。
        """
        signals: List[FrictionSignal] = []
        if not plan_dir.is_dir():
            return signals

        _, phase_epochs, cl_entries = self._parse_changelog_metadata(plan_dir)
        has_revision_log = (plan_dir / "revision_log.md").is_file()
        has_backprop_entry = has_revision_log or any(
            e["type"] in ("REVISION", "DECISION")
            or any(k in e["summary"] for k in ("回寫", "修訂", "更新 P0", "同步 P0"))
            for e in cl_entries
        )

        phase_files: List[Tuple[int, str, Path, float]] = []
        for idx in range(8):
            p_code = f"P0{idx}"
            resolved = PlanStatusResolver.resolve_phase_file(plan_dir, p_code)
            if resolved and resolved.is_file():
                try:
                    phase_files.append((idx, p_code, resolved, resolved.stat().st_mtime))
                except OSError:
                    continue

        if len(phase_files) < 2:
            return signals

        # 比對前期規格檔 (P01~P03) 是否在後期階段 (P04~P07) 確立後又被修改（容許 5 秒內批次寫入誤差）
        later_phases = [(idx, code, f, mt) for idx, code, f, mt in phase_files if idx >= 4]
        if not later_phases:
            later_phases = [phase_files[-1]]

        earliest_later_idx, earliest_later_code, earliest_later_file, earliest_later_mtime = min(
            later_phases, key=lambda x: x[3]
        )
        baseline_time = phase_epochs.get(earliest_later_code, earliest_later_mtime)

        for idx, p_code, p_file, p_mtime in phase_files:
            if idx == 0 or idx >= earliest_later_idx:
                continue
            # 若前期檔案 mtime 晚於後期階段基準時間超過 5 秒
            if p_mtime > (baseline_time + 5.0) and p_mtime > (earliest_later_mtime + 5.0):
                delta_sec = int(p_mtime - min(baseline_time, earliest_later_mtime))
                if has_backprop_entry:
                    signals.append(FrictionSignal(
                        signal_type="VALIDATED_BACKPROP",
                        severity="INFO",
                        tier_source="Tier 2",
                        target=p_file.name,
                        summary=(
                            f"前期規格 '{p_file.name}' 於後期階段 '{earliest_later_file.name}' 後更新 (+{delta_sec}s)，"
                            f"且已於 changelog.md / revision_log.md 登記合規反向回寫"
                        ),
                        details={"phase": p_code, "delta_seconds": delta_sec},
                    ))
                else:
                    signals.append(FrictionSignal(
                        signal_type="SILENT_BACKPATCH",
                        severity="HIGH",
                        tier_source="Tier 2",
                        target=p_file.name,
                        summary=(
                            f"偵測到跨階段暗中偷改：'{p_file.name}' 的修改時間晚於後續階段 '{earliest_later_file.name}' "
                            f"(+{delta_sec}s)，且 changelog.md 無對應 REVISION/DECISION 回寫紀錄"
                        ),
                        details={"phase": p_code, "later_phase": earliest_later_code, "delta_seconds": delta_sec},
                    ))

        return signals

    def _analyze_telemetry(
        self,
        since_iso: Optional[str],
        since_minutes: Optional[float],
        limit: int,
        until_iso: Optional[str] = None,
    ) -> Tuple[Optional[str], int, List[FrictionSignal], Dict[str, Any]]:
        """
        讀取並切分 cache://core/telemetry.jsonl 當前 Session 時間窗，
        提取 GATE_BOUNCE 與 TOOL_MISS_AND_RETRY 摩擦訊號，並統計 CLI 遙測基礎指標。
        """
        from core.telemetry import read_telemetry_records

        empty_stats = {
            "cli_total_calls": 0,
            "cli_failed_calls": 0,
            "cli_total_duration_ms": 0,
            "cli_avg_duration_ms": 0,
            "cli_by_mode": {},
            "cli_by_module": {},
            "first_cli_ts": None,
            "last_cli_ts": None,
        }
        raw_records = read_telemetry_records(
            since_iso=since_iso,
            since_minutes=since_minutes,
            limit=max(limit * 4, 200),
            telemetry_path=self.telemetry_path,
        )
        if not raw_records:
            return since_iso, 0, [], empty_stats

        # 若指定了歷史對話結束時間上界 until_iso，過濾晚於 (until_epoch + 60s) 之紀錄
        if until_iso:
            until_ep = _parse_ts(until_iso)
            if until_ep is not None:
                filtered_by_until: List[Dict[str, Any]] = []
                for r in raw_records:
                    r_ep = r.get("epoch") or _parse_ts(str(r.get("ts", "")))
                    if isinstance(r_ep, (int, float)) and float(r_ep) <= (until_ep + 60.0):
                        filtered_by_until.append(r)
                raw_records = filtered_by_until
                if not raw_records:
                    return since_iso, 0, [], empty_stats

        # 若未指定 since_iso 與 since_minutes，自動以「間隔 > 30 分鐘 (1800s)」切分最新連續 Session
        session_records = raw_records
        inferred_start_ts = since_iso
        if since_iso is None and since_minutes is None and len(raw_records) > 1:
            cut_idx = 0
            for i in range(len(raw_records) - 1, 0, -1):
                cur_ep = raw_records[i].get("epoch") or _parse_ts(str(raw_records[i].get("ts", "")))
                prev_ep = raw_records[i - 1].get("epoch") or _parse_ts(str(raw_records[i - 1].get("ts", "")))
                if isinstance(cur_ep, (int, float)) and isinstance(prev_ep, (int, float)):
                    if (float(cur_ep) - float(prev_ep)) > 1800.0:
                        cut_idx = i
                        break
            session_records = raw_records[cut_idx:]
            inferred_start_ts = str(session_records[0].get("ts", ""))

        if limit > 0 and len(session_records) > limit:
            session_records = session_records[-limit:]

        signals: List[FrictionSignal] = []
        consecutive_searches = 0
        search_queries: List[str] = []

        failed_calls = 0
        total_dur_ms = 0
        by_mode: Dict[str, int] = {}
        by_module: Dict[str, int] = {}
        first_cli_ts: Optional[str] = None
        last_cli_ts: Optional[str] = None

        for rec in session_records:
            mod = str(rec.get("module", "") or "root")
            cmd = str(rec.get("cmd", ""))
            args = rec.get("args") if isinstance(rec.get("args"), list) else []
            rc = int(rec.get("exit_code", 0))
            mode = str(rec.get("mode", "local"))
            dur_ms = int(rec.get("duration_ms", 0) or 0)
            err_hint = str(rec.get("error_hint", ""))
            disp_cmd = f"{mod} {cmd}".strip()

            rec_ts = str(rec.get("ts", "")).strip()
            if rec_ts:
                if first_cli_ts is None:
                    first_cli_ts = rec_ts
                last_cli_ts = rec_ts

            total_dur_ms += max(0, dur_ms)
            by_mode[mode] = by_mode.get(mode, 0) + 1
            by_module[mod] = by_module.get(mod, 0) + 1

            # 統計連續 knowledge-db search 空轉
            if mod == "knowledge-db" and cmd == "search":
                consecutive_searches += 1
                if args:
                    search_queries.append(str(args[0]))
            else:
                if consecutive_searches >= 3:
                    q_sample = ", ".join(f"'{q}'" for q in search_queries[:3])
                    signals.append(FrictionSignal(
                        signal_type="TOOL_MISS_AND_RETRY",
                        severity="MEDIUM",
                        tier_source="Tier 2",
                        target="knowledge-db search",
                        summary=f"連續執行 {consecutive_searches} 次 knowledge-db search 檢索空轉 (查詢詞: {q_sample})",
                        details={"consecutive_count": consecutive_searches, "queries": search_queries},
                    ))
                consecutive_searches = 0
                search_queries = []

            if rc != 0:
                failed_calls += 1
                is_gate = (mod, cmd) in self.GATE_COMMANDS or any(
                    cmd.startswith(g_cmd) for g_mod, g_cmd in self.GATE_COMMANDS if mod == g_mod
                )
                if is_gate:
                    signals.append(FrictionSignal(
                        signal_type="GATE_BOUNCE",
                        severity="HIGH",
                        tier_source="Tier 2",
                        target=disp_cmd,
                        summary=f"驗證關卡 '{disp_cmd}' 退件 (exit_code={rc})：{err_hint or 'Check failed'}",
                        details={"cmd": disp_cmd, "args": args, "exit_code": rc, "error_hint": err_hint},
                    ))
                else:
                    signals.append(FrictionSignal(
                        signal_type="TOOL_MISS_AND_RETRY",
                        severity="MEDIUM",
                        tier_source="Tier 2",
                        target=disp_cmd,
                        summary=f"CLI 指令 '{disp_cmd}' 執行失敗 (mode={mode}, exit_code={rc})：{err_hint or 'Command failed'}",
                        details={"cmd": disp_cmd, "args": args, "exit_code": rc, "mode": mode, "error_hint": err_hint},
                    ))

        if consecutive_searches >= 3:
            q_sample = ", ".join(f"'{q}'" for q in search_queries[:3])
            signals.append(FrictionSignal(
                signal_type="TOOL_MISS_AND_RETRY",
                severity="MEDIUM",
                tier_source="Tier 2",
                target="knowledge-db search",
                summary=f"連續執行 {consecutive_searches} 次 knowledge-db search 檢索空轉 (查詢詞: {q_sample})",
                details={"consecutive_count": consecutive_searches, "queries": search_queries},
            ))

        total_cli = len(session_records)
        t2_stats: Dict[str, Any] = {
            "cli_total_calls": total_cli,
            "cli_failed_calls": failed_calls,
            "cli_total_duration_ms": total_dur_ms,
            "cli_avg_duration_ms": int(round(total_dur_ms / total_cli)) if total_cli > 0 else 0,
            "cli_by_mode": by_mode,
            "cli_by_module": by_module,
            "first_cli_ts": first_cli_ts,
            "last_cli_ts": last_cli_ts,
        }
        return inferred_start_ts, total_cli, signals, t2_stats

    def _get_git_changed_files(self) -> List[str]:
        """取得當前工作區 git status --short 異動檔案清單。"""
        try:
            proc = subprocess.run(
                ["git", "status", "--short"],
                cwd=str(self.project_root),
                capture_output=True,
                text=True,
                timeout=3.0,
                check=False,
            )
            if proc.returncode == 0 and proc.stdout:
                return [ln.strip() for ln in proc.stdout.splitlines() if ln.strip()][:50]
        except Exception:
            pass
        return []

    def list_sessions(
        self,
        include_all_workspaces: bool = False,
        include_subagents: bool = False,
        limit: int = 20,
    ) -> List[Dict[str, Any]]:
        """
        列出本機可抓取之歷史 Session 清單（預設僅列本工作區主對話，自動過濾 Subagent）。
        """
        targets = self._get_configured_release_targets()
        raw_cands = self._collect_candidate_jsonls(targets, max_files=max(limit * 4, 80))
        sessions: List[Dict[str, Any]] = []

        for target_name, fpath, mtime in raw_cands:
            beacon = self._inspect_candidate_beacon(fpath)
            if not include_all_workspaces and not beacon["matches_workspace"]:
                continue
            if not include_subagents and beacon["is_subagent"]:
                continue

            _, sigs, _, t1 = self._parse_transcript_file(fpath)
            st = t1.get("steps_and_tools", {})
            tok = t1.get("tokens", {})
            if not include_subagents and st.get("user_turns", 0) == 0 and beacon["is_subagent"]:
                continue

            # 擷取首筆使用者需求作為主題摘要
            topic = ""
            try:
                with open(fpath, "r", encoding="utf-8", errors="replace") as f:
                    for ln in f:
                        o = json.loads(ln)
                        if isinstance(o, dict) and (
                            o.get("type") == "USER_INPUT"
                            or o.get("source") == "USER_EXPLICIT"
                            or o.get("role") == "user"
                            or (isinstance(o.get("message"), dict) and o["message"].get("role") == "user")
                        ):
                            c = str(o.get("content") or "")
                            if not c and isinstance(o.get("message"), dict):
                                c = str(o["message"].get("content") or "")
                            if "<USER_REQUEST>" in c:
                                c = c.split("<USER_REQUEST>", 1)[1].split("</USER_REQUEST>", 1)[0].strip()
                            c = " ".join(c.split())
                            if c and c.lower() not in ("/context-init", "context-init"):
                                topic = c[:60]
                                break
            except Exception:
                pass

            conv_id = fpath.parent.parent.parent.name if ".system_generated" in str(fpath) else fpath.stem
            mtime_iso = datetime.fromtimestamp(mtime, tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
            sessions.append({
                "target": target_name,
                "session_id": conv_id,
                "path": str(fpath),
                "mtime_iso": mtime_iso,
                "workspace": beacon.get("detected_workspace") or (str(self.project_root) if beacon["matches_workspace"] else "external"),
                "matches_workspace": beacon["matches_workspace"],
                "is_subagent": beacon["is_subagent"],
                "total_steps": st.get("total_steps", 0),
                "user_turns": st.get("user_turns", 0),
                "total_tool_calls": st.get("total_tool_calls", 0),
                "estimated_full_tokens": tok.get("estimated_full_tokens", 0),
                "estimated_compact_tokens": tok.get("estimated_compact_tokens", 0),
                "signal_count": len(sigs),
                "topic": topic or "(No explicit user prompt)",
            })
            if limit > 0 and len(sessions) >= limit:
                break

        return sessions

    @staticmethod
    def render_session_list_text(sessions: List[Dict[str, Any]]) -> str:
        """渲染歷史 Session 清單為純文字表格。"""
        lines: List[str] = []
        lines.append("=" * 108)
        lines.append("YS-Codebase Historical Session Transcripts")
        lines.append("=" * 108)
        if not sessions:
            lines.append("No matching session transcripts found.")
            lines.append("=" * 108)
            return "\n".join(lines)

        lines.append(
            f"{'#':>2} | {'Session ID':<36} | {'Updated (UTC)':<19} | {'Steps(User)':<12} | {'Est. Tokens':<12} | {'Sigs':>4} | Topic"
        )
        lines.append("-" * 108)
        for idx, s in enumerate(sessions, 1):
            steps_str = f"{s['total_steps']}({s['user_turns']})"
            tok_str = f"~{s['estimated_full_tokens']:,}"
            lines.append(
                f"{idx:02d} | {s['session_id']:<36} | {s['mtime_iso']:<19} | {steps_str:<12} | {tok_str:<12} | {s['signal_count']:>4} | {s['topic']}"
            )
        lines.append("=" * 108)
        return "\n".join(lines)

    def analyze(
        self,
        plan_name_or_subpath: Optional[str] = None,
        transcript_path: Optional[str] = None,
        since_minutes: Optional[float] = None,
        limit: int = 50,
    ) -> SessionTraceReport:
        """
        執行三級漸進式軌跡提取與五大硬性摩擦訊號聚合。
        """
        # 1. Tier 1: 定錨並解析本地 .jsonl
        locked_transcript, candidates = self.locate_transcript(explicit_path=transcript_path)
        tier1_first_ts: Optional[str] = None
        tier1_last_ts: Optional[str] = None
        tier1_signals: List[FrictionSignal] = []
        thinking_excerpts: List[Dict[str, Any]] = []
        t1_stats: Dict[str, Any] = {}
        is_external_workspace = False

        if locked_transcript is not None:
            beacon_info = self._inspect_candidate_beacon(locked_transcript)
            if explicit_path := transcript_path:
                det_ws = beacon_info.get("detected_workspace", "")
                if det_ws and not beacon_info.get("matches_workspace", False):
                    is_external_workspace = True
            tier1_first_ts, tier1_signals, thinking_excerpts, t1_stats = self._parse_transcript_file(locked_transcript)
            tier1_last_ts = t1_stats.get("last_ts")

        # 2. 定位目標計畫（若顯式傳入外部工作區之歷史 Transcript 且未指定 --plan，不強綁本倉活躍計畫）
        plan_dir: Optional[Path] = None
        plan_note: str = ""
        plan_earliest_ts: Optional[str] = None
        plan_signals: List[FrictionSignal] = []

        if is_external_workspace and not plan_name_or_subpath:
            plan_note = f"[External Workspace Transcript: {beacon_info.get('detected_workspace')}] 略過本倉計畫與 Telemetry 綁定。"
        else:
            plan_dir, plan_note = self._resolve_plan_for_audit(plan_name_or_subpath)
            if plan_dir is not None:
                plan_earliest_ts, _, _ = self._parse_changelog_metadata(plan_dir)
                # 若顯式指定了歷史 Transcript，且該 Transcript 結束時間早於當前活躍計畫建立時間，不混入無關計畫 mtime
                if transcript_path and tier1_last_ts and plan_earliest_ts:
                    ep_t1_end = _parse_ts(str(tier1_last_ts))
                    ep_plan_start = _parse_ts(str(plan_earliest_ts))
                    if ep_t1_end is not None and ep_plan_start is not None and (ep_t1_end + 600.0) < ep_plan_start and not plan_name_or_subpath:
                        plan_note = f"[Historical Session Prior to Active Plan '{plan_dir.name}'] 僅對齊該時間窗之軌跡。"
                        plan_dir = None
                        plan_earliest_ts = None
                    else:
                        plan_signals = self.audit_plan_mtimes(plan_dir)
                else:
                    plan_signals = self.audit_plan_mtimes(plan_dir)

        # 3. Tier 2: 讀取並分析 core.telemetry（若屬外部工作區則跳過本倉 Telemetry；若為歷史對話則以 tier1_last_ts 為上界）
        effective_since_iso = tier1_first_ts or plan_earliest_ts
        if is_external_workspace:
            session_start_ts = effective_since_iso
            telem_count = 0
            tier2_signals = []
            t2_stats = {
                "cli_total_calls": 0,
                "cli_failed_calls": 0,
                "cli_total_duration_ms": 0,
                "cli_avg_duration_ms": 0,
                "cli_by_mode": {},
                "cli_by_module": {},
                "first_cli_ts": None,
                "last_cli_ts": None,
            }
        else:
            session_start_ts, telem_count, tier2_signals, t2_stats = self._analyze_telemetry(
                since_iso=effective_since_iso if since_minutes is None else None,
                since_minutes=since_minutes,
                limit=limit,
                until_iso=tier1_last_ts if since_minutes is None else None,
            )

        # 若無本倉 Telemetry 紀錄（如外部工作區或 Telemetry 啟用前之歷史對話），自動由 Transcript 終端指令回填 CLI 呼叫與 GATE_BOUNCE
        t1_cli = t1_stats.get("transcript_cli", {})
        if telem_count == 0 and t1_cli.get("cli_total_calls", 0) > 0:
            inferred_calls = int(t1_cli["cli_total_calls"])
            t2_stats["cli_total_calls"] = inferred_calls
            t2_stats["cli_failed_calls"] = int(t1_cli.get("cli_failed_calls", 0))
            t2_stats["cli_by_mode"] = {"transcript_inferred": inferred_calls}
            t2_stats["cli_by_module"] = dict(t1_cli.get("cli_by_module", {}))
            tier2_signals.extend(t1_cli.get("gate_bounces", []))

        all_signals = tier1_signals + tier2_signals + plan_signals
        git_files = self._get_git_changed_files()

        # 彙整會話基礎常數統計 (session_stats)
        start_ts_for_dur = t1_stats.get("first_ts") or t2_stats.get("first_cli_ts") or effective_since_iso
        end_ts_for_dur = t1_stats.get("last_ts") or t2_stats.get("last_cli_ts")
        dur_sec = 0.0
        if start_ts_for_dur and end_ts_for_dur:
            ep_s = _parse_ts(str(start_ts_for_dur))
            ep_e = _parse_ts(str(end_ts_for_dur))
            if ep_s is not None and ep_e is not None and ep_e >= ep_s:
                dur_sec = round(ep_e - ep_s, 1)

        default_tokens = {
            "estimated_compact_tokens": 0,
            "estimated_full_tokens": 0,
            "by_category": {
                "user_input": 0,
                "model_output": 0,
                "thinking": 0,
                "tool_call_args": 0,
                "tool_outputs": 0,
            },
            "reported_api_usage": {
                "input_tokens": 0,
                "output_tokens": 0,
                "cache_read_tokens": 0,
                "cache_creation_tokens": 0,
                "total_tokens": 0,
            },
            "transcript_compact_kb": 0.0,
            "transcript_full_kb": 0.0,
        }
        default_steps = {
            "total_steps": 0,
            "user_turns": 0,
            "model_turns": 0,
            "thinking_steps": 0,
            "truncated_steps": 0,
            "error_steps": 0,
            "total_tool_calls": 0,
            "tool_distribution": {},
            "subagent_calls": 0,
            "total_read_ops": 0,
            "unique_files_read": 0,
            "total_edit_ops": 0,
            "unique_files_edited": 0,
        }
        default_efficiency = {
            "total_tokens": 0,
            "effective_tokens": 0,
            "wasted_tokens": 0,
            "efficiency_pct": 100.0,
            "waste_pct": 0.0,
            "wasted_breakdown": {
                "duplicate_reads": 0,
                "failed_tool_steps": 0,
                "edit_churn_rework": 0,
                "unindexed_blind_reads": 0,
            },
        }
        default_consumers = {
            "by_tool": [],
            "heavy_steps": [],
            "heavy_cli_commands": [],
        }
        session_stats: Dict[str, Any] = {
            "tokens": t1_stats.get("tokens", default_tokens),
            "token_efficiency": t1_stats.get("token_efficiency", default_efficiency),
            "top_consumers": t1_stats.get("top_consumers", default_consumers),
            "steps_and_tools": t1_stats.get("steps_and_tools", default_steps),
            "time_and_cli": {
                "session_start_ts": start_ts_for_dur,
                "session_end_ts": end_ts_for_dur,
                "session_duration_sec": dur_sec,
                "session_duration_human": _format_duration(dur_sec),
                "cli_total_calls": t2_stats.get("cli_total_calls", 0),
                "cli_failed_calls": t2_stats.get("cli_failed_calls", 0),
                "cli_total_duration_ms": t2_stats.get("cli_total_duration_ms", 0),
                "cli_avg_duration_ms": t2_stats.get("cli_avg_duration_ms", 0),
                "cli_by_mode": t2_stats.get("cli_by_mode", {}),
                "cli_by_module": t2_stats.get("cli_by_module", {}),
            },
        }

        # 4. 判定 Active Tier 與 Tier 3 Fallback
        if locked_transcript is not None:
            active_tier = "Tier 1+2 (Transcript + Core Telemetry)"
            fallback_checklist: List[str] = []
        elif telem_count > 0 or plan_signals:
            active_tier = "Tier 2 (Core Telemetry & Plan mtime)"
            fallback_checklist = []
        else:
            active_tier = "Tier 3 (In-Context Fallback)"
            fallback_checklist = [
                "盤點本輪對話中是否有同一檔案被原生編輯/寫入工具修改 >= 2 次（MULTI_EDIT_CHURN）？",
                "盤點本輪對話中是否有 CLI 報錯、參數猜錯或連續搜尋 >= 3 次才命中目標（TOOL_MISS_AND_RETRY）？",
                "盤點是否在後期階段回頭修改了前期 P01~P04 規格而未登記於 changelog.md（SILENT_BACKPATCH）？",
                "盤點是否曾被 plan verify、dev check 或 Reviewer 退件重修（GATE_BOUNCE）？",
                "盤點是否重複讀取相同檔案、讀取超長截斷暫存檔，或未先執行 knowledge-db 定位即盲讀多檔（CONTEXT_WASTE）？",
            ]

        return SessionTraceReport(
            active_tier=active_tier,
            transcript_path=str(locked_transcript) if locked_transcript else None,
            transcript_candidates=candidates,
            target_plan=plan_dir.name if plan_dir else None,
            plan_resolution_note=plan_note,
            session_start_ts=session_start_ts or effective_since_iso,
            telemetry_count=telem_count,
            git_changed_files=git_files,
            session_stats=session_stats,
            signals=all_signals,
            thinking_excerpts=thinking_excerpts,
            fallback_checklist=fallback_checklist,
        )

