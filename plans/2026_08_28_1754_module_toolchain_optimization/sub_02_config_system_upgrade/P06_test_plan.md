# 測試計畫與驗證報告 (Test Plan & Verification)

> 功能名稱：Config 系統架構升級、Contribute 專案特化規範與工具鏈建立 (Config & Project Contribute System)  
> 建立日期：2026-08-28  
> 所屬主計畫：`plans://2026_08_28_1754_module_toolchain_optimization/` (sub_02)  
> 狀態：Passed  
> 模板版本：v1.3  

---

## 1. 自動化測試案例清單 (Automated Test Cases)

| 測試編號 | 測試類型 | 驗證目標與斷言 | 對應需求 | 執行指令 / 測試方法 |
| :--- | :---: | :--- | :---: | :--- |
| **FT-01** | 單元測試 | **Config SDK 點分隔查詢與快取**：驗證 `core.config.get("mod", "a.b.c")` 正確解析巢狀結構並命中記憶體快取。 | FR-01, FR-02 | `python yscb.py dev test core -k test_config_get_dot_notation` |
| **FT-02** | 單元測試 | **Local 覆蓋 Project 雙層合併**：驗證 `config.local.json` 之鍵值優先覆蓋 `config.project.json`，且未覆蓋部分完整保留。 | FR-02 | `python yscb.py dev test core -k test_local_overrides_project` |
| **FT-03** | 單元測試 | **Config SDK 寫入與熱自愈**：驗證 `core.config.set("mod", "key", val, local=False)` 正確寫入檔案並自動更新快取。 | FR-01, EC-03 | `python yscb.py dev test core -k test_config_set_and_auto_healing` |
| **FT-04** | 單元測試 | **`configurable/` 部署與淨化**：驗證 `act_deploy_configs_from_modules()` 正確自 `configurable/` 部署種子至 `config://` 並清除 runtime 模板。 | FR-03, FR-04 | `python yscb.py dev test core -k test_deploy_configurable_templates` |
| **FT-05** | 單元測試 | **專案特化 `contribute.json` 覆蓋與 Local 阻斷**：驗證 `ContributesAggregator` 正確讀取 `contribute.json` 覆蓋，且檢測到 `contribute.local.json` 時安全忽略。 | FR-05, EC-04 | `python yscb.py dev test core -k test_contribute_json_override` |
| **FT-06** | 整合測試 | **Knowledge-DB 與 Agents-Workflow SDK 收斂**：驗證兩大模組完全透過 `core.config` SDK 正常載入 spaces, thesaurus, targets 與 paths。 | FR-06 | `python yscb.py dev test knowledge-db` & `agents-workflow` |
| **FT-07** | 整合測試 | **`config` CLI 指令運作**：驗證 `python yscb.py config list`, `get`, `set` 正確輸出與修改配置。 | FR-07 | `python yscb.py dev test core -k test_config_cli` |
| **ET-01** | 邊界測試 | **無 Config 檔案安全回退**：驗證模組目錄無任何設定檔時返回 `default` 不拋錯。 | EC-01 | `python yscb.py dev test core -k test_config_missing_fallback` |
| **ET-02** | 邊界測試 | **損毀 JSON 容錯降級**：驗證 JSON 語法損毀時輸出警告日誌並安全降級。 | EC-02 | `python yscb.py dev test core -k test_config_corrupted_json_isolation` |
| **RT-01** | 全域回歸 | **全模組虛擬沙盒回歸跑測**：全系統 4 大模組 100% Passed (164+ 測試全綠)。 | NFR-04 | `python yscb.py dev test --all` |

---

## 2. 測試案例清單 (Test Cases)

| 測試 ID | 測試類型 | 驗證目標 | 預期行為 | 實機測試狀態 |
| :--- | :--- | :--- | :--- | :---: |
| **FT-01** | 功能測試 | 點分隔路徑查詢與巢狀結構解析 | `config.get("agents-workflow", "paths.plans")` 正確解析 | `Passed` |
| **FT-02** | 功能測試 | Local > Project 雙層深層合併 | Local 優先覆蓋 Project 同名鍵，未覆蓋者完整保留 | `Passed` |
| **FT-03** | 功能測試 | Config SDK 寫入與原子取代 | `config.set()` 寫入對應層級檔案，刷新快取無髒讀 | `Passed` |
| **FT-04** | 功能測試 | 部署引擎掃描 `configurable/` 模板 | `act_deploy_configs_from_modules()` 部署至 `config://` 並物理刪除模板目錄 | `Passed` |
| **FT-05** | 功能測試 | 專案特化 `contribute.json` 覆蓋注入 | `ContributesAggregator` 階層 ② 改讀 `config://<mod>/contribute.json` | `Passed` |
| **FT-06** | 功能測試 | 消費端 100% 收斂至 SDK | `core.uri`, `knowledge-db`, `agents-workflow` 無手寫組態讀寫 | `Passed` |
| **FT-07** | 功能測試 | CLI 工具鏈運作 | `python yscb.py config list/get/set` 正確輸出與修改 | `Passed` |
| **ET-01** | 異常測試 | 設定檔缺失安全回退 | 檔案不存在時回傳 `default` 值，不拋出未捕獲例外 | `Passed` |
| **ET-02** | 異常測試 | 損毀 JSON 容錯隔離 | 遇到語法錯誤 JSON 時輸出警告日誌，回傳 `default` | `Passed` |
| **RT-01** | 回歸測試 | 全模組沙盒回歸 | 4 大模組 172/172 測試全綠通過 | `Passed` |

---

## 3. 測試執行紀錄 (Execution Log)

```text
======================================================================
YS-Codebase Test Execution Diagnostic Report
======================================================================
[*] Mode: Default (LOGIC + ENV) | Target: All | Build: Hermetic Build
----------------------------------------------------------------------
[*] Module: agents-workflow (11.04s)                            [PASS]
    |-- [Contract] Auto-Contract Suite ... (3/3)
    \-- [Custom]   Custom Tests ........... (29/29)
[*] Module: core (1.45s)                                        [PASS]
    |-- [Contract] Auto-Contract Suite ... (3/3)
    \-- [Custom]   Custom Tests ........... (54/54)
[*] Module: dev (7.98s)                                         [PASS]
    |-- [Contract] Auto-Contract Suite ... (3/3)
    \-- [Custom]   Custom Tests ........... (40/40)
[*] Module: knowledge-db (10.52s)                               [PASS]
    |-- [Contract] Auto-Contract Suite ... (3/3)
    \-- [Custom]   Custom Tests ........... (37/37)
----------------------------------------------------------------------
Summary : 172 Total, 172 Passed, 0 Failed, 0 Skipped (12.979s)
Status  : PASSED (100% Ready)
======================================================================
```

- [ ] **UX-01 (CLI 指令與 Config 操作手感驗證)**：
  - 實機執行 `python yscb.py config list`、`python yscb.py config get agents-workflow paths` 與 `python yscb.py config set core project_root ./`。
  - 驗證控制台輸出格式工整、錯誤提示清晰，且修改能即時反映至全系統運作。
