# API 與介面規格書 (API & Interface Specification)

> 功能名稱：sub_05_agents_workflow_code_optimization  
> 建立日期：2026-10-31  
> 所屬主計畫：2026_10_30_1641_code_optimize  
> 狀態：Confirmed  
> 模型：Gemini 4 Argon (Low)  

> 模板版本：v1.2  

---

## 1. 介面契約清單 (Interface Inventory)

| 介面 / 類別名稱 | 所屬檔案路徑 | 存取層級 | 核心職責 |
| :--- | :--- | :---: | :--- |
| `resolve_plan_uri` / `parse_markdown_blockquote_headers` | `agents_workflow/plans/_common.py` | Internal | 統一解析 `workflow.plans://`/`workflow.archived://` 語意 URI 與 Markdown 頂部 `> Key：Value` 標頭 |
| `ArtifactCompiler` | `agents_workflow/compiler.py` | Public | 執行 Stage 1 錨點展開與 Stage 2 語意 URI 編譯（移除 `mod_order` 與舊版單目標包裝） |
| `ReleasePublisher` | `agents_workflow/publisher.py` | Public | 執行多目標二層物化發布、Diff 短路檢測與孤兒清理（移除 `interactive` 未使用參數與舊遷移方法） |
| `PlanVerifier` / `PlanReport` | `agents_workflow/plans/verifier.py` | Public | 執行計畫結構、標頭章節與跨文件追溯鏈驗證（委派規格予 `_verifier_specs`、自癒予 `_verifier_healer`） |
| `SessionTraceEngine` | `agents_workflow/plans/session_trace.py` | Public | 探索跨平台 AI IDE 對話轉錄並委派 `_trace_parser` 與 `_trace_renderer` 產出審計報告 |
| `PlanStatusResolver` / `RoadmapManager` / `TodoManager` | `agents_workflow/plans/status.py`, `agents_workflow/roadmap.py` | Public | 推導 7 大計畫軌道下一步行動與執行統一立項晉升管線 |

---

## 2. 核心 API 簽名與詳細規格 (Method Signatures & Contracts)

```python
# agents_workflow/plans/_common.py
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Union

def resolve_plan_uri(uri_scheme: str, fallback_rel: Optional[str] = None) -> Path: ...
def parse_markdown_blockquote_headers(content_or_lines: Union[str, Sequence[str]], max_lines: int = 35) -> Dict[str, str]: ...

# agents_workflow/compiler.py
class ArtifactCompiler:
    def resolve_single_artifact(self, raw_text: str, inserts: List[Dict[str, Any]], doc_name: str = "") -> str: ...
    def compile_stage1(self) -> Dict[str, Any]: ...
    def resolve_stage2_uri(
        self,
        content: str,
        current_dst_path: str,
        deployment_map: Dict[str, str],
        doc_name: str = "",
        target_name: str = "antigravity",
    ) -> str: ...

# agents_workflow/publisher.py
class ReleasePublisher:
    def release_all(self, force: bool = False) -> Dict[str, Any]: ...

# agents_workflow/plans/verifier.py
class PlanVerifier:
    def verify_plan(
        self,
        plan_name_or_dir: Union[str, Path],
        phase: str = "all",
        log_msg: Optional[str] = None,
        log_type: str = "PHASE",
        model: Optional[str] = None,
    ) -> PlanReport: ...
    def verify_all_plans(self) -> Dict[str, PlanReport]: ...

# agents_workflow/plans/_trace_parser.py
def parse_transcript_file(
    transcript_path: Path,
    project_root: Path,
    plans_dir: Path,
    archive_dir: Path,
) -> Tuple[List[str], List[FrictionSignal], List[Dict[str, Any]], Dict[str, Any]]: ...
```

- **錯誤與例外契約 (Error & Exception Contracts)**：
  - `targets.save_tier_targets`：當底層 `config.set` 或 `config.save` 失敗時，不再以空白 `except Exception: pass` 吞沒，直接拋出底層異常（對應 `EC-02`）。
  - `plans.__init__.__getattr__`：存取非公開匯出之屬性時拋出 `AttributeError`（對應 `EC-04`）。
- **階段決策紀錄**：`[P03:DR-01]` 移除 `ArtifactCompiler.resolve_single_artifact` 之未使用參數 `mod_order`、`ReleasePublisher.release_all` 之未使用參數 `interactive`、以及 `PlanVerifier.verify_all_plans` 之未使用參數 `include_archived`，實現 `Mode A` 零冗餘簽名。

---

## 3. 依賴拓撲與實作順序 (Implementation Topology)

```text
Step 1 (基礎原語與規格層):
  plans/_common.py -> plans/_verifier_specs.py -> plans/_verifier_healer.py
  plans/_trace_renderer.py -> plans/_trace_parser.py

Step 2 (核心引擎與無環配置層):
  compiler.py -> targets.py -> publisher.py -> initializer.py

Step 3 (Plans 業務層與門面):
  scanner.py -> verifier.py -> status.py -> archiver.py -> searcher.py -> roadmap.py -> session_trace.py -> plans/__init__.py

Step 4 (CLI 入口與測試同步):
  scripts/cli.py & contributes/core.json -> tests/test_*.py
```
