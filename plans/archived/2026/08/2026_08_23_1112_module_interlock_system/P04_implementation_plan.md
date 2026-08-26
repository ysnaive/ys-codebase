# 最終實作計畫書 (Implementation Plan)

> 功能名稱：Module 安裝期連動系統設計 (Installation-time Interlock System)  
> 建立日期：2026-08-23  
> 所屬主計畫：無  
> 狀態：Confirmed  
> 擴充項目：dogfooding_pipeline_ext  
> 模板版本：v1.4  

---

## 1. 交叉驗證與架構檢核 (Cross-Verification Checklist)

- [x] **FR 對齊**：P01 之 FR-01~FR-08 在 P03 均有對應的類別、函式簽名與合約規格。
- [x] **EC 防護**：P01 之 EC-01~EC-08（包含 Hook 缺漏、例外隔離、格式損壞、檔案遺失、同 Slot 衝突等）在 P03 均有明確的例外處理與防禦機制。
- [x] **架構一致**：P02 劃分之 3 層解耦架構與 P03 介面定義一致，依賴拓撲已完整驗證。
- [x] **規範約束**：100% 使用純標準庫 (Zero External Dependency)，路徑與編碼強制 UTF-8。
- [x] **Extension 注入**：`dogfooding_pipeline_ext` 已納入實作階段的四步標準閉環流水線中。
- [x] **Test-First 定稿**：`P06_test_plan.md` 已完整對齊 FT-01~08, ET-01~08, RT-01, PT-01, UX-01~02 並於本階段剛性定稿。

---

## 2. 靈魂拷問 (Stress Test)

> Agent 扮演架構審查員，提出關鍵潛在坑點問題：

### Q1: 模組卸載時的「孤兒指令與純淨還原」極限情境
**審查問題**：當使用者執行 `python yscb_cli.py installer remove agents-workflow-unity` 卸載外掛模組時，系統如何保證在不重新下載 `agents-workflow` 的前提下，自動將 `.agents/workflows/` 與 `modules/agents-workflow/workflows/` 中的 SOP 還原為純淨版？
**解答**：
1. `workflows/commands/` 是永遠唯讀且自包含的基準庫，不受任何外掛修改。
2. 卸載完成後，Installer 發出 `_broadcast_modules_changed([("removed", "agents-workflow-unity")])`。
3. `agents-workflow` 的 `_on_modules_changed.py` 被觸發，重新從 `workflows/commands/` 讀取基準指令，由於已無 Unity 外掛，合成引擎直接剝除剩餘 Slot 標記並輸出純淨版至 `workflows/*.md`。
4. `IDECacheTracker` 同步比對快取，自動清除因外掛移除而失效的孤兒指令檔案，達成 100% 離線無損還原。

---

## 3. 實作順序 (按依賴拓撲排序)

| 順序 | 實作項目 | 變更檔案與目標 | 品質驗證方式 |
|:---:|:---|:---|:---|
| **Task 1** | Core SDK 跨模組貢獻查詢通道 | `ys_codebase/source/core/yscb_core/context.py` 新增 `get_contributions()` | 單元測試 `test_interlock.py::test_get_contributions` |
| **Task 2** | Installer 批次完成後單次生命週期廣播 | `ys_codebase/yscb_installer.py` 新增 `_broadcast_modules_changed()`（`build` 排除） | 單元測試 `test_interlock.py::test_broadcast_on_install` |
| **Task 3** | SOP Slot 補丁動態合成引擎 | `ys_codebase/source/agents-workflow/scripts/sop_synthesizer.py` 實作 `SOPSynthesizer` | 單元測試 `test_interlock.py::test_sop_synthesizer` |
| **Task 4** | IDE 生成快取與孤兒檔案清理追蹤器 | `ys_codebase/source/agents-workflow/scripts/ide_sync.py` 實作 `IDECacheTracker` | 單元測試 `test_interlock.py::test_ide_cache_tracker` |
| **Task 5** | 雙層 Extension 發現與優先級調度器 | `ys_codebase/source/agents-workflow/scripts/ext_registry.py` 實作 `ExtensionRegistry` | 單元測試 `test_interlock.py::test_extension_registry` |
| **Task 6** | 建立 `workflows/commands/` 基準庫並植入 Slot 標記 | 遷移原始指令至 `commands/`，於 `NewPlan.md`, `Review.md`, `ContextInit.md` 植入 `<!-- YSCB_SLOT:xxx -->` | 靜態標記檢查與正則剝除驗證 |
| **Task 7** | `agents-workflow` 生命週期廣播 Hook | `ys_codebase/source/agents-workflow/scripts/_on_modules_changed.py` 實作接收端與環境感知 | 整合測試 `test_interlock.py::test_on_modules_changed_hook` |
| **Task 8** | 升級 `cli.py` 與 `verify_plan.py` | 整合合成引擎、雙層 Extension 掃描 (`ext list`/`verify`) 與來源標籤排版 | CLI 實機調用與格式審查 |
| **Task 9** | 建立標準 Mock 測試外掛模組 | `test/fixtures/mock_workflow_plugin/`（含 manifest, mock_rules, mock_verify） | 檔案完整性檢查 |
| **Task 10** | 連動系統全量單元與整合測試 | `test/test_interlock.py`（覆蓋 FT-01~08, ET-01~08, PT-01） | `pytest test/test_interlock.py` 100% Passed |
| **Task 11** | Dogfooding 建置、回歸與同步 | 執行 Stage 1~4 Dogfooding 閉環流水線，更新 `test/run_regression.py` | `python test/run_regression.py` 100% Passed (45+ 測試) |

---

## 4. 📚 知識庫文檔衝擊與交付規劃 (Documentation Impact Plan)

依據 P03 (API)、P05 (Tasks) 與 P06 (Tests) 進行 7 大維度投影，明確預排結案時需同步更新或新建之 `docs/` 文件清單：

| 判定依據 (P03/P05/P06 錨點) | 知識維度 | 預計更新/新建的文檔路徑 | 具體涵蓋內容 |
|:---|:---|:---|:---|
| `P03: API / 介面變更` | 維度 2 (邊界與使用) | `docs/Core/README.md` | 補齊 `ProjectContext.get_contributions()` 查詢 API 與用法範例 |
| `P03: API / 介面變更` | 維度 2 (邊界與使用) | `docs/Installer/README.md` | 補齊批次安裝生命週期 Hook `_on_modules_changed.py` 說明 |
| `P05: Task 2 工程妥協` | 維度 5 (工程妥協) | `docs/Installer/DESIGN_NOTES.md` | 登記 `DN-07`（批次完成後單次廣播協定與 build 指令排除鐵律） |
| `P05: Task 3~7 連動協定` | 維度 3 (中觀動態機制) | `docs/AgentsWorkflow/SOP_INTERLOCK_PROTOCOL.md` **[NEW]** | 專題手冊：說明 `contributes.agents-workflow` 剛性 Schema、Slot 標記注入機制、`workflows/commands/` 目錄劃分與 IDE 快取清理流水線 |
| `P05: Task 5, 8 雙層發現` | 維度 3 (中觀動態機制) | `docs/AgentsWorkflow/EXTENSION_VERIFIERS.md` | 更新雙層 Extension 發現鏈（`sop_ext://` 專案自定義優先覆蓋）與 `ext list` 來源標籤規格 |
| `P05: 結案全域同步` | 維度 1 (系統全貌) | `CHANGELOG.md` | 全專案高階變更日誌追加 Module 連動系統與公開協定版本更新摘要 |

---

## 5. 關鍵決策速查 (Decision Records Reference)

- **[REQ:DR-01]** 主機-外掛職責解耦：Installer 零領域知識，Host 模組自主處理合成與調度。
- **[REQ:DR-02]** `build` 指令排除廣播觸發，確保建置產物純淨性與零副作用。
- **[REQ:DR-03]** SOP 注入機制採用剛性 Slot 標記（`<!-- YSCB_SLOT:<name> -->`）取代脆弱的標題關鍵字匹配。
- **[REQ:DR-04]** 多模組同 Slot 衝突排序定義為未定義行為 (Undefined Behavior)，由安裝順序線性疊加。
- **[ARCH:DR-01]** 確立 Installer / Core SDK / Host Module 三層解耦架構。
- **[ARCH:DR-02]** 記憶體即時合成與純淨基準庫防護，模板本體永遠唯讀受保護。
- **[API:DR-01]** 確立 `action:module` CLI 位置參數批次 Delta 傳參協定。
