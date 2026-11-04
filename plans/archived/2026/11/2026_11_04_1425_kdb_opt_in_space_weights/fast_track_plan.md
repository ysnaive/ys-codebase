# Fast Track 敏捷開發計畫 (Fast Track Plan)

> 功能名稱：Knowledge-DB 權重空間顯式 Opt-in 索引機制  
> 建立日期：2026-11-04  
> 所屬主計畫：N/A  
> 狀態：Completed  
> 模型：Unknown  

> 計畫類型：Fast Track  
> 模板版本：v1.2  

---

## 1. 敏捷需求與實作計畫 (FP-01 Specification & Plan)

### 1.1 4 大剛性守門合規檢核 (Mandatory 4-Gate Check)
- [x] **修改行數守門**：代碼修改行數預估 $\le 100$ 行（約 65 行）。
- [x] **API 契約守門**：Public API 簽名契約 0 變更（無破壞性與新增導出）。
- [x] **依賴邊界守門**：零跨模組新依賴引入。
- [x] **既有測試守門**：既有單元測試套件 100% 覆蓋守門。

### 1.2 核心需求與邊界
- **需求描述**：
  - [FP-01:DR-01] 將 `knowledge-db` 對 `file-space` 空間的納入策略改為**顯式權重 Opt-in 制**：凡未於 `knowledge-db` 組態（`contributes/knowledge-db.json` 或 `config/knowledge-db/contribute.json` 之 `space_weights`）宣告權重之 `file-space` 空間（如未來專用於雲端鏡像同步之 `cloud` 空間），一律視為不納入 `knowledge-db` 資料庫索引、狀態盤點、打包匯出與 `KNOWLEDGE_DB_SPACE` 提示表。
  - [FP-01:DR-02] 移除 `file-space` 組態中冗餘之 `"weight"` 欄位（`ys_codebase/config/file-space/contribute.json` 與 `ys_codebase/source/agents-workflow/contributes/file-space.json`），使檢索權重 100% 收斂由 `knowledge-db` 的 `space_weights` 單一真理來源管轄。
- **影響範圍**：
  - `ys_codebase/source/knowledge-db/knowledge_db/engine.py`
  - `ys_codebase/source/knowledge-db/knowledge_db/pipeline.py`
  - `ys_codebase/source/file-space/file_space/providers.py`
  - `ys_codebase/config/file-space/contribute.json`
  - `ys_codebase/source/agents-workflow/contributes/file-space.json`
  - `ys_codebase/source/knowledge-db/tests/test_file_space.py`

### 1.3 實作任務與測試規劃
- [x] **TASK-01**：於 `KnowledgeEngine._load_and_merge_space_weights` 與 `get_all_space_weights` 移除自動從 `space_manager.get_all_spaces()` 補齊未宣告權重空間之邏輯（僅保留單元測試顯式傳入 `contributes_data["spaces"]` 且未傳入 `space_weights` 時之測試便利回退），並於 `status()` 與 `bundle()` 僅預設處理具備權重之受索引空間。
- [x] **TASK-02**：於 `IndexingPipeline` 新增 `_get_indexed_space_names` 與 `_filter_symbol_for_indexed_spaces`，在全量建置 (`_build_unified_index_locked`) 與增量熱修補 (`_collect_all_dirty_files`) 過濾未配置權重之空間與符號 `spaces` 標籤。
- [x] **TASK-03**：於 `file_space/providers.py` 之 `get_knowledge_db_spaces` 依據 `knowledge-db` 的 `space_weights` 過濾輸出至 `KNOWLEDGE_DB_SPACE` 的空間清單，並清理 `file-space` 組態檔中冗餘的 `"weight"` 屬性。
- **測試案例清冊**：
  - [x] **FT-01**：驗證未於 `space_weights` 宣告權重之 `file-space` 空間不會被納入 `KnowledgeEngine.status()`、`build_unified_index()`、`search()` 與 `get_knowledge_db_spaces()`，且跨空間重疊檔案僅保留受索引空間標籤（`test_ft_09_opt_in_space_weights_excludes_unweighted_spaces`）。
  - [x] **RT-01**：全模組既有單元測試 100% 回歸通過（`knowledge-db` 109/109、`file-space` 17/17、`agents-workflow` 141/141）。

---

## 2. 實作與驗證成果 (FP-02 Execution & Test Log)

- **實作結果**：完成 `KnowledgeEngine`、`IndexingPipeline` 與 `file_space/providers.py` 之顯式 `space_weights` Opt-in 過濾，並清理 `file-space` 組態中冗餘的 `"weight"` 欄位；以 `@build` 熱部署並完成 `agents-workflow compile` 與 `release --target antigravity --force`。
- **實機測試日誌**：
  - `python yscb.py dev check knowledge-db && python yscb.py dev check file-space && python yscb.py dev check agents-workflow` -> `PASSED`
  - `python yscb.py dev test knowledge-db -q --no-build` -> `Pass: 109(100.0%), Fail: 0, Skip: 0`
  - `python yscb.py dev test file-space -q` -> `Pass: 17(100.0%), Fail: 0, Skip: 0`
  - `python yscb.py dev test agents-workflow -q` -> `Pass: 141(100.0%), Fail: 0, Skip: 0`

---

## 3. SOP Review 審查與結案交付 (Review & FP-03 Closure)

- [x] **SOP Review 品質矩陣**：三層文檔對齊（`docs/` 手冊、`DESIGN_NOTES.md`、微觀註解）、測試 100% 通過。
- [x] **日誌與發布交付**：追加 `CHANGELOG.md` 發布摘要。
- [x] **標頭狀態更新**：完成上述審查並將本清單其餘項勾選 `[x]` 後，將頂部標頭 `> 狀態：` 更新為 `Completed`。
- [x] **結構與註解檢核（最終守門）**：最後實機執行 `python yscb.py agents-workflow plan verify <plan_name>` 驗證 100% Passed（若檢出未通過項則原地修正重驗）。
