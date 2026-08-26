# API 與介面規格書 (API & Interface Specification)

> 功能名稱：Plans CLI 工具鏈補齊與舊版功能遷移 (Plans CLI Toolchain Migration)  
> 建立日期：2026-08-26  
> 所屬主計畫：[agents-workflow 模組全面遷移與升級 (2026_08_25_2200_agents_workflow_migration)](../umbrella_overview.md)  
> 狀態：Confirmed  
> 依據 P01/P02：[P01_requirements_spec.md](./P01_requirements_spec.md), [P02_architecture_plan.md](./P02_architecture_plan.md)  
> 模板版本：v1.2  

---

## 1. 介面契約清單 (Interface Inventory)

| 介面 / 類別名稱 | 所屬檔案路徑 | 存取層級 | 核心職責 |
| :--- | :--- | :---: | :--- |
| `PlanArchiver` | `agents_workflow/plans/archiver.py` | Public | 執行計畫完成度/CHANGELOG/交接快照清理/防衝突 4 重檢查與安全搬移 |
| `PlanScanner` | `agents_workflow/plans/scanner.py` | Public | 掃描進行中目錄，解析 Track 與 Phase 狀態並渲染 ASCII 狀態矩陣 |
| `PlanSearcher` | `agents_workflow/plans/searcher.py` | Public | 跨目錄檢索 Markdown 文件，支援 DR 正則結構化去重與全文程式碼片段檢索 |
| `PlanVerifier` | `agents_workflow/plans/verifier.py` | Public | 稽核 Markdown 文件是否殘留模板指引註解及 Header 元數據規範性 |
| `cmd_plan` | `scripts/cli.py` | Public CLI | 派發 `plan archive`, `plan status`, `plan search`, `plan verify` 與別名 |

---

## 2. 異常型別與契約定義 (Custom Exceptions)

```python
class PlansToolchainError(Exception):
    """Plans 工具鏈通用例外基底。"""
    pass

class PlanNotFoundError(PlansToolchainError):
    """找不到指定的計畫目錄時拋出 [EC-01]。"""
    pass

class PlanFormatError(PlansToolchainError):
    """計畫名稱時間戳前綴不符合規範時拋出 [EC-02]。"""
    pass

class PlanIncompleteError(PlansToolchainError):
    """計畫未標記 Completed 或未登載 CHANGELOG 且無 --force 時拋出 [EC-03]。"""
    pass

class PlanDestinationExistsError(PlansToolchainError):
    """歸檔目的地目錄已存在同名計畫時拋出 [EC-04]。"""
    pass
```

---

## 3. 核心 API 簽名與詳細規格 (Method Signatures & Contracts)

### 3.1 `PlanArchiver` (archiver.py)

```python
class PlanArchiver:
    """計畫安全歸檔服務。"""

    def __init__(self, plans_dir: Optional[Path] = None, archive_dir: Optional[Path] = None, project_root: Optional[Path] = None):
        """
        初始化 Archiver。
        若路徑為 None，預設調用 core.uri.resolve 解析 workflow.plans://, workflow.archived://, project://。
        """
        ...

    def archive_plan(self, plan_name: str, force: bool = False) -> dict:
        """
        執行計畫安全歸檔操作。
        
        Args:
            plan_name: 計畫目錄名稱 (例如 2026_08_23_1505_feature_name)
            force: 若為 True，跳過完成狀態與 CHANGELOG 記載檢查
            
        Returns:
            dict: {
                "success": bool,
                "plan_name": str,
                "source_path": Path,
                "dest_path": Path,
                "cleaned_handoff": bool,
                "warnings": list[str],
                "error": Optional[str]
            }
            
        Raises:
            PlanNotFoundError: 目錄不存在 [EC-01]
            PlanFormatError: 時間戳格式不符 [EC-02]
            PlanIncompleteError: 未完成且無 force [EC-03]
            PlanDestinationExistsError: 目的地衝突 [EC-04]
        """
        ...
```

### 3.2 `PlanScanner` (scanner.py)

```python
class PlanScanner:
    """進行中計畫狀態矩陣掃描服務。"""

    def __init__(self, plans_dir: Optional[Path] = None):
        ...

    def get_plan_info(self, plan_dir: Path) -> dict:
        """
        解析單一計畫目錄的元數據。
        
        Returns:
            dict: {
                "name": str,
                "path": Path,
                "track": str,        # Umbrella | Fast Track | Full Track | Phase 0 | Unknown
                "status": str,       # Completed | Phase X ... | Paused
                "sub_plans": list[dict]
            }
        """
        ...

    def scan_active_plans(self) -> list[dict]:
        """
        掃描 workflow.plans:// 下的所有活躍進行中計畫。
        明確不掃描歷史目錄 [FR-02, P00:DR-04]。
        """
        ...

    def render_matrix_ascii(self, plans: list[dict]) -> str:
        """將掃描結果渲染為美觀的 ASCII 表格。"""
        ...
```

### 3.3 `PlanSearcher` (searcher.py)

```python
class PlanSearcher:
    """歷史計畫與決策記錄檢索服務。"""

    def __init__(self, plans_dir: Optional[Path] = None, archive_dir: Optional[Path] = None):
        ...

    def search_drs(self, query: str = "", limit: int = 25) -> list[dict]:
        """
        結構化檢索 Decision Records (DR)。
        正則匹配 [{Phase}:DR-XX] 與 ### DR-XX，按 (plan_name, dr_id) 去重。
        
        Returns:
            list[dict]: [{
                "plan_name": str,
                "source_file": str,
                "dr_id": str,
                "summary": str
            }]
        """
        ...

    def search_full_text(self, query: str, year: Optional[str] = None, month: Optional[str] = None, limit: int = 20) -> list[dict]:
        """
        跨目錄全文檢索 Markdown。
        
        Returns:
            list[dict]: [{
                "plan_name": str,
                "rel_path": str,
                "line_no": int,
                "matched_line": str,
                "context_lines": list[tuple[int, str]]
            }]
        """
        ...
```

### 3.4 `PlanVerifier` (verifier.py)

```python
class PlanVerifier:
    """計畫規範與合規稽核服務。"""

    def __init__(self, plans_dir: Optional[Path] = None, archive_dir: Optional[Path] = None):
        ...

    def verify_single_file(self, file_path: Path) -> list[dict]:
        """
        稽核單一 Markdown 文件。
        檢查：
        1. 是否殘留 <!-- AGENT_GUIDANCE --> 模板指引註解
        2. Blockquote Header (功能名稱, 建立日期, 狀態)
        
        Returns:
            list[dict]: [{"level": "ERROR" | "WARN", "msg": str}]
        """
        ...

    def verify_plan_directory(self, plan_dir: Path) -> dict[str, list[dict]]:
        """遞迴稽核計畫目錄（包含 sub_* 子計畫）。"""
        ...

    def verify(self, plan_name: Optional[str] = None, include_all: bool = False) -> dict:
        """執行整體稽核任務並回傳彙總統計。"""
        ...
```

---

## 4. 依賴拓撲與實作順序 (Implementation Topology)

```text
Layer 0: agents_workflow/plans/__init__.py
         └── 定義例外型別與子套件導出
Layer 1: agents_workflow/plans/scanner.py
         └── 實作 Header/Track/Phase 解析與 ASCII 矩陣輸出
Layer 2: agents_workflow/plans/archiver.py
         └── 依賴 Header 解析，實作 4 重安全檢查與目錄搬移
Layer 3: agents_workflow/plans/searcher.py
         └── 實作 DR 正則提取去重與全文串流匹配
Layer 4: agents_workflow/plans/verifier.py
         └── 實作註解掃描與 Header 規範稽核
Layer 5: scripts/cli.py
         └── 實作 cmd_plan CLI 路由派發與別名支援
Layer 6: test/test_agents_workflow_plans_toolchain.py
         └── 實作 11 個單元與邊界測試案例 (FT-01~04, ET-01~06, RT-01)
```
