# 功能交付與演練說明書 (Walkthrough & Delivery)

> 功能名稱：Dev 模組狀態檢核工具升級 (Dev Module Check & Diagnostics Upgrade)  
> 建立日期：2026-08-28  
> 所屬主計畫：`plans://2026_08_28_1754_module_toolchain_optimization/` (sub_03)  
> 狀態：Confirmed  
> 模板版本：v1.3  

---

## 1. 交付成果總覽 (Executive Summary)

本子計畫 (`sub_03_dev_module_check_upgrade`) 完成了 YS-Codebase 生態系中 **Dev 模組靜態合規與架構守門檢核系統 (`dev check`)** 的全面重構與升級：
1. **5 步流水線合規檢查引擎 (`dev.checker.Checker`)**：
   - **Step 1 (ManifestGuard)**：必填欄位完整性、SemVer 嚴格校驗、強制 `dependencies` 包含 `core`（`core` 本體除外）。
   - **Step 2 (CoreInjectGuard)**：檢核 `contributes/core.json`（CLI 子指令與 URI 協議注入）。
   - **Step 3 (StructureGuard)**：`scripts/cli.py` 進入點檢查、禁止根目錄散落 `config.*.json` 模板、暫存廢棄檔案掃描、`contributes.format.md` 文檔合規提示。
   - **Step 4 (AstSecurityGuard)**：AST 語法檢查、空間穿透防禦（禁止業務模組探測 `module.source://`）、反模式靶向攔截（禁止業務代碼直接手寫存取 `config.project.json` / `contributes.merged.json`，放行原生 I/O）。
   - **Step 5 (TestClassGuard)**：強制測試類別繼承 `dev.testing.case.YSCBTestCase`。
2. **三級嚴重度與 Release 剛性守門 (`dev.releaser.Releaser`)**：
   - `[PASS]`、`[WARN]`、`[FAIL]` 結構化分類。
   - 存在 `[FAIL]` 時剛性阻斷 `dev release` 發布流程，保障外發產物質量；同時放行 `dev build` 以利本機除錯。
3. **終端診斷排版與機器可讀輸出**：
   - 彩色/結構化終端報告與 `--json` 格式化輸出。
4. **歷史反模式與穿透全面清理**：
   - 藉由新檢核工具，成功抓出並徹底清理了 `agents-workflow`（`compiler.py`, `initializer.py`, `publisher.py`, `targets.py`）中歷史殘留的 6 處 `module.source://` 探測與手寫讀寫 config 反模式！

---

## 2. 變更檔案清冊 (File Change Manifest)

### 核心檢查器與守門引擎
- **`source/dev/dev/checker.py`** (REFACTOR)：實作 `CheckSeverity`, `CheckIssue`, `CheckReport` 與 5 步檢核流水線。
- **`source/dev/dev/releaser.py`** (MODIFY)：整合 `Checker.check_module()` 於 `release_check()`，當 `has_fails` 時阻斷。
- **`source/dev/scripts/cli.py`** (MODIFY)：升級 `dev check` 指令支援結構化三級診斷報告與 `--json` 格式。
- **`source/dev/dev/testing/case.py`** (MODIFY)：更新 `create_mock_source_module` 預設加入 `core` 依賴。

### 消費端清理與反模式修復
- **`source/agents-workflow/agents_workflow/compiler.py`** (MODIFY)：移除 `module.source://` fallback 穿透。
- **`source/agents-workflow/agents_workflow/initializer.py`** (MODIFY)：`_write_project_config` 100% 收斂為 `core.config.set()`。
- **`source/agents-workflow/agents_workflow/publisher.py`** (MODIFY)：`_get_project_config` 100% 收斂為 `core.config.get_all()`。
- **`source/agents-workflow/agents_workflow/targets.py`** (MODIFY)：`_load_config_data` / `_save_config_data` 100% 收斂為 `core.config`。

### 測試套件
- **`source/dev/tests/test_checker.py`** (REFACTOR)：覆蓋 FT-01~07 與 ET-01~02 檢核測試案例。

---

## 3. 實機驗收與回歸測試結果 (Verification Results)

```text
======================================================================
YS-Codebase Test Execution Diagnostic Report
======================================================================
[*] Mode: Default (LOGIC + ENV) | Target: All | Build: Hermetic Build
----------------------------------------------------------------------
[*] Module: agents-workflow (19.60s)                            [PASS]
    |-- [Contract] Auto-Contract Suite ... (3/3)
    \-- [Custom]   Custom Tests ........... (29/29)
[*] Module: core (2.30s)                                        [PASS]
    |-- [Contract] Auto-Contract Suite ... (3/3)
    \-- [Custom]   Custom Tests ........... (54/54)
[*] Module: dev (13.45s)                                        [PASS]
    |-- [Contract] Auto-Contract Suite ... (3/3)
    \-- [Custom]   Custom Tests ........... (46/46)
[*] Module: knowledge-db (20.33s)                               [PASS]
    |-- [Contract] Auto-Contract Suite ... (3/3)
    \-- [Custom]   Custom Tests ........... (37/37)
----------------------------------------------------------------------
Summary : 178 Total, 178 Passed, 0 Failed, 0 Skipped (21.623s)
Status  : PASSED (100% Ready)
======================================================================
```

---

## 4. 操作手冊與 CLI 速查 (Quick Reference)

### 4.1 CLI 指令

```bash
# 1. 檢核全生態系所有源碼模組
python yscb.py dev check --all

# 2. 檢核指定單一模組
python yscb.py dev check <module_name>

# 3. 機器可讀 JSON 格式輸出
python yscb.py dev check --all --json
```

### 4.2 Python SDK (`dev.checker`)

```python
from dev.checker import Checker, CheckSeverity

checker = Checker()

# 檢核單一模組 (回傳 CheckReport)
report = checker.check_module("knowledge-db")
if report.has_fails:
    for err in report.errors:
        print("FAIL:", err)

# 支援舊版 Tuple 兼容解包
passed, errors = checker.check_module("knowledge-db")
```
