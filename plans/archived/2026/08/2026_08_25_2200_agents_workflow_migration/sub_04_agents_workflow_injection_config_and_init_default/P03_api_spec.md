# Phase 3: API 與介面規格說明書 (API Spec) - agents-workflow 配置治理與一鍵初始化

> 計畫名稱：`sub_04_agents_workflow_injection_config_and_init_default`  
> 建立日期：2026-08-26  
> 所屬主計畫：[2026_08_25_2200_agents_workflow_migration](../umbrella_overview.md)  
> 依據架構設計：[P02_architecture_plan.md](./P02_architecture_plan.md)  
> 當前狀態：`Confirmed` (Phase 3 API 設計確認完成)  
> 擴充項目：none  
> 模板版本：v1.4  

---

## 1. 組態與清單 Schema 規格 (Configuration & Manifest Schemas)

### 1.1 `manifest.json` URI 貢獻宣告
```json
{
  "name": "agents-workflow",
  "version": "0.1.0",
  "contributes": {
    "core": {
      "uri": {
        "workflow.plans": "config://agents-workflow/config.project.json:paths.plans",
        "workflow.archived": "config://agents-workflow/config.project.json:paths.archived",
        "workflow.ext": "config://agents-workflow/config.project.json:paths.ext",
        "workflow.docs": "config://agents-workflow/config.project.json:paths.docs"
      }
    }
  }
}
```

### 1.2 `config.project.json` 模板 Schema
```json
{
  "paths": {
    "plans": "!undefined",
    "archived": "!undefined",
    "ext": "!undefined",
    "docs": "!undefined"
  },
  "ide": [],
  "enable_agents_md": true,
  "enable_project_changelog": true
}
```

---

## 2. 初始化引擎 API 簽名 (`WorkflowInitializer`)

```python
class WorkflowInitializer:
    """負責 agents-workflow 的一鍵初始化、路徑探測、目錄建立與組態原子持久化。"""

    DEFAULT_RECOMMENDED_PATHS: Dict[str, str] = {
        "plans": "project://.agent_workflow/plans",
        "archived": "project://.agent_workflow/plans/archived",
        "ext": "project://.agent_workflow/extensions",
        "docs": "project://docs"
    }

    def __init__(self, host_dir: Optional[str] = None):
        self.host_dir = host_dir

    def probe_paths(self, target_paths: Dict[str, str]) -> List[Dict[str, Any]]:
        """
        探測目標路徑的實體狀態與存在性。
        
        :param target_paths: 包含 plans, archived, ext, docs 的路徑字典 (可為語意 URI 或實體路徑)
        :return: 包含 key, uri_or_path, real_path, exists 的資訊清冊
        """

    def run_init_default(
        self,
        paths_override: Optional[Dict[str, str]] = None,
        auto_confirm: bool = False,
        interactive: bool = True
    ) -> Dict[str, Any]:
        """
        執行 --init-default 完整流程。
        
        :param paths_override: 使用者傳入之覆蓋路徑字典 (例: {"plans": "project://my_plans"})
        :param auto_confirm: 若為 True (-y/--yes)，跳過互動確認直接執行
        :param interactive: 是否處於 TTY 終端模式
        :return: {"success": bool, "created_dirs": List[str], "bound_paths": Dict[str, str], "cancelled": bool}
        """
```

---

## 3. CLI 命令列介面規格 (`scripts/cli.py`)

### 3.1 命令語法與參數清單
```bash
python yscb.py agents-workflow --init-default [options]
```

| 參數名稱 | 縮寫 | 說明 | 範例 |
| :--- | :---: | :--- | :--- |
| `--init-default` | - | 觸發 workflow 協議與目錄一鍵初始化流程 | `yscb agents-workflow --init-default` |
| `--yes` | `-y` | 自動確認，無提示直接建立目錄與綁定路徑 | `yscb agents-workflow --init-default -y` |
| `--path-plans` | - | 覆蓋 plans 協議綁定路徑 | `--path-plans="project://custom_plans"` |
| `--path-archived` | - | 覆蓋 archived 協議綁定路徑 | `--path-archived="project://custom_archived"` |
| `--path-ext` | - | 覆蓋 ext 協議綁定路徑 | `--path-ext="project://custom_extensions"` |
| `--path-docs` | - | 覆蓋 docs 協議綁定路徑 | `--path-docs="project://my_docs"` |

---

## 4. 錯誤處理與邊界值規格 (Error Handling Specifications)

| 異常/邊界情境 | 觸發條件 | 處理策略與預期返回值 |
| :--- | :--- | :--- |
| **使用者輸入 `n` 拒絕** | 互動提示時輸入 `n` 或 `no` | 返回 `{"success": True, "cancelled": True}`，終端輸出 `[agents-workflow] Initialization cancelled by user.`，退出碼為 0。 |
| **`project://` 未定義** | 宿主尚未配置 `project_root` | 若 Core 支援 JIT，自動引導 JIT 補齊 `project://`；若非互動模式且未定義，拋出錯誤並退出碼 1。 |
| **無效路徑參數** | `--path-*` 傳入空值或格式錯誤 | 終端輸出 `[agents-workflow] Error: Invalid path value for --path-<key>`，退出碼為 1。 |

---

## 5. 當前階段確認狀態

- **當前狀態**：`Draft` (Phase 3 API 設計草擬完成)  
- **推進關卡**：請開發者審查本 API 規格說明書，若確認無誤，請明確指示「**確認無誤，推進至 Phase 4**」！
