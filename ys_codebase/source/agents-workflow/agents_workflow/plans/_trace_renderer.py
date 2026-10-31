"""
agents_workflow.plans._trace_renderer — Session Trace 摩擦訊號資料模型、報告結構與純文字渲染器。
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


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
