# 需求規格書 (Requirements Specification)

> 功能名稱：開發者測試框架與全自動契約回歸工作流 (Dev Testing Framework & Regression Workflow)
> 建立日期：2026-08-24
> 所屬主計畫：[2026_08_23_2030_architecture_refactor](../umbrella_overview.md)
> 依據 P00 / 調研報告：[P00_semantic_requirements.md](../P00_semantic_requirements.md) / [R01_uitk_net_testing_survey.md](./R01_uitk_net_testing_survey.md), [R02_testing_architecture_synthesis.md](./R02_testing_architecture_synthesis.md)
> 狀態：Draft
> 擴充項目：none
> 模板版本：v1.4

---

## 功能需求 (Functional Requirements)

| ID | 功能描述 | 輸入 | 處理 | 輸出 | 對應 P00 語意 |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **FR-01** | **測試執行引擎 (`dev test`)** | 模組名 / `--all`、`--type` (logic/sandbox/host/network)、`-k pattern`、`--verbose`、`--keep-sandbox` | 1. 發現指定模組或全模組之 `source/<mod>/tests/test_*.py`。<br/>2. 依據 `--type` 與 `-k` 組織 TestSuite。<br/>3. 動態掛載全自動契約測試與模組自訂測試。<br/>4. 收集執行結果並格式化 ASCII 終端統計表。 | 終端結構化報告與 Exit Code (0/1) | P00 包含範疇 3.4；R01 §2；R02 §3.1 |
| **FR-02** | **全自動標準規格契約守門 (Universal Auto-Contract)** | `source/` 目錄下的模組源碼 | 1. 無需手寫樣板代碼，測試引擎自動對目標模組執行 4 大契約檢驗：<br/>  - Manifest Schema 格式與必備欄位。<br/>  - `scripts/cli.py` 進入點與 `main(argv)` 簽名。<br/>  - AST 零未聲明外部依賴檢查。<br/>  - 純淨建置打包試跑驗證。 | 模組標準合規性驗證結果 | R02 §2.1；R02 §3.3 |
| **FR-03** | **測試基礎類別 (`YSCBTestCase`)** | 繼承 `unittest.TestCase` | 1. `setUp` 自動建立臨時專案沙盒目錄並備份 `sys.path` / `os.environ`。<br/>2. `tearDown` 強制恢復全域環境，杜絕跨測試狀態污染。<br/>3. 提供專屬斷言庫：`assertSuccess`, `assertInOutput`, `assertFileExists`, `assertJsonEquals`。<br/>4. 封裝 `run_cli(argv, cwd)` 支援跨進程/進程內 CLI 呼叫。 | 標準化測試編寫 SDK | P00 包含範疇 3.4；R01 §2.1；R02 §3.2 |
| **FR-04** | **環境能力動態探測 (`@require`)** | `Requirement` 位元旗標 (`NONE`, `SANDBOX`, `HOST_CLI`, `NETWORK`) | 1. 測試方法執行前動態探測運行環境能力。<br/>2. 若環境未滿足（如離線執行 Network 測試），自動調用 `unittest.SkipTest` 優雅跳過，避免 CI 假性紅燈。 | 優雅跳過提示與乾淨測試統計 | R01 §2.2；R02 §3.2 |
| **FR-05** | **沙盒生命週期管理 (Preserve on Failure)** | 測試執行狀態 | 1. 測試案例通過時：`tearDown` 自動清空刪除臨時沙盒，不殘留垃圾。<br/>2. 測試案例失敗時：`tearDown` 完整保留沙盒目錄，並在終端輸出絕對路徑供現場排查。 | 乾淨空間維護與除錯保全 | P00 包含範疇 2.3；R02 §2.3 |
| **FR-06** | **全量回歸品質守門 (Full Regression Gate)** | 全量模組清單 | 1. 提供 `dev test --all`，依 Kahn 依賴拓撲順序依序執行所有模組測試。<br/>2. 作為 `dev build --all` 與發布前的強制阻斷守門閘門。 | 全專案回歸診斷報告 | P00 包含範疇 3.4；R02 §4 |

---

## 非功能需求 (Non-Functional Requirements)

| ID | 類別 | 約束描述 | 驗證方式 |
| :--- | :--- | :--- | :--- |
| **NFR-01** | **零外部依賴** | 100% 基於 Python 3.8+ 標準庫 `unittest` 擴展，嚴禁引入 `pytest` 等第三方套件。 | 靜態 AST import 掃描驗證 |
| **NFR-02** | **執行效能** | 純邏輯單元測試毫秒級 (< 5ms) 執行，全量契約測試 (< 200ms)。 | 執行時間計時斷言 |
| **NFR-03** | **物理空間隔離** | 測試運行期間絕不寫入真實 `source/`、`build/` 或全域組態。 | 檔案變更監控驗證 |

---

## Edge Cases

| ID | 場景描述 | 預期行為 | 對應 FR |
| :--- | :--- | :--- | :--- |
| **EC-01** | 模組無任何自訂 `tests/` 目錄或測試案例 | 自動完成全套「標準規格契約測試」，自訂測試部分輸出 `(No custom tests)` 並回傳 Exit Code 0。 | FR-01, FR-02 |
| **EC-02** | 測試案例引發未捕獲例外或斷言失敗 | 捕獲完整 Traceback，保留該案例專屬沙盒目錄，終端輸出除錯路徑並返回 Exit Code 1。 | FR-01, FR-05 |
| **EC-03** | `-k pattern` 未匹配到任何測試案例 | 終端提示 `No tests matched pattern '<pattern>'` 並優雅返回 Exit Code 0。 | FR-01 |
| **EC-04** | 測試過程修改了全域環境變數或 `sys.path` | `tearDown` 必定執行備份回填，保證後續測試案例環境純淨。 | FR-03 |
| **EC-05** | 在無網路或沙盒圍欄下執行 `@require(Requirement.NETWORK)` 測試 | 自動觸發 `SkipTest`，標記為 `[SKIPPED]`，不計入 Failure。 | FR-04 |

---

## 專案擴充特化判定矩陣 (Extension Specialization Matrix)

| 擴充項目名稱 | 觸發模式 | 本計畫適用性判定 | 納入 / 排除具體理由 |
| :--- | :--- | :--- | :--- |
| `sop_ext` 清單 | `on_demand` | ❌ 排除 (Excluded) | 本子計畫為測試引擎 SDK，不涉及業務領域特化擴充 |

---

## Decision Records

### [P01:DR-01] 4 大運行階層 + 1 全量回歸守門架構
- **議題**：測試引擎應如何劃分測試運行模式與環境依賴？
- **結論**：劃分為 `Level 1: Logic (純邏輯)`、`Level 2: Sandbox (進程內沙盒)`、`Level 3: Host CLI (宿主子進程)`、`Level 4: Network (遠端網路)` 與 `Level 5: Full Regression (全量回歸)`。
- **理由**：兼顧開發即時反饋效率（毫秒級）與完整跨進程 E2E 真實度，支援靈活分流執行。

### [P01:DR-02] 全自動模組標準契約守門 (Universal Auto-Contract)
- **議題**：模組契約測試應由開發者手動繼承編寫，還是由測試引擎全自動執行？
- **結論**：由 `TestRunner` 對 `source/` 下所有模組全自動動態掛載並執行 4 大核心契約檢驗，達成**零樣板代碼、不可跳過之剛性守門**。
- **理由**：杜絕人為遺漏，降低套件開發者門檻。

### [P01:DR-03] 失敗沙盒保留策略 (Preserve on Failure)
- **議題**：測試臨時目錄清理機制為何？
- **結論**：測試通過自動完全刪除；測試失敗時完整保留並輸出絕對路徑供現場排查。
- **理由**：兼顧磁碟清潔與極致除錯體驗。

### [P01:DR-04] Layer 1 全域內建 tests 排除
- **議題**：測試目錄是否需列入 `dev.builder` 內建排除清單？
- **結論**：在 `dev.builder.GLOBAL_IGNORES` 中內建納入 `tests` 與 `tests/*`。
- **理由**：零設定保證發布產物純淨，杜絕測試腳本外溢至生產環境。
