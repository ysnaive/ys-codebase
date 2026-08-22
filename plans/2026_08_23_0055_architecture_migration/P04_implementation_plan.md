# 最終實作計畫書 (Implementation Plan)

> 功能名稱：架構轉型遷移、SOP 規範對齊、Dogfooding 流水線與 Changelog 防呆加固  
> 建立日期：2026-08-23  
> 所屬主計畫：無  
> 狀態：Confirmed  
> 擴充項目：none (本計畫產出 dogfooding_pipeline_ext)  
> 模板版本：v1.4  

---

## 1. 交叉驗證與架構檢核 (Cross-Verification Checklist)

- [x] **FR 對齊**：P01 每個功能需求 (FR-01 ~ FR-06) 在 P03 均有對應的檔案契約與介面定義。
- [x] **EC 防護**：P01 每個 Edge Case (EC-01 ~ EC-03) 在 P03/P06 均有明確的測試策略與報錯定義。
- [x] **架構一致**：P02 變更清單與 P03 檔案路徑一致，且完全符合三層空間隔離規範。
- [x] **規範約束**：100% Python 3.8+ 標準庫（零第三方依賴），`AGENTS.md` 軟合併定界標記完整保留。
- [x] **Extension 注入**：`dogfooding_pipeline_ext` 之 Stage 1~4 全流程已完整注入下方實作順序與 P06 測試計畫中。

---

## 2. 靈魂拷問 (Stress Test)

> Agent 扮演架構審查員，提出具建設性的潛在坑點問題：

### Q1: 在加固 `verify_plan.py` 檢查 `changelog.md` 後，是否會導致測試套件 `test/test_installer.py` 中先前建立的模擬臨時計畫目錄驗證失敗？
**回答**：已預先盤查 `test/test_installer.py`。在 Task 6 加固 `verify_plan.py` 時，將同步確認測試套件中的模擬目錄均建立標準 `changelog.md`，確保 `test/run_regression.py` 能 100% 通過全量回歸測試！

---

## 3. 實作順序 (按依賴拓撲排序)

> 此表為 Phase 5 實作的**權威依據**。

| 順序 | 實作項目 | 變更檔案與目標 | 品質驗證方式 |
|:---:|:---|:---|:---|
| **Task 1** | 建立 Dogfooding 專案特化擴充文件 | `[NEW]` [extensions/dogfooding_pipeline_ext.md](file:///H:/UseFolder/CodeRepo/ys_codebase/extensions/dogfooding_pipeline_ext.md)<br>`[NEW]` `ys_codebase/source/agents-workflow/workflows/extensions/dogfooding_pipeline_ext.md` | `python yscb_cli.py agents-workflow ext list` 成功解析 |
| **Task 2** | 更新 `Review.md` 規範 | `[MOD]` `ys_codebase/source/agents-workflow/workflows/Review.md` | 步驟 2 引入 `ext list/show`，步驟 3 引入 `docs audit` |
| **Task 3** | 更新 `DocumentationStandards.md` 規範 | `[MOD]` `ys_codebase/source/agents-workflow/workflows/DocumentationStandards.md` | 追加「🛠️ 知識庫定式維護工具鏈」章節 |
| **Task 4** | 更新 `NewPlan.md` 規範 | `[MOD]` `ys_codebase/source/agents-workflow/workflows/NewPlan.md` | Phase 0 步驟 1/2 強制載明伴隨建立 `changelog.md`；Phase 4/7 融入 `docs new-topic` 與 `archive` |
| **Task 5** | 更新 `AGENTS.template.md` 範本 | `[MOD]` `ys_codebase/source/agents-workflow/workflows/templates/AGENTS.template.md` | 定式作業清單補齊 `<docs\|ext>` |
| **Task 6** | 加固 `verify_plan.py` 檢查邏輯 | `[MOD]` `ys_codebase/source/agents-workflow/scripts/verify_plan.py` | 移除 `changelog.md` 略過邏輯，增加存在性與標頭格式檢查 |
| **Task 7** | 更新根目錄 `AGENTS.md` 行為準則 | `[MOD]` [AGENTS.md](file:///H:/UseFolder/CodeRepo/ys_codebase/AGENTS.md) | 補齊定式清單，並於第 4 節寫入 Dogfooding 三層空間與防呆鐵律 |
| **Task 8** | 更新知識庫全域指南與說明 | `[MOD]` [docs/_project/CONTRIBUTING.md](file:///H:/UseFolder/CodeRepo/ys_codebase/docs/_project/CONTRIBUTING.md)<br>`[MOD]` [docs/AgentsWorkflow/DETERMINISTIC_SCRIPTS.md](file:///H:/UseFolder/CodeRepo/ys_codebase/docs/AgentsWorkflow/DETERMINISTIC_SCRIPTS.md) | 補齊 Dogfooding 四步流水線說明；修正舊版路徑 |
| **Task 9** | 執行 Dogfooding Stage 2 打包構建 | `ys_codebase/build/agents-workflow/` | 執行 `python yscb_cli.py installer build agents-workflow`，檢查產物更新 |
| **Task 10** | 執行 Dogfooding Stage 3 全量回歸測試 | `test/run_regression.py` | 實機執行 `python test/run_regression.py`，驗證 23/23 + E2E 100% Passed |
| **Task 11** | 執行 Dogfooding Stage 4 自引用同步 | `modules/agents-workflow/`<br>`.agents/workflows/` | 執行 `installer install agents-workflow --force` 與 `--ide-antigravity` 生成指令 |

---

## 4. 📚 知識庫文檔衝擊與交付規劃 (Documentation Impact Plan)

> 依據 P03 (API 介面)、P05 (實作任務) 與 P06 (測試案例) 投影 7 大知識維度，預排結案時需同步更新或新建之 `docs/` 文件：

| 判定依據 (P03/P05/P06 錨點) | 知識維度 | 預計更新/新建的文檔路徑 | 具體涵蓋內容 |
| :--- | :--- | :--- | :--- |
| `P03: API 變更 (CONTRIBUTING)` | 維度 6 (操作引導) | `docs/_project/CONTRIBUTING.md` | 補齊 Dogfooding 四步流水線 (源碼 ➔ build ➔ regression ➔ install) 實例與圖解 |
| `P05: 定式工具加固` | 維度 6 (操作引導) | `docs/AgentsWorkflow/DETERMINISTIC_SCRIPTS.md` | 修正舊版路徑為統一 `python yscb_cli.py agents-workflow ...`，追加 `docs` 與 `ext` 工具指令說明 |
| `P05: 知識庫維護標準更新` | 維度 4 (合約承諾) | `docs/AgentsWorkflow/README.md` | 補齊最新定式工具庫索引與 `dogfooding_pipeline_ext` 說明 |
| `P07: 全域知識地圖同步` | 維度 1 (領域模型) | `docs/README.md` | 知識地圖確認對齊最新規範狀態 |

---

## 5. 關鍵決策速查 (Decision Records Reference)

- **[REQ:DR-01]** 確立 Dogfooding 雙層防禦體系（`AGENTS.md` 專案特化規範 + `dogfooding_pipeline_ext.md` 動態 Checkpoint）。
- **[REQ:DR-02]** 確立 `changelog.md` 伴隨 Phase 0 剛性初始化與 `verify_plan.py` 加固。
- **[API:DR-01]** `verify_plan.py` 對 `changelog.md` 執行存在性與結構化檢查。
- **[API:DR-02]** `NewPlan.md` Phase 0 步驟 2 定義雙星伴隨初始化契約 (Mandatory Co-Initialization)。
