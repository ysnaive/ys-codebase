# Fast Track 敏捷開發計畫 (Fast Track Plan)

> 功能名稱：sub_01_knowledge_db_cli_options_and_filtering  
> 建立日期：2026-09-14  
> 所屬主計畫：2026_09_14_0455_downstream_feedback_remediation  
> 狀態：Completed  
> 計畫類型：Level 0 Fast Track  
> 模板版本：v1.2  

---

## 1. 敏捷需求與實作計畫 (FT-1 Specification & Plan)

### 1.1 核心需求與邊界
- **需求描述**：
  - 修復 `knowledge-db` 之 CLI 選項值提取邏輯（ISSUE-01）：在 `scripts/cli.py` 中，使用 `bags.get_option(...)` 被強制轉為字串後會包含 `CmdOption(name=..., params=...)`，導致 `space`、`ftype`、`kind`、`lang`、`limit`、`depth`、`output` 選項失效或轉換為整數時拋出 ValueError 並回退預設值。全面改用 `bags.get_option_value(name, default=None)` 提取純字串值。
  - 解開檢索選項互斥過嚴限制（ISSUE-03）：在 `contributes/core.json` 中，將 `search` 的 `ftype` 選項從 `"scope"` 互斥群組移至獨立群組 `"filter"`，允許 `--space` 與 `--ftype` 複合傳入過濾。
- **4 大守門條件合規核驗**：
  1. 修改檔案數：2 個 (`source/knowledge-db/scripts/cli.py`, `source/knowledge-db/contributes/core.json`) $\le 2$ 個（合規）
  2. 總行數預估：修改 30 行 $\le 100$ 行（合規）
  3. Public API 契約：0 變更，維持現有 API 簽名與呼叫約定（合規）
  4. 既有測試守門：`knowledge-db` 150/150 測試通過率 100% 守門（合規）
- **影響範圍**：`source/knowledge-db/scripts/cli.py`、`source/knowledge-db/contributes/core.json`、`source/knowledge-db/tests/test_cli.py`。

### 1.2 實作任務與測試規劃
- [x] **TASK-01**：修改 `scripts/cli.py`，於 `bundle`、`search`、`callers`、`callees`、`impact` 中全面將 `bags.get_option(...)` 替換為 `bags.get_option_value(...)`。
- [x] **TASK-02**：修改 `contributes/core.json`，將 `search` 指令中的 `ftype` 選項自 `"scope"` 拆分至 `"filter"` 群組。
- [x] **TASK-03**：於 `tests/test_cli.py` 新增 `test_cli_options_extraction_and_orthogonal_filter` 驗證選項提取與複合過濾。
- **測試案例**：
  - `FT-01`：`search` 指令複合使用 `--space` 與 `--ftype` 正常檢索且成功過濾（已於實機與單元測試通過）。
  - `FT-02`：`callers`、`callees`、`impact` 傳入 `--limit 5`、`--depth 3` 等數值選項被正確解析而非回退預設（已於實機與單元測試通過）。

---

## 2. 實作與驗證成果 (FT-2 Execution & Test Log)

- **實作結果**：
  - `scripts/cli.py` 全面遷移至 `bags.get_option_value()`，並針對 `limit` 與 `depth` 增加正規化與解析容錯。
  - `contributes/core.json` 成功拆分 `ftype` 至獨立群組 `"filter"`，解除與 `space` 之互斥限制。
  - `tests/test_cli.py` 新增 FT-10 覆蓋選項提取與正交複合篩選。
- **實機測試日誌**：
  - 單元測試：`python yscb.py dev test knowledge-db` -> 150 Total, 150 Passed, 0 Failed, 0 Skipped (15.609s)。
  - 靜態檢查：`python yscb.py dev check knowledge-db` -> PASSED (0 warnings, 0 errors)。
  - 本地直裝驗證：`python yscb.py install knowledge-db@build --force` -> Successfully installed。
  - 實機指令驗證：
    - `python yscb.py knowledge-db search --space docs --ftype md "SOP"` -> 成功檢索出 4 筆 Markdown 文檔節點。
    - `python yscb.py knowledge-db callers "InvertedIndex" --limit 2` -> 精準回傳 2 筆調用者。
    - `python yscb.py knowledge-db impact "InvertedIndex" --depth 1 --limit 2` -> 精準限制 1 階與 2 筆上限。

---

## 3. SOP Review 審查與結案交付 (Review & FT-3 Closure)

- [x] **SOP Review 品質矩陣**：三層文檔對齊（`docs/` 手冊、`DESIGN_NOTES.md`、微觀註解）、測試 100% 通過。
- [x] **日誌與發布交付**：追加 `project://CHANGELOG.md` 發布摘要。
- [x] **結構與註解檢核**：實機執行 `python yscb.py agents-workflow plan verify <plan_name>` 驗證 100% Passed。
- **結案狀態**：`Completed`
