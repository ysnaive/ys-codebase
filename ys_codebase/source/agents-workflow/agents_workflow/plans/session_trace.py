"""
Session Trace & Friction Signal Extraction Engine (3-Tier Progressive Fallback).
100% Python Standard Library.
"""

import json
import os
import re
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

from ._trace_parser import (
    EDIT_TOOL_NAMES as _EDIT_TOOL_NAMES,
    GATE_COMMANDS as _GATE_COMMANDS,
    READ_TOOL_NAMES as _READ_TOOL_NAMES,
    _estimate_tokens,
    _parse_ts,
    parse_transcript_file,
)
from ._trace_renderer import (
    FrictionSignal,
    SessionTraceReport,
    _format_duration,
)
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


class SessionTraceEngine:
    """
    三級漸進式軌跡提取與五大硬性摩擦訊號偵測引擎：
    - Tier 1: 多宿主 release_targets 本地 .jsonl 三層信標定錨與思考鏈提取
    - Tier 2: core.telemetry (cache://core/telemetry.jsonl) 時間窗切片 + 計畫 mtime 回寫消歧
    - Tier 3: In-Context 結構化逆向審訊保底
    """

    EDIT_TOOL_NAMES = _EDIT_TOOL_NAMES
    READ_TOOL_NAMES = _READ_TOOL_NAMES
    GATE_COMMANDS = _GATE_COMMANDS

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
            cfg_file = _resolve_uri_safe(
                "config://agents-workflow/config.project.json",
                "ys_codebase/config/agents-workflow/config.project.json",
            )
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
        1. 是否精確匹配當前 project_root 工作區指紋
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

            tail_last_chunk = (tail_text if tail_text else head_text)[-16384:]
            if "session-trace" in tail_last_chunk or "/session-audit" in tail_last_chunk:
                info["has_self_beacon"] = True

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
        """三層信標定錨。"""
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

        if beacon_matched:
            return beacon_matched[0], []
        if len(workspace_matched) == 1:
            return Path(workspace_matched[0]["path"]), []
        if len(workspace_matched) > 1:
            return None, workspace_matched[:5]
        return None, []

    def _resolve_plan_for_audit(
        self, plan_name_or_subpath: Optional[str] = None
    ) -> Tuple[Optional[Path], str]:
        """定位待審計之計畫目錄 (EC-02)。"""
        scanner = PlanScanner(plans_dir=self.plans_dir)
        target_dir, err_msg = scanner.resolve_target_plan_dir(plan_name_or_subpath)
        if target_dir is not None:
            return target_dir, ""

        if plan_name_or_subpath:
            return None, err_msg or f"找不到指定的計畫目錄：'{plan_name_or_subpath}'。"

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
        """解析計畫 changelog.md：回傳 (最早紀錄時間字串, {階段代碼: 最早完成時間epoch}, 變更紀錄清單)。"""
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
        """掃描目標計畫目錄下 P00~P07 之 mtime 逆序修改，消歧 VALIDATED_BACKPROP 與 SILENT_BACKPATCH。"""
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
        """讀取並切分 cache://core/telemetry.jsonl 當前 Session 時間窗。"""
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

        if until_iso:
            until_ep = _parse_ts(until_iso)
            if until_ep is not None:
                raw_records = [
                    r for r in raw_records
                    if isinstance(r.get("epoch") or _parse_ts(str(r.get("ts", ""))), (int, float))
                    and float(r.get("epoch") or _parse_ts(str(r.get("ts", "")))) <= (until_ep + 60.0)
                ]
                if not raw_records:
                    return since_iso, 0, [], empty_stats

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
        """列出本機可抓取之歷史 Session 清單（預設僅列本工作區主對話，自動過濾 Subagent）。"""
        targets = self._get_configured_release_targets()
        raw_cands = self._collect_candidate_jsonls(targets, max_files=max(limit * 4, 80))
        sessions: List[Dict[str, Any]] = []

        for target_name, fpath, mtime in raw_cands:
            beacon = self._inspect_candidate_beacon(fpath)
            if not include_all_workspaces and not beacon["matches_workspace"]:
                continue
            if not include_subagents and beacon["is_subagent"]:
                continue

            _, sigs, _, t1 = parse_transcript_file(fpath)
            st = t1.get("steps_and_tools", {})
            tok = t1.get("tokens", {})
            if not include_subagents and st.get("user_turns", 0) == 0 and beacon["is_subagent"]:
                continue

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

    def analyze(
        self,
        plan_name_or_subpath: Optional[str] = None,
        transcript_path: Optional[str] = None,
        since_minutes: Optional[float] = None,
        limit: int = 50,
    ) -> SessionTraceReport:
        """執行三級漸進式軌跡提取與五大硬性摩擦訊號聚合。"""
        locked_transcript, candidates = self.locate_transcript(explicit_path=transcript_path)
        tier1_first_ts: Optional[str] = None
        tier1_last_ts: Optional[str] = None
        tier1_signals: List[FrictionSignal] = []
        thinking_excerpts: List[Dict[str, Any]] = []
        t1_stats: Dict[str, Any] = {}
        is_external_workspace = False

        if locked_transcript is not None:
            beacon_info = self._inspect_candidate_beacon(locked_transcript)
            if transcript_path:
                det_ws = beacon_info.get("detected_workspace", "")
                if det_ws and not beacon_info.get("matches_workspace", False):
                    is_external_workspace = True
            tier1_first_ts, tier1_signals, thinking_excerpts, t1_stats = parse_transcript_file(locked_transcript)
            tier1_last_ts = t1_stats.get("last_ts")

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

        effective_since_iso = tier1_first_ts or plan_earliest_ts
        if is_external_workspace:
            session_start_ts = effective_since_iso
            telem_count = 0
            tier2_signals: List[FrictionSignal] = []
            t2_stats: Dict[str, Any] = {
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
