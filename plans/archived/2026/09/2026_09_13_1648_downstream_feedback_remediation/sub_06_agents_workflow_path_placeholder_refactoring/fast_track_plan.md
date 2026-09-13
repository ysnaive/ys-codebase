# Fast Track 敏捷開發計畫 (Fast Track Plan)

> 功能名稱：sub_06_agents_workflow_path_placeholder_refactoring  
> 建立日期：2026-09-13  
> 所屬主計畫：2026_09_13_1648_downstream_feedback_remediation  
> 狀態：Completed  
> 計畫類型：Level 0 Fast Track  
> 模板版本：v1.2  

---

## 1. 敏捷需求與實作計畫 (FT-1 Specification & Plan)

### 1.1 核心需求與邊界
- **需求描述**：
  1. **佔位符語意明確化 (# vs $)**：
     - `__#{uri}__`：明確定義為「自身相對路徑佔位符」，轉譯為相對於目標生成檔案所在目錄 (`cur_dir`) 之相對路徑，主要用於 Markdown 超連結。
     - `__${uri}__` / `__$(起始錨點){uri}__`：明確定義為「錨點/絕對相對路徑佔位符」，轉譯為相對於指定起始錨點之相對路徑。
  2. **`__${uri}__` 語意擴充與起始錨點語法 (`__$(起始錨點){uri}__`)**：
     - 原不帶起始錨點的 `__${uri}__` 維持向後相容，預設以 `project://`（專案根目錄）為起始錨點進行映射。
     - 新增擴充語法 `__$(起始錨點){uri}__`：支援在括號內指定起始錨點（如 `__$(module.source://){uri}__` 或 `__$(project://docs){uri}__` 或其他語意 URI / 目標 key），計算目標 `uri` 相對於該起始錨點的路徑 (`os.path.relpath(target_abs, anchor_abs)`)。
     - 支援 Standalone（剝除外層反引號）與 Inline（穿插代碼中保留反引號）雙模式。
  3. **未包裹標籤警示健全性 (`check_unenclosed_tags`)**：
     - 正則表達式支援偵測擴充之 `__$(...){...}__` 格式，防止裸標籤未加反引號外溢。
- **影響範圍**：
  - `ys_codebase/source/agents-workflow/agents_workflow/compiler.py` (Modify: 更新正則、`resolve_stage2_uri` 與 `_resolve_project_uri`)
  - `ys_codebase/source/agents-workflow/tests/test_compiler.py` (Modify: 新增 FT-01、FT-02 與 FT-03 測試)
  - `docs/agents-workflow/FACTORY_PIPELINE.md` (Modify: 更新佔位符語法章節)
  - `docs/agents-workflow/DESIGN_NOTES.md` (Modify: 新增 DN-AW-12)
- **4 大剛性守門合規檢核**：
  - [x] 代碼修改行數預計 $\le 100$ 行（核心修改預計 30~50 行，完全合規）
  - [x] Public API 契約 0 變更（`resolve_stage2_uri` 維持原函式簽名）
  - [x] 零跨模組新依賴引入（100% Python 標準庫）
  - [x] 既有單元測試與回歸測試 100% 覆蓋守門

### 1.2 實作任務與測試規劃
- [x] **TASK-01**：重構 `compiler.py` 正則表達式與 `resolve_stage2_uri`，實作 `__$(起始錨點){uri}__` 解析邏輯並保持 `__${uri}__` 預設 `project://` 相容
- [x] **TASK-02**：編寫單元測試覆蓋 `__$(anchor){uri}__` 預設錨點、自訂語意錨點、Standalone 與 Inline 等多維場景
- [x] **TASK-03**：同步更新 `FACTORY_PIPELINE.md`、`DESIGN_NOTES.md` (DN-AW-12) 並執行回歸驗收
- **測試案例**：
  - `FT-01`：驗證 `__${uri}__` 維持以 `project://` 為預設起始映射（既有相容性守門）
  - `FT-02`：驗證 `__$(anchor){uri}__` 正確將 `uri` 解析為相對於 `anchor` 所指向之目錄或實體路徑
  - `FT-03`：驗證 `__$(anchor){uri}__` 在 Standalone 與 Inline 穿插語意下之正確性

---

## 2. 實作與驗證成果 (FT-2 Execution & Test Log)

- **實作結果**：
  1. **TASK-01 佔位符語意擴充實作**：於 `compiler.py` 擴充 `PROJECT_URI_INNER_REGEX`、`PROJECT_URI_EXACT_REGEX` 與 `UNENCLOSED_TAG_REGEX`，實作 `_resolve_anchor_dir` 與 `_resolve_project_uri(tag_uri, anchor)`，完整支援 `__$(起始錨點){uri}__` 語法並維持 `__${uri}__` 預設 `project://` 相容；`resolve_stage2_uri` 優先採納顯式指定的 `self.host_dir`（若提供），保障測試與沙盒環境的宿主路徑純淨性。
  2. **TASK-02 單元測試覆蓋**：於 `test_compiler.py` 新增 `test_ft_17_project_uri_custom_anchor_syntax`、`test_ft_18_project_uri_custom_anchor_standalone_and_inline` 與 `test_ft_19_unenclosed_tags_warning_with_anchor_syntax`，覆蓋預設無錨點、目錄錨點、檔案錨點 (取 dirname)、跨層級計算、空括號退化、Standalone (完全替代剝除反引號)、Inline (保留代碼反引號) 與裸露標籤警示。
  3. **TASK-03 規格與設計手冊更新**：於 `docs/agents-workflow/FACTORY_PIPELINE.md` 完善 `#`（自身相對路徑）與 `$`（錨點相對路徑）之語意對齊與語法說明；於 `docs/agents-workflow/DESIGN_NOTES.md` 登錄 `[DN-AW-12]`。
- **實機測試日誌**：
  - `python yscb.py dev test agents-workflow`：79 Total, 79 Passed, 0 Failed, 0 Skipped (65.69s)
  - `python yscb.py dev check agents-workflow`：Status: PASSED (0 Warning, 0 Error)

---

## 3. SOP Review 審查與結案交付 (Review & FT-3 Closure)

- [x] **SOP Review 品質矩陣**：三層文檔對齊（`docs/agents-workflow/FACTORY_PIPELINE.md`、`DESIGN_NOTES.md` [DN-AW-12]、`compiler.py` 微觀註解）、測試 100% 通過 (79/79)。
- [x] **日誌與發布交付**：追加 `project://CHANGELOG.md` 發布摘要。
- [x] **結構與註解檢核**：實機執行 `python yscb.py agents-workflow plan verify sub_06_agents_workflow_path_placeholder_refactoring` 驗證 100% Passed。
- **結案狀態**：`Completed`
