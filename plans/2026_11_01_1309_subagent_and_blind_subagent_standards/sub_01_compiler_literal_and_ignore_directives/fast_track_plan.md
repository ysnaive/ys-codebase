# Fast Track 敏捷開發計畫 (Fast Track Plan)

> 功能名稱：編譯器 `yscb:literal:begin/end` 與 `yscb:ignore:begin/end` 區塊語法強化  
> 建立日期：2026-11-01  
> 所屬主計畫：2026_11_01_1309_subagent_and_blind_subagent_standards  
> 狀態：Completed  
> 模型：Gemini 4 Argon (Low)  

> 計畫類型：Fast Track  
> 模板版本：v1.2  

---

## 1. 敏捷需求與實作計畫 (FP-01 Specification & Plan)

### 1.1 4 大剛性守門合規檢核 (Mandatory 4-Gate Check)
- [x] **修改行數守門**：代碼修改行數預估 $\le 100$ 行（實際新增/修改核心代碼約 88 行）。
- [x] **API 契約守門**：Public API 簽名契約 0 變更（`resolve_single_artifact`、`resolve_stage2_uri`、`check_unenclosed_tags` 等公開方法簽名完全不變）。
- [x] **依賴邊界守門**：零跨模組新依賴引入（100% Python 標準庫）。
- [x] **既有測試守門**：既有單元測試套件 100% 覆蓋守門。

### 1.2 核心需求與邊界
- **需求描述**：
  1. **`[FP-01:DR-01]` 升級字面量保護區塊為成對標記 `<!-- yscb:literal:begin -->` ... `<!-- yscb:literal:end -->`**：
     - 淘汰舊版僅限三反引號 Fenced Code Block 首行的單行 `<!-- yscb:literal -->` 限制，改為可置於任意獨立行的成對標記。
     - Stage 1 (`resolve_single_artifact`) 原樣遮罩保護區塊內容與首尾標記（不展開、不清除 `__@{...}__`，亦不觸發 `check_unenclosed_tags` 警告）。
     - Stage 2 (`resolve_stage2_uri`) 剝除最外層 `<!-- yscb:literal:begin -->` 與 `<!-- yscb:literal:end -->` 標記行，並將區塊內部所有文字與動態標籤（`__@{...}__`, `__#{...}__`, `__${...}__`, `__%{...}__`）100% 原樣輸出至物化檔。
  2. **`[FP-01:DR-02]` 新增源碼註解抹除區塊 `<!-- yscb:ignore:begin -->` ... `<!-- yscb:ignore:end -->`**：
     - 支援於提示詞與標準原始檔任意獨立行撰寫不進入物化檔的維護者註解。
     - 於 Stage 1 與 `check_unenclosed_tags` 前直接整段剝除（含標記行與內部所有內容），完全不進入 Stage 1 快取與 Stage 2 最終物化檔。
  3. **`[FP-01:DR-03]` 深度計數巢狀自舉保護與未閉合標記警告 (`[compiler:warning]`)**：
     - 採用狀態與深度計數解析：當外層處於 `literal:begin ... literal:end` 內時，內層出現的第 2 層 `literal:begin/end` 或 `ignore:begin/end` 均視為純文字字面量原樣保留（支援於規範文檔中直接展示該語法本身）；當外層處於 `ignore:begin ... ignore:end` 內時，內部一切內容（含 `literal` 標記）一律忽略抹除。
     - 若偵測到未配對閉合之 `begin` 或孤立之 `end` 標記，輸出 `[compiler:warning]` 診斷訊息。
  4. **`[FP-01:DR-04]` 資產遷移與 `Revision Plan` 衍生 `sub_XX` 結構檢核對齊**：
     - 將既有資產（`YscbSkillDesignToolStandards.md`、`skill-creator/SKILL.md`、`skill-creator/references/extension-guide.md`、`docs/agents-workflow/DESIGN_NOTES.md`）中之舊版 `<!-- yscb:literal -->` 全面更新為 `<!-- yscb:literal:begin -->` ... `<!-- yscb:literal:end -->`，並補充 `<!-- yscb:ignore:begin/end -->` 規範說明。
     - 於 `verifier.py` 支援含 `revision_log.md` 之 `Revision Plan` 主計畫衍生 `sub_XX` 子計畫目錄，免除強制要求 `umbrella_overview.md`。
- **影響範圍**：
  - `ys_codebase/source/agents-workflow/agents_workflow/compiler.py`
  - `ys_codebase/source/agents-workflow/agents_workflow/plans/verifier.py`
  - `ys_codebase/source/agents-workflow/assets/standards/YscbSkillDesignToolStandards.md`
  - `ys_codebase/source/agents-workflow/assets/skills/skill-creator/SKILL.md`
  - `ys_codebase/source/agents-workflow/assets/skills/skill-creator/references/extension-guide.md`
  - `docs/agents-workflow/DESIGN_NOTES.md`
  - `ys_codebase/source/agents-workflow/tests/test_compiler.py`

### 1.3 實作任務與測試規劃
- [x] **TASK-01**：於 `compiler.py` 實作 `yscb:literal:begin/end` 與 `yscb:ignore:begin/end` 深度計數解析、Stage 1/2 遮罩剝除與未閉合標記警告，並於 `verifier.py` 放行 `Revision Plan` 衍生 `sub_XX`。
- [x] **TASK-02**：更新 `YscbSkillDesignToolStandards.md`、`skill-creator/SKILL.md`、`extension-guide.md` 與 `docs/agents-workflow/DESIGN_NOTES.md` 至新語法並補齊 `yscb:ignore:begin/end` 說明。
- [x] **TASK-03**：於 `test_compiler.py` 新增與更新單元測試，執行 `dev check` 與 `dev test` 驗證 100% 通過。
- **測試案例清冊**：
  - [x] **FT-01**：驗證 `<!-- yscb:literal:begin -->` ... `<!-- yscb:literal:end -->`（含跨段落/代碼塊與巢狀自舉展示 `literal`/`ignore` 語法）於 Stage 1 遮罩保護、Stage 2 自動剝除外層標記並 100% 保留內部字面量，以及 `<!-- yscb:ignore:begin -->` ... `<!-- yscb:ignore:end -->` 完全抹除不物化與未閉合標記警告（`test_ft_15_literal_and_ignore_block_directives`）。
  - [x] **RT-01**：全模組既有單元測試 100% 回歸通過（`138/138` Passed）。

---

## 2. 實作與驗證成果 (FP-02 Execution & Test Log)

- **實作結果**：
  - 於 `compiler.py` 實作 `_preprocess_directives` 深度計數解析器，整合至 `check_unenclosed_tags`、`resolve_single_artifact`（含 `insert` 片段載入）與 `resolve_stage2_uri`。
  - 全面遷移 `YscbSkillDesignToolStandards.md`、`skill-creator/SKILL.md`、`extension-guide.md` 與 `docs/agents-workflow/DESIGN_NOTES.md`，並完成 `install agents-workflow@build --force`、`contributes check`、`agents-workflow compile`（0 warning）與 `agents-workflow release --force`（71 written）。
- **實機測試日誌**：
  - `python yscb.py dev check agents-workflow` -> `Status: PASSED`
  - `python yscb.py dev test agents-workflow -q` -> `Pass: 138(100.0%), Fail: 0, Skip: 0`

---

## 3. SOP Review 審查與結案交付 (Review & FP-03 Closure)

- [x] **SOP Review 品質矩陣**：三層文檔對齊（`docs/` 手冊、`DESIGN_NOTES.md`、微觀註解）、測試 100% 通過。
- [x] **日誌與發布交付**：追加 `CHANGELOG.md` 發布摘要。
- [x] **標頭狀態更新**：完成上述審查並將本清單其餘項勾選 `[x]` 後，將頂部標頭 `> 狀態：` 更新為 `Completed`。
- [x] **結構與註解檢核（最終守門）**：最後實機執行 `python yscb.py agents-workflow plan verify <plan_name>` 驗證 100% Passed（若檢出未通過項則原地修正重驗）。
