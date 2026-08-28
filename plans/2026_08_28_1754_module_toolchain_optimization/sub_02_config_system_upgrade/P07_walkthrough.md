# 功能交付與演練說明書 (Walkthrough & Delivery)

> 功能名稱：Config 系統架構升級、Contribute 專案特化規範與工具鏈建立 (Config & Project Contribute System)  
> 建立日期：2026-08-28  
> 所屬主計畫：`plans://2026_08_28_1754_module_toolchain_optimization/` (sub_02)  
> 狀態：Confirmed  
> 模板版本：v1.3  

---

## 1. 交付成果總覽 (Executive Summary)

本子計畫 (`sub_02_config_system_upgrade`) 完成了 YS-Codebase 生態系中 **Config 運行組態體系** 與 **Contribute 能力擴充體系** 的徹底分離與工具鏈升級：
1. **微內核 `core.config` SDK**：提供 `get`, `get_all`, `set`, `delete`, `reload`, `list_modules` 介面，原生支援 Local > Project 雙層深層合併與 `(project_mtime, local_mtime)` 快取自愈。
2. **標準 `configurable/` 模板目錄規範**：徹底消滅源碼根目錄散落之模板檔案，由部署引擎 `act_deploy_configs_from_modules()` 自動增量補齊並物理刪除 runtime 空間之 `configurable/`。
3. **專案特化 `contribute.json` 類別**：下游專案對目標模組的擴充注入統一置於 `config://<target>/contribute.json`（強制受 Git 追蹤），並剛性禁止與阻斷警告 `contribute.local.json`。
4. **全模組消費端 100% 收斂**：`core.uri`、`knowledge-db` (`space.py`)、`agents-workflow` (`targets.py`, `publisher.py`, `initializer.py`) 徹底移除手寫組態與手寫 contributes 邏輯。
5. **CLI 工具鏈與 Contributes 註冊**：提供 `python yscb.py config list / get / set / reload` 指令體系。

---

## 2. 變更檔案清冊 (File Change Manifest)

### 核心微內核與引擎
- **`source/core/core/config.py`** (NEW)：實作微內核 `ConfigManager` 與統一公開 SDK。
- **`source/core/core/engine.py`** (MODIFY)：升級 `act_deploy_configs_from_modules()` 支援 `configurable/` 掃描與 `contribute.json` 部署淨化，移除重複舊代碼。
- **`source/core/core/contributes.py`** (MODIFY)：階層 ② 改為讀取 `config://<target>/contribute.json`，剛性阻斷並警告 `contribute.local.json`。
- **`source/core/core/uri.py`** (MODIFY)：`_get_project_dir()` 與 `resolve()` 收斂調用 `core.config.get()`。
- **`source/core/scripts/cli.py`** (MODIFY)：實作 `cmd_config` 處理器與 `config list / get / set / reload` 指令路由。
- **`source/core/contributes/core.json`** (MODIFY)：註冊 `commands.config` 與防呆規則。

### 模組模板目錄標準化
- **`source/core/configurable/config.project.json`** (NEW / REFACTOR)
- **`source/agents-workflow/configurable/config.project.json`** (NEW / REFACTOR)
- **`source/knowledge-db/configurable/contribute.json`** (NEW / REFACTOR)

### 消費端模組重構
- **`source/knowledge-db/knowledge_db/space.py`** (MODIFY)：100% 由 `core.contributes` 驅動，徹底刪除手寫讀取 `config.project.json` / `config.local.json` 之舊邏輯。
- **`source/agents-workflow/agents_workflow/targets.py`** (MODIFY)：收斂調用 `core.config` 讀寫。
- **`source/agents-workflow/agents_workflow/publisher.py`** (MODIFY)：收斂調用 `core.config.get_all()`。
- **`source/agents-workflow/agents_workflow/initializer.py`** (MODIFY)：收斂調用 `core.config.set()`。

### 測試套件
- **`source/core/tests/test_config.py`** (NEW)：涵蓋 FT-01~03, FT-07, ET-01~02 單元測試。
- **`source/core/tests/test_contributes.py`** (MODIFY)：新增 FT-05 專案特化 `contribute.json` 覆蓋與 `contribute.local.json` 阻斷測試。
- **`source/core/tests/test_engine.py`** (MODIFY)：新增 FT-04 `configurable/` 部署與模板淨化測試。
- **`source/knowledge-db/tests/test_space.py`** (MODIFY)：更新 FT-04 為驗證 `contribute.json` 覆蓋。

---

## 3. 實機驗收與回歸測試結果 (Verification Results)

```text
======================================================================
YS-Codebase Test Execution Diagnostic Report
======================================================================
[*] Mode: Default (LOGIC + ENV) | Target: All | Build: Hermetic Build
----------------------------------------------------------------------
[*] Module: agents-workflow (24.27s)                            [PASS]
    |-- [Contract] Auto-Contract Suite ... (3/3)
    \-- [Custom]   Custom Tests ........... (29/29)
[*] Module: core (3.84s)                                        [PASS]
    |-- [Contract] Auto-Contract Suite ... (3/3)
    \-- [Custom]   Custom Tests ........... (54/54)
[*] Module: dev (16.47s)                                        [PASS]
    |-- [Contract] Auto-Contract Suite ... (3/3)
    \-- [Custom]   Custom Tests ........... (40/40)
[*] Module: knowledge-db (25.81s)                               [PASS]
    |-- [Contract] Auto-Contract Suite ... (3/3)
    \-- [Custom]   Custom Tests ........... (37/37)
----------------------------------------------------------------------
Summary : 172 Total, 172 Passed, 0 Failed, 0 Skipped (27.717s)
Status  : PASSED (100% Ready)
======================================================================
```

---

## 4. 操作手冊與 API 速查 (Quick Reference)

### 4.1 Python SDK (`core.config`)

```python
from core import config

# 查詢組態 (支援點分隔路徑，Local 覆蓋 Project)
plans_dir = config.get("agents-workflow", "paths.plans", default="project://plans")

# 獲取完整字典
all_cfg = config.get_all("agents-workflow")

# 寫入組態 (local=False 寫入 config.project.json，local=True 寫入 config.local.json)
config.set("core", "project_root", "./", local=False)

# 刪除鍵值
config.delete("core", "custom_key", local=False)

# 強制重載快取
config.reload("core")
```

### 4.2 CLI 指令

```bash
# 1. 檢視全模組組態狀態
python yscb.py config list [--mod=<module>] [--json]

# 2. 查詢特定設定值
python yscb.py config get <module> [key] [--json]

# 3. 更新設定值 (加上 --local 寫入個人本地覆蓋)
python yscb.py config set <module> <key> <val> [--local]

# 4. 強制刷新記憶體快取
python yscb.py config reload [module]
```
