# 需求規格說明書 (Requirements Specification)

> 功能名稱：sub_05_jit_self_healing_integration  
> 建立日期：2026-09-04  
> 所屬主計畫：2026_09_02_0533_ecosystem_hot_update_git_decoupling_and_pip_governance  
> 狀態：Confirmed  
> 依據 P00：[P00_discuss.md](./P00_discuss.md)  
> 模板版本：v1.5  

---

## 1. 功能需求清單 (Functional Requirements)

| 需求編號 | 需求名稱 | 詳細規格描述 | 優先級 | 對應 P00 語意 |
| :--- | :--- | :--- | :---: | :--- |
| **FR-01** | `core.events` 獨立微內核模組與 `Engine` 徹底解耦 | 新增獨立輕量模組 `core.events`，提供 `broadcast(event_name, context=None, emit_module="core", search_roots=None)`。完全從 `core.engine.Engine` 抽離，並徹底移除 `Engine.act_broadcast_event` 門面，達成微內核徹底解耦；原呼叫端（`installer.py`、`engine.py`）直接調用 `core.events.broadcast`。標準 Hook 尋址定義為 `module://<module>/scripts/hook.<Sender>.py`，函式簽名支援 `on_{event_name}` 與 `{event_name}` 雙向匹配。 | P0 | [P00:DR-02] |
| **FR-02** | 宿主 `yscb.py` 入口生命週期管線收斂 | 在 `yscb.py` 的命令分發流程中建立標準前置與後置生命週期管線：分發前依序執行微環境路徑注入、運行端完整性嗅探自癒 (`_ensure_jit_modules_sync`)，並透過 `core.events.broadcast("pre_cli_dispatch")` 廣播事件；命令執行完畢後執行後置事件（廣播 `post_cli_dispatch` 並進行非阻塞 12 小時更新提示）。 | P0 | [P00:DR-02], [P00:DR-03] |
| **FR-03** | `agents-workflow` 對齊標準 Core Event Hook 並清理 Ad-hoc 攔截 | 於 `agents-workflow` 的 `scripts/hook.core.py` 中實現 `on_pre_cli_dispatch(ctx)` 處理常式，調用 `ensure_jit_release()` 執行 JIT 資產指紋檢測與自癒物化；徹底移除 `agents_workflow/scripts/cli.py` 中原有的 Ad-hoc JIT 攔截代碼，回歸正規生命週期調度。 | P0 | [P00:DR-02], [P00:DR-03] |
| **FR-04** | `dev` 沙盒測試 Hook 統一收斂至 `core.events` | 移除 `dev.testing.sandbox.SandboxProvisioner._dispatch_test_hooks` 重複造輪子之實作，改為直接調用 `core.events.broadcast(hook_name, ctx, emit_module="dev", search_roots=[...])`，達成跨模組事件基礎設施統一。 | P0 | [P00:DR-02] |
| **FR-05** | `core` 擴充 `events` contribute 規範與 `event list` 查表 CLI | 在 `core` 模組 `contribute.json` 與 `contributes.format.md` 擴充宣告格式 `events: list[{"<name>": "description"}]`（純資料查表宣告）；於 `yscb.py` 新增 `event list`（或 `core events`）指令，自動從 `contributes` 聚合並格式化輸出全生態系可派送之事件清冊。 | P1 | [P00:DR-02] |
| **FR-06** | `core.contributes` JIT 快照自癒與生命週期管線協同 | 確保在 `pre_cli_dispatch` 生命週期廣播時，若涉及 contributes 快照變更，能平穩即時自癒；保持 `core.contributes.get()` 既有的讀取時惰性自癒機制互不干擾，維持雙層防護。 | P1 | [P00:DR-02], [P00:DR-03] |

---

## 2. 邊界與異常情況 (Edge Cases & Failure Modes)

| 邊界編號 | 情境說明 | 預期防禦與處理行為 |
| :--- | :--- | :--- |
| **EC-01** | 模組尚未安裝或缺少 `scripts/hook.<Sender>.py` | 事件管線自動安全略過該模組，不拋出任何異常，不阻塞主流程。 |
| **EC-02** | 模組 Hook 內部執行拋出異常 (例如自癒物化失敗或檔案鎖定) | `core.events.broadcast` 以 Warning 日誌捕獲異常，絕不阻斷宿主 CLI 的後續指令分發與執行。 |
| **EC-03** | 宿主初次執行 `init`、`restore` 或 `bootstrap` 等自舉指令 | 自動短路跳過前置 `pre_cli_dispatch` 廣播，避免因模組或 `core` 尚未就緒引發連鎖錯誤。 |
| **EC-04** | 極速跳過機制（Clean 狀態零開銷） | 各模組在 `on_pre_cli_dispatch` 處理常式中必須具備指紋/快照提前短路機制，若未發生實質變更則在 $\le 1\text{ms}$ 內返回，杜絕 CLI 調用卡頓。 |
| **EC-05** | 未定義 `events` contribute 節點之模組執行 `event list` | 優雅容錯，僅顯示有宣告 `events` 之中繼資訊，不中斷查表流程。 |

---

## 3. 非功能需求 (Non-Functional Requirements)

| 需求編號 | 類別 | 指標與量化約束 |
| :--- | :--- | :--- |
| **NFR-01** | 效能 / 延遲 | 全套 `pre_cli_dispatch` 生命週期廣播與嗅探在 Clean（無變更）狀態下，總體耗時必須 $\le 5\text{ms}$，維持 sub-100ms CLI 響應保證。 |
| **NFR-02** | 依賴邊界 | 100% 維持純 Python 標準庫實作，嚴禁為事件管線引入任何外部第三方 Pip 依賴。 |
| **NFR-03** | 架構純淨性 | Hook 註冊與執行 100% 走 `scripts/hook.<Sender>.py` 動態管線；`contributes.events` 純粹作為宣告式文檔與 CLI 查表用途，程式執行期零強依賴。 |

---

## 4. 知識庫與踩坑紀錄查閱 (Known Gotchas & CAUTIONs)

- **`[!NOTE]`** `yscb.py` 採用同進程 `runpy.run_path` 調度分發，因此事件廣播在同進程記憶體中執行，模組間透過 `hook.core.py` 獨立隔離載入。
- **`[!IMPORTANT]`** `pre_cli_dispatch` 事件必須在模組 CLI `runpy.run_path` 執行前觸發，使目標模組執行前環境（如 `.agents/` 目錄資產）已完成自癒。
- **`[!CAUTION]`** 在執行 `agents-workflow release`、`compile` 等發布或構建指令本身時，Hook 內的 `ensure_jit_release` 應避免重複物化或引發遞迴衝突。

