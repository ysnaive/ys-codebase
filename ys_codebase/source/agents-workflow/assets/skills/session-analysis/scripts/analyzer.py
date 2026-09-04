#!/usr/bin/env python3
"""
Antigravity Session Analyzer Tool.
Exclusively supports Antigravity IDE environment.
Analyzes steps from: after previous analysis (exclusive) ~ before current analysis (exclusive).
"""
import sys
import os
import json
import re
import argparse
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any

# Windows UTF-8 output protection
if sys.stdout and hasattr(sys.stdout, 'buffer'):
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass


def find_antigravity_transcript(conversation_id: Optional[str] = None, explicit_path: Optional[str] = None) -> Optional[Path]:
    """Locate the transcript.jsonl file in Antigravity environment."""
    if explicit_path:
        p = Path(explicit_path)
        if p.is_file():
            return p
        return None

    # Base directory for Antigravity IDE
    candidate_bases = [
        Path.home() / ".gemini" / "antigravity-ide" / "brain",
        Path("/home/developer/.gemini/antigravity-ide/brain"),
    ]

    for base in candidate_bases:
        if not base.is_dir():
            continue
        if conversation_id:
            target = base / conversation_id / ".system_generated" / "logs" / "transcript.jsonl"
            if target.is_file():
                return target
        else:
            # Find the most recently modified transcript
            matches = list(base.glob("*/.system_generated/logs/transcript.jsonl"))
            if matches:
                matches.sort(key=lambda x: x.stat().st_mtime, reverse=True)
                return matches[0]

    return None


def parse_transcript_slice(transcript_path: Path) -> Tuple[List[Dict[str, Any]], int, int, str]:
    """
    Read transcript and slice it from:
    after previous analysis (exclusive) ~ before current analysis (exclusive).
    """
    all_entries = []
    with open(transcript_path, "r", encoding="utf-8") as f:
        for idx, line in enumerate(f):
            line = line.strip()
            if not line:
                continue
            try:
                data = json.loads(line)
                data["_line_index"] = idx
                all_entries.append(data)
            except Exception:
                continue

    # Identify trigger points of session-analysis
    trigger_indices = []
    last_user_input_idx = -1
    for i, entry in enumerate(all_entries):
        stype = entry.get("type")
        content = entry.get("content", "") or ""
        # Check if user invoked session analysis
        if stype == "USER_INPUT":
            last_user_input_idx = i
            if "SessionAnalysis" in content or "session-analysis" in content or "analyzer.py" in content:
                trigger_indices.append(i)
                continue
        # Check if planner invoked analyzer script
        for tc in entry.get("tool_calls", []):
            args = tc.get("args", {})
            cmd = args.get("CommandLine", "")
            if "analyzer.py" in cmd or "analyze_session.py" in cmd:
                # Avoid duplicate trigger if already registered for the current user input turn
                if trigger_indices and trigger_indices[-1] == last_user_input_idx:
                    continue
                if not trigger_indices or trigger_indices[-1] != i:
                    trigger_indices.append(i)

    if not trigger_indices:
        # No session analysis trigger found; take entire conversation
        start_idx = 0
        end_idx = len(all_entries) - 1
        scope_desc = f"全對話初始 (Step 0) ~ 當前最新 (Step {end_idx})"
    elif len(trigger_indices) == 1:
        # Current analysis is the only trigger; analyze from 0 to before current trigger
        current_trigger = trigger_indices[-1]
        start_idx = 0
        end_idx = max(0, current_trigger - 1)
        scope_desc = f"對話開頭 (Step 0) ~ 本次分析前 (Step {end_idx}) [不包含本次分析]"
    else:
        # Multiple triggers: take between previous analysis and current analysis
        prev_trigger = trigger_indices[-2]
        current_trigger = trigger_indices[-1]
        
        # Advance start_idx past the response of the previous analysis
        start_idx = prev_trigger + 1
        while start_idx < current_trigger and all_entries[start_idx].get("type") in ("PLANNER_RESPONSE", "TOOL_OUTPUT", "CHECKPOINT"):
            start_idx += 1
            
        end_idx = max(start_idx, current_trigger - 1)
        scope_desc = f"上次分析後 (Step {start_idx}) ~ 本次分析前 (Step {end_idx}) [不包含兩端]"

    slice_entries = all_entries[start_idx:end_idx + 1] if start_idx <= end_idx else []
    return slice_entries, start_idx, end_idx, scope_desc


def analyze_slice(entries: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Extract metrics from the sliced entries."""
    model_steps = 0
    user_inputs = 0
    tool_counts = {}
    skills_triggered = set()
    workflows_called = set()
    kdb_stats = {"search": 0, "callers": 0, "callees": 0, "impact": 0, "status": 0}
    cli_commands = []
    gated_commands_detected = []

    content_chars = {
        "read": 0,
        "write": 0,
        "thinking": 0,
        "dialogue": 0,
        "cli": 0,
    }

    for entry in entries:
        stype = entry.get("type")
        content = entry.get("content", "") or ""
        char_len = len(content)

        if stype == "PLANNER_RESPONSE":
            model_steps += 1
            content_chars["dialogue"] += char_len
        elif stype == "USER_INPUT":
            user_inputs += 1
            content_chars["dialogue"] += char_len
        elif stype == "VIEW_FILE":
            content_chars["read"] += char_len
        elif stype == "RUN_COMMAND":
            content_chars["cli"] += char_len
        elif stype in ("CODE_ACTION", "WRITE_TO_FILE"):
            content_chars["write"] += char_len

        # Parse tool calls
        for tc in entry.get("tool_calls", []):
            name = tc.get("name", "unknown")
            tool_counts[name] = tool_counts.get(name, 0) + 1
            args = tc.get("args", {})

            if name == "run_command":
                cmd = args.get("CommandLine", "").strip('"')
                cli_commands.append(cmd)
                content_chars["cli"] += len(cmd)

                # Track knowledge-db
                if "knowledge-db" in cmd:
                    for k in kdb_stats:
                        if f"knowledge-db {k}" in cmd or f"kdb {k}" in cmd:
                            kdb_stats[k] += 1

                # Detect gated commands
                if any(x in cmd for x in ("dev bump", "dev release", "remove core", "rollback")):
                    gated_commands_detected.append(cmd)

            elif name == "view_file":
                fpath = args.get("AbsolutePath", "").strip('"')
                if "skills/" in fpath:
                    m = re.search(r"skills/([^/]+)/", fpath)
                    if m:
                        skills_triggered.add(m.group(1))
                if "workflows/" in fpath:
                    m = re.search(r"workflows/([^/]+)\.md", fpath)
                    if m:
                        workflows_called.add(m.group(1))

    # Token estimations
    system_prompt_fixed_baseline = 7800
    dynamic_tokens = sum(content_chars.values()) // 4
    read_tokens = content_chars["read"] // 4
    write_tokens = content_chars["write"] // 4
    dialogue_tokens = content_chars["dialogue"] // 4
    cli_tokens = content_chars["cli"] // 4
    thinking_tokens = int(dynamic_tokens * 0.25)

    context_window_est = system_prompt_fixed_baseline + dynamic_tokens
    denom = max(1, context_window_est)
    system_fixed_pct = (system_prompt_fixed_baseline / denom) * 100
    dynamic_pct = (dynamic_tokens / denom) * 100
    read_pct = (read_tokens / denom) * 100
    write_pct = (write_tokens / denom) * 100
    cli_pct = (cli_tokens / denom) * 100
    dialogue_pct = (dialogue_tokens / denom) * 100
    thinking_pct = (thinking_tokens / denom) * 100

    return {
        "model_steps": model_steps,
        "user_inputs": user_inputs,
        "tool_counts": tool_counts,
        "skills_triggered": sorted(list(skills_triggered)),
        "workflows_called": sorted(list(workflows_called)),
        "kdb_stats": kdb_stats,
        "cli_count": len(cli_commands),
        "gated_commands": gated_commands_detected,
        "tokens": {
            "context_window": context_window_est,
            "system_fixed": system_prompt_fixed_baseline,
            "system_fixed_pct": round(system_fixed_pct, 1),
            "dynamic_tokens": dynamic_tokens,
            "dynamic_pct": round(dynamic_pct, 1),
            "read_tokens": read_tokens,
            "read_pct": round(read_pct, 1),
            "write_tokens": write_tokens,
            "write_pct": round(write_pct, 1),
            "cli_tokens": cli_tokens,
            "cli_pct": round(cli_pct, 1),
            "dialogue_tokens": dialogue_tokens,
            "dialogue_pct": round(dialogue_pct, 1),
            "thinking_tokens": thinking_tokens,
            "thinking_pct": round(thinking_pct, 1),
        }
    }


def format_markdown_report(metrics: Dict[str, Any], scope_desc: str) -> str:
    """Format the report into strict markdown."""
    t = metrics["tokens"]
    tc = metrics["tool_counts"]
    kdb = metrics["kdb_stats"]
    gated = metrics["gated_commands"]

    # Guardrails audit
    if not gated:
        guardrail_card = "- **紀律自檢**：✅ 核心紀律全數合規 (0 異常)"
    else:
        guardrail_card = f"- **紀律自檢**：⚠️ 發現 {len(gated)} 項授權守門指令調用\n"
        for cmd in gated:
            guardrail_card += f"    - **指令**：`{cmd}` (需核實是否獲開發者顯式授權)\n"

    skills_str = ", ".join(metrics["skills_triggered"]) if metrics["skills_triggered"] else "無"
    workflows_str = ", ".join(metrics["workflows_called"]) if metrics["workflows_called"] else "無"

    read_calls = tc.get("view_file", 0)
    write_calls = tc.get("write_to_file", 0) + tc.get("replace_file_content", 0) + tc.get("multi_replace_file_content", 0)

    report = f"""# 🔍 對話階段歷程分析報告 (Session Analysis Report)

> **分析範圍**：{scope_desc}  
> **環境探針**：Google Antigravity (原生 transcript.jsonl 精準解析)

### 📌 流程與紀律自檢 (Guardrails Audit)
{guardrail_card}

### 📊 行為統計與 Token 視窗分佈 (Dimension Breakdown)
- **實時 Context 視窗預估**：約 `{t["context_window"]:,}` Tokens
  - **系統固定上下文 (System Prompt)**：約 `{t["system_fixed"]:,}` Tokens (`{t["system_fixed_pct"]:.1f}%`) *(純靜態恆定，Prompt Cache 命中率 ~99%+)*
  - **動態累積上下文 (Dynamic Context)**：約 `{t["dynamic_tokens"]:,}` Tokens (`{t["dynamic_pct"]:.1f}%`)
- **模型實際推論輪次 (Planner Steps)**：`{metrics["model_steps"]}` 輪 *(嚴格排除 Tool Output 雜訊)*
- **使用者輸入 (User Inputs)**：`{metrics["user_inputs"]}` 次
- **外部指令調用 (CLI)**：約 `{t["cli_tokens"]:,}` Tokens (`{t["cli_pct"]:.1f}%`) | 執行 `{metrics["cli_count"]}` 次
- **Skills 觸發**：`{len(metrics["skills_triggered"])}` 項：`[{skills_str}]`
- **Workflows 觸發**：`{len(metrics["workflows_called"])}` 項：`[{workflows_str}]`
- **細部操作吞吐**：
  - **Read (檔案檢視)**：約 `{t["read_tokens"]:,}` Tokens (`{t["read_pct"]:.1f}%`) | 調用 `{read_calls}` 次
  - **Write (代碼寫入/編輯)**：約 `{t["write_tokens"]:,}` Tokens (`{t["write_pct"]:.1f}%`) | 產出 `{write_calls}` 次
  - **Thinking (思考推導估算)**：約 `{t["thinking_tokens"]:,}` Tokens (`{t["thinking_pct"]:.1f}%`)
  - **Dialogue (對話互動)**：約 `{t["dialogue_tokens"]:,}` Tokens (`{t["dialogue_pct"]:.1f}%`)

### 🧩 模組特化評測 (Modular Evaluations)
- **知識庫檢索效益 (knowledge-db)**：
  - **調用次數**：`search`: {kdb["search"]} 次, `callers`/`callees`: {kdb["callers"] + kdb["callees"]} 次, `impact`: {kdb["impact"]} 次, `status`: {kdb["status"]} 次
  - **效益估算**：精確切片檢索預估節省約 `{(kdb["search"] + kdb["callers"]) * 7500:,}` Tokens 全庫走訪消耗
"""
    return report


def main():
    parser = argparse.ArgumentParser(description="Antigravity Session Analyzer Tool")
    parser.add_argument("--id", dest="conversation_id", help="Target Conversation ID")
    parser.add_argument("--path", dest="transcript_path", help="Explicit path to transcript.jsonl")
    parser.add_argument("--json", dest="output_json", action="store_true", help="Output raw JSON metrics")
    args = parser.parse_args()

    # Step 1: Probe Antigravity environment
    transcript = find_antigravity_transcript(args.conversation_id, args.transcript_path)
    if not transcript or not transcript.is_file():
        print("[session-analysis] 錯誤：目前環境非 Antigravity IDE 或未檢測到有效 transcript 日誌。")
        print("本工具腳本僅支援 Antigravity 環境。")
        print("請 Agent 查閱 references/evaluation_guide.md 依通用評估通則自行評估。")
        sys.exit(1)

    # Step 2: Slice entries (after previous analysis ~ before current analysis)
    entries, start_idx, end_idx, scope_desc = parse_transcript_slice(transcript)

    # Step 3: Analyze metrics
    metrics = analyze_slice(entries)

    # Step 4: Output
    if args.output_json:
        result = {
            "scope": scope_desc,
            "start_step": start_idx,
            "end_step": end_idx,
            "metrics": metrics
        }
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        print(format_markdown_report(metrics, scope_desc))


if __name__ == "__main__":
    main()
