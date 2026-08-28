# API 與介面規格書 (API & Interface Specification)

> 功能名稱：Agents-Workflow Release 預設 Local 模式、Gitignore 軟合併同步與 Core Config 來源層級探測 (Release Local Mode, Gitignore Sync & Core Config Origin Inspection)  
> 建立日期：2026-08-28  
> 所屬主計畫：`plans://2026_08_28_1754_module_toolchain_optimization/` (sub_05)  
> 狀態：Confirmed  
> 模板版本：v1.2  

---

## 1. 介面契約清單 (Interface Inventory)

| 介面 / 類別名稱 | 所屬檔案路徑 | 存取層級 | 核心職責 |
| :--- | :--- | :---: | :--- |
| `core.config.get_raw` | `core/config.py` | Public | 讀取單一層級 (Local 或 Project) 原始未合併設定 |
| `core.config.inspect` | `core/config.py` | Public | 探測鍵值之來源層級 (`local`/`project`/`both`/`none`) 與覆蓋狀態 |
| `ReleaseTargetManager` | `agents_workflow/targets.py` | Public | 管理 Release Target 啟用/停用（預設 Local，支援 `--proj`）與狀態清冊 |
| `ReleasePublisher` | `agents_workflow/publisher.py` | Public | 4 步原子發布交易引擎與 `.gitignore` 軟合併同步 |
| `cmd_release_target` | `scripts/cli.py` | Public | CLI 指令封裝（支援 `--proj` 旗標與多層彩色排版） |

---

## 2. 核心 API 簽名與詳細規格 (Method Signatures & Contracts)

### 2.1 `core.config`
```python
def get_raw(
    module: str,
    key: Optional[str] = None,
    local: bool = False,
    default: Any = None,
) -> Any:
    """
    讀取指定模組特定層級 (local=True 讀 Local, local=False 讀 Project) 之未合併原始組態。
    若 key 為 None 則回傳該層級完整字典副本。
    """
    ...

def inspect(module: str, key: str) -> Dict[str, Any]:
    """
    探測指定模組特定鍵值之來源層級與覆蓋狀態。
    回傳字典結構:
    {
        "key": key,
        "effective": effective_value,
        "source": "local" | "project" | "both" | "none",
        "local_value": ...,
        "project_value": ...,
        "is_overridden": bool
    }
    """
    ...
```

### 2.2 `agents_workflow.targets.ReleaseTargetManager`
```python
class ReleaseTargetManager:
    @classmethod
    def list_targets(cls) -> List[Dict[str, Any]]:
        """
        列出所有可用 Targets，標註來源狀態:
        [ENABLED (LOCAL)], [ENABLED (PROJECT)], [ENABLED (BOTH)], [DISABLED], [ORPHAN / NOT FOUND]
        """
        ...

    @classmethod
    def add_target(cls, target_name: str, is_project: bool = False) -> bool:
        """
        啟用 Target。
        - is_project=False: 寫入 config.local.json (預設)
        - is_project=True: 寫入 config.project.json
        自動觸發 ReleasePublisher.release_all()。
        """
        ...

    @classmethod
    def remove_target(cls, target_name: str, is_project: bool = False) -> bool:
        """
        停用 Target。
        - is_project=False: 從 config.local.json 移除
        - is_project=True: 從 config.project.json 移除
        自動觸發 ReleasePublisher.release_all()（清理檔案）。
        """
        ...
```

### 2.3 `agents_workflow.publisher.ReleasePublisher`
```python
class ReleasePublisher:
    GITIGNORE_BEGIN_MARKER = "# === YSCB AGENTS_WORKFLOW IGNORE BEGIN ==="
    GITIGNORE_END_MARKER = "# === YSCB AGENTS_WORKFLOW IGNORE END ==="

    def sync_gitignore(self, active_targets: Optional[List[str]] = None) -> Dict[str, Any]:
        """
        非破壞性軟合併 project://.gitignore 中的 YSCB 管理區塊。
        若 .gitignore 不存在則自動建立；若已存在則安全更新標記區塊，外部規則 100% 保持原樣。
        """
        ...
```

---

## 3. 依賴拓撲與實作順序 (Implementation Topology)

```text
[Layer 1: Microkernel Config SDK]
    └── core/config.py (get_raw & inspect 實作與匯出)
             │
             ▼
[Layer 2: Target & Publisher Services]
    ├── agents_workflow/targets.py (預設 Local, is_project 參數, list_targets 升級)
    └── agents_workflow/publisher.py (聯集 Targets 解析, sync_gitignore 軟合併)
             │
             ▼
[Layer 3: CLI Interface & Tests]
    ├── scripts/cli.py (cmd_release_target --proj 支援與彩色排版)
    ├── core/tests/test_config.py (新增 get_raw & inspect 測試)
    └── agents_workflow/tests/test_targets.py (新增 Local 預設與 .gitignore 測試)
```
