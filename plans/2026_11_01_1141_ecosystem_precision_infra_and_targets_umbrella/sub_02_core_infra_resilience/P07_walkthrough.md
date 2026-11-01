# 成果展示與結案報告 (Walkthrough)

> 功能名稱：core / dev / server 基礎設施韌性、跨分支 cmd_restore 自癒與 Windows 句柄釋放加固  
> 建立日期：2026-11-01  
> 所屬主計畫：2026_11_01_1141_ecosystem_precision_infra_and_targets_umbrella  
> 狀態：Completed  
> 模型：Gemini 4 Argon (Low)  

> 模板版本：v1.4  

---

## 1. 變更概述 (Executive Summary)

- **核心功能落地**：
  1. **跨分支 `restore` 版號比對與 Windows 安裝前 Server 句柄釋放 (`TODO-07`)**：於 `yscb.py` 與 `core/installer.py` 之 `cmd_restore` 比對已安裝 `.modules/<name>/manifest.json` 版號與 `lock.json` 目標版號，版號不符或 `manifest.json` 損毀時自動覆寫更新；並於 `install` / `update` / `remove` / `restore` 執行前主動呼叫 `_notify_server_release_handles()` 請求常駐 Server 重啟 Warm Worker 釋放 `.pyd`/`.dll` 句柄，且於 `_atomic_swap_dir` / `act_reload` 非阻塞清理 `.old_*` 殘留目錄。
  2. **`PipInstallError` 例外契約統一 (`TODO-11`)**：將 `core/pip_manager.py` 中 `_bootstrap_pip` 與 `ensure_venv` 失敗拋出之 `RuntimeError` 統一為 `PipInstallError`，使 `Installer.sync_pip_dependencies` 優雅攔截並降級為 `[core:pip] Warning:`。
  3. **檢核失敗報告尾端 `[Agent Directive]` 技能路由注入 (`TODO-12`)**：於 `core/validator.py` (`ValidationResult.format_report`) 與 `dev/checker.py` (`CheckReport`) 檢核失敗時尾端注入 `[Agent Directive]`，引導 AI Agent 遵循 `yscb-module-dev` 進行修復。
  4. **`core.vfs` 本地實體代理與遠端快取物化邊界定錨 (`TODO-03`)**：清除 `core/vfs/vfs.py` 過時註解，並更新 `docs/core/README.md` 與 `docs/core/uri_protocols.md`。

---

## 2. 變更檔案清單 (Changed Files Inventory)

| 檔案路徑 | 變更類型 | 變更說明 |
| :--- | :---: | :--- |
| `yscb.py` | Modify | `cmd_restore` 校驗已安裝 `manifest.json` 版號，並於還原前通知 Server 釋放句柄 |
| `ys_codebase/source/core/core/installer.py` | Modify | `cmd_restore` 版號比對、新增 `_notify_server_release_handles` 與 `_cleanup_stale_old_dirs` |
| `ys_codebase/source/core/core/engine.py` | Modify | `_atomic_swap_dir` 與 `act_reload` 強化 `.old_*` / `.staging_*` 非阻塞清理 |
| `ys_codebase/source/core/core/pip_manager.py` | Modify | `_bootstrap_pip` 與 `ensure_venv` 失敗統一拋出 `PipInstallError` |
| `ys_codebase/source/core/core/validator.py` | Modify | `ValidationResult.format_report` 失敗時附加 `[Agent Directive]` |
| `ys_codebase/source/core/core/vfs/vfs.py` | Modify | 定錨 `core.vfs` 職責註解並移除過時 `MemoryBackend` 描述 |
| `ys_codebase/source/dev/dev/checker.py` | Modify | `CheckReport` 失敗時附加 `[Agent Directive]` 與 `agent_directive` 欄位 |
| `ys_codebase/source/core/tests/test_{installer,engine,venv_core,validator}.py` | Modify | 新增跨分支 `restore`、句柄釋放、`PipInstallError` 與 `[Agent Directive]` 測試 |
| `ys_codebase/source/dev/tests/test_checker.py` | Modify | 新增 `CheckReport` `[Agent Directive]` 斷言測試 |
| `docs/core/{README.md,uri_protocols.md,DESIGN_NOTES.md}` | Modify | 同步更新 `core.vfs` 契約、跨分支 `restore` 與句柄釋放機制 |
| `docs/dev/README.md` | Modify | 同步更新 `dev check` 失敗時之 `[Agent Directive]` 說明 |

---

## 3. 測試與品質驗證結果 (Verification & Quality Audit)

- **自動化測試通過率**：`core` 全量 208 項測試 (`Pass: 208(100.0%), Fail: 0`) 與 `dev` 全量 80 項測試 (`Pass: 80(100.0%), Fail: 0`) 100% 通過；`dev check core` 與 `dev check dev` 100% `PASSED`。
- **實機 UX / 人工驗證**：`UX-01` 實機執行 `python yscb.py restore` 與 `contributes check` 驗證版號比對跳過與 Server Warm Worker 句柄釋放運作無誤，開發者確認 `[測試通過]`。

---

## 4. SOP Review 三層文檔與品質審查 (Three-Tier Review)

### 4.1 三層文檔交付對齊表
| 維度 | 文件路徑 | 交付狀態 | 驗收重點 |
| :--- | :--- | :---: | :--- |
| **宏觀 (Macro)** | `CHANGELOG.md` | 已完成 | 登載 `sub_02` 基礎設施韌性、跨分支 `restore` 與 `[Agent Directive]` 亮點 |
| **中觀 (Meso)** | `docs/core/README.md`, `docs/dev/README.md` | 已完成 | 更新 `restore` 版號校驗、`core.vfs` 定位與 `dev check` 指引 |
| **中觀 (Meso)** | `docs/core/uri_protocols.md` | 已完成 | 明確定義 `core.vfs` 本地檔案代理與遠端轉本地快取物化契約 |
| **中觀 (Meso)** | `docs/core/DESIGN_NOTES.md` | 已完成 | 記錄 Windows 安裝前 Server 句柄釋放與 `.old_*` 非阻塞回收防坑設計 |
| **微觀 (Micro)** | 源碼 Public API / 函式註解 | 已完成 | 嚴格維護 Docstring，標註動機理由 |

### 4.2 品質與清理檢核
- [x] **代碼清理**：無死代碼、無除錯 print/log、無敷衍之 quick-and-dirty hack。
- [x] **測試完整覆蓋**：所有單元測試與整合測試 100% 通過，無跳過或被破壞之斷言。

---

## 5. 推薦 Commit 訊息 (Conventional Commit Format)

```text
fix(core,dev): verify module versions in restore, release server handles before swap, and inject agent directives
```

---

## 6. 計畫結構合規檢核 (Plan Compliance Verification)

- [x] **完成狀態確認**：所有前置階段、代碼實作、SOP 審查與測試驗證均已落實完成，本檔其餘檢核項已勾選 `[x]` 且頂部標頭 `> 狀態：` 已設為 `Completed`。
- [x] **結構與註解檢核（最終守門）**：最後實機執行 `python yscb.py agents-workflow plan verify 2026_11_01_1141_ecosystem_precision_infra_and_targets_umbrella/sub_02_core_infra_resilience` 驗證 100% Passed（若檢出未通過項則原地修正重驗）。

