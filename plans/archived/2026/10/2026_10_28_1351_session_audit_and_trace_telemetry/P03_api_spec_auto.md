# API 與介面規格書 (API & Interface Specification)

> 功能名稱：Session 隱形摩擦自檢技能與三級軌跡提取機制 (`session_audit_and_trace_telemetry`)  
> 建立日期：2026-10-28  
> 所屬主計畫：獨立計畫 (Standalone)  
> 狀態：Confirmed  
> 模型：Gemini 4 Argon (Low)  

> 模板版本：v1.2  

---

## 1. 介面契約清單 (Interface Inventory)

| 介面 / 類別名稱 | 所屬檔案路徑 | 存取層級 | 核心職責 |
| :--- | :--- | :---: | :--- |
| `resolve_telemetry_path` | `core/telemetry.py` | Public | 解析 `cache://core/telemetry.jsonl` 實體路徑（支援 `YSCB_TELEMETRY_PATH` 測試覆寫）。 |
| `record_cli_event` | `core/telemetry.py` | Public | 寫入單筆 CLI 執行紀錄並執行 512KB / 1,500 筆自動滾動截斷。 |
| `read_telemetry_records` | `core/telemetry.py` | Public | 依時間窗與條件讀取解析 `telemetry.jsonl` 紀錄清單。 |
| `FrictionSignal` | `agents_workflow/plans/session_trace.py` | Public | 表示單筆硬性摩擦訊號之資料結構（含類別、嚴重度、來源層級、證據與時間）。 |
| `SessionTraceReport` | `agents_workflow/plans/session_trace.py` | Public | 封裝三級軌跡提取結果、目標計畫狀態、摩擦訊號清單與格式化輸出。 |
| `SessionTraceEngine` | `agents_workflow/plans/session_trace.py` | Public | 執行三層信標 `.jsonl` 定錨、Telemetry 切片、`mtime` 回寫消歧與五大摩擦訊號偵測。 |
| `session_trace` | `agents-workflow/scripts/cli.py` | Public | `python yscb.py agents-workflow session-trace` CLI 命令入口函式。 |

---

## 2. 核心 API 簽名與詳細規格 (Method Signatures & Contracts)

```python
# === File: ys_codebase/source/core/core/telemetry.py ===
from typing import Any, Dict, List, Optional
from pathlib import Path

MAX_TELEMETRY_BYTES: int = 512 * 1024
KEEP_TELEMETRY_LINES: int = 1500

def resolve_telemetry_path(yscb_abs: Optional[str] = None) -> Path:
    """解析 cache://core/telemetry.jsonl 絕對路徑；若設定 YSCB_TELEMETRY_PATH 則優先採用。"""

def should_record_telemetry(module_name: str, cmd_path: List[str], raw_args: List[str]) -> bool:
    """判定是否記錄：排除 YSCB_TEST_SANDBOX=='1' (除非有 YSCB_TELEMETRY_PATH)、--help 與 session-trace。"""

def record_cli_event(
    module_name: str,
    cmd_path: List[str],
    args: List[str],
    exit_code: int,
    duration_ms: float,
    mode: str = "local",
    error_hint: str = "",
    yscb_abs: Optional[str] = None,
    cwd: Optional[str] = None,
) -> bool:
    """原子追加單筆 JSONL 紀錄並於超過 MAX_TELEMETRY_BYTES 時滾動保留最新 KEEP_TELEMETRY_LINES 筆。"""

def read_telemetry_records(
    since_iso: Optional[str] = None,
    since_minutes: Optional[float] = None,
    limit: Optional[int] = None,
    yscb_abs: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """讀取並過濾 telemetry.jsonl 紀錄清單，單行損毀自動跳過。"""


# === File: ys_codebase/source/agents-workflow/agents_workflow/plans/session_trace.py ===
from dataclasses import dataclass, field

@dataclass
class FrictionSignal:
    signal_type: str          # MULTI_EDIT_CHURN | TOOL_MISS_AND_RETRY | SILENT_BACKPATCH | GATE_BOUNCE | CONTEXT_WASTE | VALIDATED_BACKPROP
    severity: str             # HIGH | MEDIUM | INFO
    tier_source: str          # Tier 1 | Tier 2
    target: str               # 檔案路徑、CLI 指令或階段名稱
    summary: str              # 摩擦證據簡述
    details: Dict[str, Any] = field(default_factory=dict)

@dataclass
class SessionTraceReport:
    active_tier: str                              # Tier 1+2 | Tier 2 | Tier 3 (In-Context Fallback)
    transcript_path: Optional[str] = None
    transcript_candidates: List[Dict[str, Any]] = field(default_factory=list)
    target_plan: Optional[str] = None
    plan_resolution_note: str = ""
    session_start_ts: Optional[str] = None
    telemetry_count: int = 0
    signals: List[FrictionSignal] = field(default_factory=list)
    thinking_excerpts: List[Dict[str, Any]] = field(default_factory=list)
    fallback_checklist: List[str] = field(default_factory=list)
    def to_dict(self) -> Dict[str, Any]: ...
    def render_text(self) -> str: ...

class SessionTraceEngine:
    def __init__(
        self,
        plans_dir: Optional[Path] = None,
        archive_dir: Optional[Path] = None,
        project_root: Optional[Path] = None,
        telemetry_path: Optional[Path] = None,
    ) -> None: ...

    def locate_transcript(
        self,
        explicit_path: Optional[str] = None,
        release_targets: Optional[List[str]] = None,
    ) -> Tuple[Optional[Path], List[Dict[str, Any]]]:
        """三層信標定錨：1. 顯式路徑 -> 2. 尾端 64KB project_root + 自指信標 -> 3. 多候選清單。"""

    def audit_plan_mtimes(self, plan_dir: Path) -> List[FrictionSignal]:
        """比對 P00~P07 mtime 與 changelog.md 階段時間戳，消歧 VALIDATED_BACKPROP 與 SILENT_BACKPATCH。"""

    def analyze(
        self,
        plan_name_or_subpath: Optional[str] = None,
        transcript_path: Optional[str] = None,
        since_minutes: Optional[float] = None,
        limit: int = 50,
    ) -> SessionTraceReport:
        """執行三級漸進式軌跡提取與五大摩擦訊號聚合。"""
```

- **錯誤與例外契約 (Error & Exception Contracts)**：
  - `record_cli_event` 與 `read_telemetry_records`：內部捕獲所有 `OSError` / `ValueError`，絕不向外拋出未處理例外阻塞 CLI。
  - `SessionTraceEngine.analyze`：遇無效 `--transcript` 路徑或不可讀目錄時記錄於 `plan_resolution_note` 並自動降級至 Tier 2 / Tier 3，`cli.session_trace` 正常返回退出碼 `0`（僅在顯式傳入不存在之 `--plan <bad_name>` 時返回 `1`）。
- **階段決策紀錄**：`[P03:DR-01]` `FrictionSignal.signal_type` 納入 `VALIDATED_BACKPROP` (`INFO` 等級)，以便在報告中透明呈現「已合規登記之反向回寫」與「未申報之 `SILENT_BACKPATCH` (`HIGH` 等級)」對比。

---

## 3. 依賴拓撲與實作順序 (Implementation Topology)

```text
Step 1: core/telemetry.py & core/__init__.py (底層紀錄與讀取原語)
  └──> Step 2: core/commands/dispatcher.py & core/tests/test_cli_router.py (攔截掛載與 core 單元測試)
         └──> Step 3: agents_workflow/plans/session_trace.py & plans/__init__.py (三級提取與五大訊號分析引擎)
                └──> Step 4: scripts/cli.py, contributes/{core,agents-workflow}.json, _manifest.md & session-audit/SKILL.md
                       └──> Step 5: agents-workflow/tests/test_plans_toolchain.py & @build 雙模組熱同步
```

