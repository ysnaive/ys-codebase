# 成果展示與結案報告 (Walkthrough)

> 功能名稱：全生態系模組 CLI 活躍執行合約遷移與向後相容過渡層徹底拔除  
> 建立日期：2026-09-07  
> 所屬主計畫：2026_09_07_0831_quality_update  
> 狀態：Completed  
> 模板版本：v1.4  

---

## 1. 變更概述 (Executive Summary)

- **核心功能落地**：
  1. **生態系三大模組（`dev`, `knowledge-db`, `agents-workflow`）全面升級活躍執行合約**：
     - 重構 `source/<mod>/scripts/cli.py`，全面實作強型別精確命令函式 `cmd(cmd_bags: CmdBags) -> int`。
     - 徹底移除舊 `process(args)` 進入點，全生態系 5 大模組 CLI 實作達成 100% 規格同構。
  2. **Contributes Commands 規範就地納管**：
     - 於各模組 `contributes/core.json` 完整宣告 `commands`（含層級描述、`tier` 安全等級、`args` 規格、`options` 正交互斥群組與 `usage` 規範）。
     - `knowledge-db` 查詢與分析類唯讀指令（`search`, `status`）宣告 `"server_compatible": true`，支援 sub-50ms 熱轉發。
     - `agents-workflow` 實作同構巢狀指令樹 `plan`（純分支 Help 自動接管，子指令 `plan check` / `plan status` 映射至底線平鋪函式 `plan_check`）。
     - `dev` 正式納管沙盒測試原子指令 `op-test` 與 `op-mksb`。
  3. **剛性守門（Hard Sunset Gate）全面生效**：
     - 自 `core.commands.dispatcher` 徹底刪除雙軌向後相容過渡退化層與 `has_legacy_process` 試探邏輯。
     - 未定義精確函式且非純分支之模組調用，剛性阻斷並拋出 `EC-05` 契約缺失錯誤（退出碼 127）。
  4. **剛性 `.modules` 運行時邊界鎖定與防呆守護**：
     - `yscb.py` 與 `dispatcher.py` 嚴格限定僅允許從 `.modules/` 運行時空間載入，徹底根除向 `source/` 兜底的任何 fallback 與路徑注入。
     - 加入全域剛性架構約束註解，落實「虛擬機測試 (`dev test`) $\to$ `install @build` $\to$ 實機測試」鐵律。
     - 復原 `_maybe_auto_spawn_server` 背景非同步按需拉起機制，兼顧常駐服務熱轉發。

---

## 2. 變更檔案清單 (Changed Files Inventory)

| 檔案路徑 | 變更類型 | 變更說明 |
| :--- | :---: | :--- |
| `source/dev/contributes/core.json` | Modify | 宣告 `dev` 所有頂層指令、正交選項與 `op-test`/`op-mksb` 原子命令 |
| `source/dev/scripts/cli.py` | Modify | 改寫為精確命令函式接收 `CmdBags`，徹底拔除 `process(args)` |
| `source/knowledge-db/contributes/core.json` | Modify | 宣告 `knowledge-db` 完整命令樹，查詢指令標記 `server_compatible: true` |
| `source/knowledge-db/scripts/cli.py` | Modify | 改寫為精確命令函式接收 `CmdBags`，徹底拔除 `process(args)` |
| `source/agents-workflow/contributes/core.json` | Modify | 宣告 `agents-workflow` 指令樹，建立 `plan` 巢狀同構子指令結構 |
| `source/agents-workflow/scripts/cli.py` | Modify | 改寫為精確命令函式接收 `CmdBags`，實作底線平鋪子函式，徹底拔除 `process(args)` |
| `source/core/core/commands/dispatcher.py` | Modify | 徹底刪除 `process` fallback 達成 Hard Sunset，鎖定 `.modules` 邊界，補齊 `_maybe_auto_spawn_server` |
| `source/core/core/commands/help.py` | Modify | 優化動態 options 渲染，當無選項時顯示 `(No options available)` |
| `source/core/tests/test_core_commands.py` | Modify | 將 FT-08 更新為嚴格斷言 EC-05 契約缺失（退出碼 127） |
| `source/server/scripts/cli.py` | Modify | 移除背景守護模式中殘留的 `source/core` fallback |
| `source/server/tests/test_server.py` | Modify | 修正測試樁路徑至 `.modules/mock_exit` 符合運行空間邊界 |
| `yscb.py` | Modify | 僅允許注入 `.modules/core`，加入剛性防呆架構註解，阻斷 `source/core` 插入 |

---

## 3. 測試與品質驗證結果 (Verification & Quality Audit)

- **自動化測試通過率**：**100% (486 / 486 綠燈通過)**
  - `core`: 162/162 Passed
  - `dev`: 83/83 Passed
  - `knowledge-db`: 144/144 Passed
  - `agents-workflow`: 74/74 Passed
  - `server`: 23/23 Passed
- **靜態合規檢核 (`dev check`)**：全生態系 5 大模組全部 **100% PASSED**。
- **實機 UX / 人工驗證**：
  - `UX-01`：**`[測試通過]`** 開發者實機驗收 `dev`、`knowledge-db`、`agents-workflow` 與 `server` 各命令之格式化 Help 說明，排版優雅清晰無誤。
  - `UX-02`：**`[測試通過]`** 開發者實機驗收 `agents-workflow plan check`、`server status`、`list` 與背景自動喚醒機制無誤。

---

## 4. 📚 知識庫文檔交付驗收對齊表 (Documentation Delivery Audit)

| 維度 | 文件路徑 | 交付狀態 | 驗收重點 |
| :--- | :--- | :---: | :--- |
| **模組手冊** | `docs/core/README.md` | ✅ 已交付 | 更新 `core.commands` 活躍合約架構與剛性守門 |
| **專題手冊** | `docs/core/cli_commands_architecture.md` | ✅ 已交付 | 記錄生態系全模組遷移指引與 Hard Sunset 規範 |
| **設計決策** | `docs/core/DESIGN_NOTES.md` | ✅ 已交付 | 記錄 [DN-22] 活躍合約全面遷移與 [DN-23] 運行空間剛性隔離 |
| **發布日誌** | `CHANGELOG.md` | ✅ 已交付 | 記錄 1.1.0 重構版本核心變更歷程 |

---

## 5. 推薦 Commit 訊息 (Conventional Commit Format)

```text
refactor(ecosystem): migrate all modules to core.commands contract and hard sunset legacy process fallback

- Refactor dev, knowledge-db, agents-workflow CLI scripts to precise command functions with CmdBags
- Declare standard contributes/core.json commands schema with orthogonal options and server_compatible flags
- Hard sunset dual-track legacy fallback in dispatcher.py, strictly returning EC-05 (exit 127)
- Rigidly enforce .modules runtime space across yscb.py and dispatcher.py with zero source fallback
- Restore background auto-spawn daemon mechanism for non-server commands in dispatcher.py
- Full regression passed across all 5 ecosystem modules (486 tests, 100% Green)
```

---

## 6. 計畫結構合規檢核 (Plan Compliance Verification)

- [x] **結構與註解檢核**：實機執行 `python yscb.py agents-workflow plan check 2026_09_07_0831_quality_update` 驗證 100% Passed。
