# 成果展示與結案報告 (Walkthrough)

> 功能名稱：sub_01_core_microkernel_and_tests  
> 建立日期：2026-10-24  
> 所屬主計畫：2026_10_23_1122_ecosystem_modules_hardening_and_test_purification  
> 狀態：Completed  
> 模型：Gemini 4 Argon (Low)  

> 模板版本：v1.4  

---

## 1. 變更概述 (Executive Summary)

- **核心功能落地**：
  - **微內核去耦合與死代碼清除 (`C-01`, `FR-01`, `T-03`)**：自 `core/providers.py` 移除 11 個未被呼叫的 `agents-workflow` 專屬階段導引函式，自 `core/uri.py` `format_undefined_uri_hint()` 移除 `agents-workflow` 硬編碼字串分支，並自 `core/contributes.py` 與 `core/__init__.py` 清除已廢棄之 `print_global_help()` 死代碼及 `test_contributes_help.py` 測試墓碑。
  - **CLI 驗證、熱派發與組態診斷強化 (`C-02`~`C-06`, `FR-02`~`FR-06`)**：擴充 `contributes check` 單檔與模組模式支援 `config://<target>/contribute.json` 專案層級覆寫檢驗與外殼剝離（`EC-01`/`EC-02`）；修復 `dispatcher._try_hot_dispatch` 支援 `cmd_path: List[str]` 多層子指令路徑傳遞（`EC-03`）；實作 `Installer.cmd_list(remote=True)` 遠端套件探測（`EC-04`）並修正 `cmd_update()` 先執行 `act_reload` 再執行 `act_migrate` 之遷移時序；於 `core/scripts/cli.py` 與 `contributes/core.json` 補齊 `config list --local`、`config inspect`、`config unset`（`EC-05`/`EC-06`），並於 `dispatcher.py` Step 8 統一攔截群組節點未知子命令（`EC-07`）與無參數 `HelpRenderer` 渲染。
  - **`core/tests/` 測試套件純化收斂 (`T-01`~`T-06`, `FR-07`~`FR-10`)**：刪除 `test_contributes_help.py` 並將 7 個碎片測試檔無損收斂至對應子系統測試檔，實質改寫 5 個虛假/過寬測試、清除跨模組 `agents-workflow` patch 依賴、補齊 `test_config.py` 等沙盒隔離與 `tearDown`/`try...finally` 保護，並新增 `contributes check` 負向攔截、`OptionResolver` `--` 與布林反轉、`cmd_update` 端到端升級與 Major Lock 測試。

---

## 2. 變更檔案清單 (Changed Files Inventory)

| 檔案路徑 | 變更類型 | 變更說明 |
| :--- | :---: | :--- |
| `ys_codebase/source/core/core/providers.py` | Modify | 移除 `get_phase_cli_guide` 與 `get_phase00`~`get_research_cli_guide` 等 11 個遺留函式 |
| `ys_codebase/source/core/core/uri.py` | Modify | 移除 `format_undefined_uri_hint()` 中對 `agents-workflow` 之硬編碼特判 |
| `ys_codebase/source/core/core/contributes.py` | Modify | 移除死代碼 `print_global_help()` |
| `ys_codebase/source/core/core/__init__.py` | Modify | 移除 `print_global_help` 匯出 |
| `ys_codebase/source/core/core/commands/contributes_cmd.py` | Modify | 支援 `config://<target>/contribute.json` 父目錄模組推導、外殼剝離與不存在目標報錯 (`EC-01`, `EC-02`) |
| `ys_codebase/source/core/core/commands/dispatcher.py` | Modify | `_try_hot_dispatch` 支援 `cmd_path: List[str]` 並於 Step 8 統一攔截群組未知子命令 |
| `ys_codebase/source/core/core/installer.py` | Modify | 實作 `cmd_list(remote=True)` (`C-04`/`EC-04`) 並修正 `cmd_update` 遷移腳本於 `act_reload` 後執行 |
| `ys_codebase/source/core/contributes/core.json` | Modify | 宣告 `config inspect` 與 `config unset` 子命令 Schema |
| `ys_codebase/source/core/scripts/cli.py` | Modify | 實作 `config_inspect`、`config_unset`、接入 `config_list --local` 與群組無參數 `HelpRenderer` |
| `ys_codebase/source/core/tests/*` | Modify / Delete | 收斂 7 個碎片測試檔與刪除 1 個墓碑檔，完成 `T-01`~`T-06` 實質斷言與補盲（193 Passed） |
| `ys_codebase/source/core/README.md` | Modify | 同步 `list --remote`、`config inspect` 與 `config unset` CLI 範例 |
| `docs/core/README.md` | Modify | 同步 `list --remote`、`config inspect` 與 `config unset` CLI 手冊說明 |
| `docs/core/DESIGN_NOTES.md` | Modify | 新增 `[DN-13]` 記錄專案層級 `contribute.json` 單檔校驗之父目錄推導與剝殼機制 |

---

## 3. 測試與品質驗證結果 (Verification & Quality Audit)

- **自動化測試通過率**：`python yscb.py dev check core` **PASSED**；`python yscb.py dev test core -q` **193 Passed (100.0%), 0 Fail, 0 Skip**。
- **實機 UX / 人工驗證**：完成 `core@build` 熱部署，實機執行 `python yscb.py config inspect core project_root` 驗證通過。

---

## 4. SOP Review 三層文檔與品質審查 (Three-Tier Review)

### 4.1 三層文檔交付對齊表
| 維度 | 文件路徑 | 交付狀態 | 驗收重點 |
| :--- | :--- | :---: | :--- |
| **宏觀 (Macro)** | `CHANGELOG.md` | 已更新 | 追加 `2026_10_23_1122` / `sub_01_core_microkernel_and_tests` 結案摘要 |
| **中觀 (Meso)** | `docs/core/README.md`、`ys_codebase/source/core/README.md` | 已更新 | 模組手冊、架構與新增 CLI 指令說明同步 |
| **中觀 (Meso)** | `docs/core/[topic].md` | 免更 | 無新增獨立專題手冊需求 |
| **中觀 (Meso)** | `docs/core/DESIGN_NOTES.md` | 已更新 | 新增 `[DN-13]` 記錄專案級 `contribute.json` 單檔校驗剝殼設計 |
| **微觀 (Micro)** | 源碼 Public API / 函式註解 | 已更新 | 嚴格維護 Docstring，標註動機理由 |

### 4.2 品質與清理檢核
- [x] **代碼清理**：無死代碼、無除錯 print/log、無敷衍之 quick-and-dirty hack（通過 Pillar 3 Fresh-Eyes Review：`REVIEW_STATUS: PASSED`）。
- [x] **測試完整覆蓋**：所有單元測試與整合測試 100% 通過，無跳過或被破壞之斷言。

---

## 5. 推薦 Commit 訊息 (Conventional Commit Format)

```text
refactor(core): purify microkernel, harden CLI dispatcher/config/contributes, and consolidate test suite (sub_01)
```

---

## 6. 計畫結構合規檢核 (Plan Compliance Verification)

- [x] **完成狀態確認**：所有前置階段、代碼實作、SOP 審查與測試驗證均已落實完成，本檔其餘檢核項已勾選 `[x]` 且頂部標頭 `> 狀態：` 已設為 `Completed`。
- [x] **結構與註解檢核（最終守門）**：最後實機執行 `python yscb.py agents-workflow plan verify 2026_10_23_1122_ecosystem_modules_hardening_and_test_purification/sub_01_core_microkernel_and_tests` 驗證 100% Passed（若檢出未通過項則原地修正重驗）。

