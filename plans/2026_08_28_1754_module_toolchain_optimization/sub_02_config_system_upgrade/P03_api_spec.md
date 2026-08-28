# API 與介面規格說明書 (API Specification)

> 功能名稱：Config 系統架構升級、Contribute 專案特化規範與工具鏈建立 (Config & Project Contribute System)  
> 建立日期：2026-08-28  
> 所屬主計畫：`plans://2026_08_28_1754_module_toolchain_optimization/` (sub_02)  
> 狀態：Confirmed  
> 模板版本：v1.3  

---

## 1. 核心 Python SDK 介面規格 (`core.config`)

模組路徑：`source/core/core/config.py`

### 1.1 頂層函式與公開 API

```python
def get(module: str, key: Optional[str] = None, default: Any = None) -> Any:
    """
    查詢指定模組之有效設定值（支援點分隔巢狀路徑），原生封裝 Local > Project 雙層合併與快取自愈。

    :param module: 模組識別碼 (例如 "agents-workflow", "knowledge-db", "core")
    :param key: 點分隔鍵值路徑 (例如 "paths.plans", "spaces.project_main.include")。若為 None，返回該模組之完整合併組態字典。
    :param default: 當鍵值不存在時之回傳預設值 (預設 None)
    :return: 對應之組態值或 default
    """

def get_all(module: str) -> Dict[str, Any]:
    """
    獲取指定模組之完整合併組態字典副本。

    :param module: 模組識別碼
    :return: 深度合併後的字典副本
    """

def set(module: str, key: str, value: Any, local: bool = False) -> None:
    """
    寫入或更新指定模組之設定值（支援點分隔巢狀路徑），自動同步磁碟並熱自愈記憶體快取。

    :param module: 模組識別碼
    :param key: 點分隔鍵值路徑 (例如 "paths.plans")
    :param value: 欲寫入之值 (支援 int, float, bool, str, list, dict)
    :param local: 若為 True 寫入 config.local.json，若為 False 寫入 config.project.json
    """

def delete(module: str, key: str, local: bool = False) -> bool:
    """
    刪除指定模組設定檔中的特定鍵值。

    :param module: 模組識別碼
    :param key: 點分隔鍵值路徑
    :param local: 是否從 config.local.json 刪除
    :return: 是否成功刪除
    """

def reload(module: Optional[str] = None) -> None:
    """
    手動強制清空並重載記憶體快取。若 module 為 None 則重載全模組。
    """

def list_modules() -> List[str]:
    """
    列出當前 config:// 空間下存在設定檔之所有模組清單。
    """

def get_config_path(module: str, local: bool = False) -> str:
    """
    取得指定模組設定檔之實體絕對路徑。
    """
```

---

## 2. 核心聚合引擎規格升級 (`core.contributes.ContributesAggregator`)

模組路徑：`source/core/core/contributes.py`

### 2.1 專案特化 `contribute.json` 掃描函式

```python
def _load_config_space_overrides(self, target: str) -> Dict[str, Any]:
    """
    階層 ②：載入下游專案對目標模組的特化擴充注入 (config://<target>/contribute.json)。
    🚨 剛性禁止 contribute.local.json，檢測到時輸出警告日誌並忽略。

    :param target: 受獻目標模組名稱
    :return: 專案特化注入物件字典
    """
```

- **讀取路徑**：`config://<target>/contribute.json`（對應實體 `<yscb_root>/config/<target>/contribute.json`）。
- **防呆檢查**：若 `config://<target>/contribute.local.json` 存在，調用 `logger.warning("Ignoring 'contribute.local.json' in config://%s: project contribute overrides must be tracked by Git.", target)` 忽略處理。

---

## 3. 部署引擎規格升級 (`core.engine.PackageManager`)

模組路徑：`source/core/core/engine.py`

### 3.1 模板部署與淨化函式

```python
def act_deploy_configs_from_modules(self) -> None:
    """
    Stage 3 (Atomic Config Deployment & Template Purge):
    掃描各模組 runtime 目錄下的 configurable/ 資料夾：
    - 將 config.project.json, config.local.json, contribute.json 透過 _deep_infill_dict 增量補齊至 config://<mod>/
    - 部署完成後，物理刪除 runtime 空間的 module://<mod>/configurable/，保持代碼純淨。
    """
```

---

## 4. CLI 指令體系規格 (`core` 模組)

進入點：`source/core/scripts/cli.py`

| 子指令 | 語法 | 參數與旗標 | 輸出範例 / 行為 |
| :--- | :--- | :--- | :--- |
| **`config list`** | `python yscb.py config list [--mod=<mod>]` | `--mod`: 指定模組<br/>`--json`: 輸出 JSON 格式 | 輸出各模組的 Project / Local 配置鍵值與覆蓋狀態樹 |
| **`config get`** | `python yscb.py config get <mod> [key]` | `key`: 點分隔路徑<br/>`--json`: 輸出原始格式 | 輸出解析後之有效值 (例如 `paths.plans: project://plans`) |
| **`config set`** | `python yscb.py config set <mod> <key> <val> [--local]` | `--local`: 寫入本機覆蓋檔 | 寫入設定並提示：`[config] Updated <mod>:<key> in config.project.json` |

---

## 5. 消費端 SDK 收斂規範

| 消費端模組 | 重構位置 | 原手寫邏輯 | 重構後標準 SDK 調用 |
| :--- | :--- | :--- | :--- |
| **`core.uri`** | `_get_project_dir()` | 讀取 `config/core/config.project.json` | `config.get("core", "project_root")` |
| **`core.uri`** | `resolve()` (`type: "config"`) | 遍歷 `cand_configs` 檔案列表 | `config.get(provider_name, sval)` |
| **`knowledge-db`** | `space.py:load_spaces()` | 手寫讀取 `config.project.json` + `config.local.json` | `config.get("knowledge-db", "spaces", {})` |
| **`knowledge-db`** | `space.py:load_thesaurus()` | 手寫讀取同義詞陣列 | `config.get("knowledge-db", "thesaurus", [])` |
| **`agents-workflow`** | `targets.py` | 手寫讀取/寫入 `targets` | `config.get("agents-workflow", "release_targets")`<br/>`config.set("agents-workflow", "release_targets", ...)` |
| **`agents-workflow`** | `publisher.py` | 手寫讀取 `enable_agents_md` | `config.get("agents-workflow", "enable_agents_md", True)` |
| **`agents-workflow`** | `initializer.py` | 手寫更新 `paths` | `config.set("agents-workflow", f"paths.{k}", v)` |

---

## 6. 拓撲實作順序 (Implementation Topology)

```text
[TASK-01] 遷移全生態系源碼模板至 source/<module>/configurable/
    │
    ▼
[TASK-02] 實作 source/core/core/config.py (ConfigManager SDK)
    │
    ▼
[TASK-03] 升級 source/core/core/engine.py (act_deploy_configs_from_modules 適配 configurable/)
    │
    ▼
[TASK-04] 升級 source/core/core/contributes.py (階層 ② 改讀 contribute.json，阻斷 local 級)
    │
    ▼
[TASK-05] 消費端 SDK 100% 收斂 (core.uri, knowledge-db, agents-workflow)
    │
    ▼
[TASK-06] 實作 core CLI config 子指令體系與 contributes/core.json 註冊
    │
    ▼
[TASK-07] 建立單元測試 test_config.py 並更新 test_contributes.py 與全模組回歸
```
