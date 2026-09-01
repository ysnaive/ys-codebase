# Fast Track 敏捷開發計畫 (Fast Track Plan)

> 功能名稱：knowledge-db 宣告式空間佔位符與檢索技能剛性防護 (Knowledge DB Space Token & Skill Hardening)  
> 建立日期：2026-09-01  
> 所屬主計畫：無 (獨立 Level 0 敏捷計畫)  
> 狀態：Completed  

> 計畫類型：Level 0 Fast Track  
> 模板版本：v1.1  

---

## 1. 敏捷需求與實作計畫 (FT-1 Specification & Plan)

### 1.1 核心需求與邊界
- **需求描述**：
  - 由 `knowledge-db` 模組完全自包含地宣告新 Token `KNOWLEDGE_DB_SPACE` 與對應之 `code.func://` computed provider，將全系統已註冊空間動態解算並渲染為 Markdown 空間速查表，零耦合 `agents-workflow`。
  - 將動態空間錨點 `<!-- YSCB_KNOWLEDGE_DB_SPACE_BEGIN -->` 與 `` `__@{KNOWLEDGE_DB_SPACE}__` `` 嵌入 `knowledge-db-search` Skill 中。
  - 統合前述 Retro 分析之防呆升級：
    1. **原生搜尋邊界剛性收窄**：明訂原生搜尋工具僅限單檔 `SearchPath`，絕對禁止目錄與跨檔文字廣搜。
    2. **負面範例防護**：注入「常見意圖與反模式對照表 (Anti-Patterns vs Correct Patterns)」。
    3. **Frontmatter 描述強化**：注入禁止目錄搜尋之守門語意，強化 Agent 第一反射。
- **影響範圍**：
  - `source/knowledge-db/knowledge_db/providers.py` (新增)
  - `source/knowledge-db/contributes/agents-workflow.json` (更新宣告)
  - `source/knowledge-db/assets/skills/knowledge-db-search/SKILL.md` (更新 Skill 資產)
  - `source/knowledge-db/tests/test_providers.py` (新增單元測試)
  - 100% 收斂於 `source/knowledge-db/`，零跨模組耦合。

### 1.2 實作任務與測試規劃
- [x] **TASK-01**：在 `source/knowledge-db/knowledge_db/providers.py` 實作 `get_knowledge_db_spaces` computed provider 函式。
- [x] **TASK-02**：在 `source/knowledge-db/contributes/agents-workflow.json` 宣告 `token` 與 `computed` insert。
- [x] **TASK-03**：重構 `source/knowledge-db/assets/skills/knowledge-db-search/SKILL.md`，嵌入空間錨點、單檔搜尋限制、Anti-Patterns 對照表與強化 Frontmatter。
- [x] **TASK-04**：撰寫 `test_providers.py`，執行 `dev check` 與 `dev test knowledge-db` 驗證 100% Passed。
- [x] **TASK-05**：透過 Dogfooding `@build` 安裝與編譯，驗證物化後的 `.agents/skills/knowledge-db-search/SKILL.md` 正確解算空間表與完整規範。
- **測試案例**：
  - `FT-01`：`get_knowledge_db_spaces` 函式單元測試，驗證輸出包含所有已註冊空間之 Markdown 表格。
  - `FT-02`：`agents-workflow` 測試編譯，驗證 `KNOWLEDGE_DB_SPACE` 成功被動態替換為空間表格。
  - `RT-01`：`knowledge-db` 全量單元測試 100% 通過。

---

## 2. 實作與驗證成果 (FT-2 Execution & Test Log)

- **實作結果**：
  - 於 `source/knowledge-db/knowledge_db/providers.py` 成功實作 `get_knowledge_db_spaces` 空間表格動態生成函式。
  - 於 `source/knowledge-db/contributes/agents-workflow.json` 宣告 `KNOWLEDGE_DB_SPACE` Token 與 `computed` 插入規則，達成 100% 零耦合。
  - 於 `source/knowledge-db/assets/skills/knowledge-db-search/SKILL.md` 嵌入空間錨點、收窄原生工具為單檔、注入 Anti-Patterns 對照表。
- **實機測試日誌**：
  - `dev check knowledge-db`：PASSED。
  - `dev test knowledge-db`：**130/130 Passed (100% Ready, 1.43s)**。
  - `install knowledge-db@build --force`：成功安裝並自動觸發 `agents-workflow` 發布勾子。
  - 實機檢核 `.agents/skills/knowledge-db-search/SKILL.md`：成功動態渲染已註冊空間表格（`docs`, `plans`, `source`），包含反模式對照與單檔限制。

---

## 3. 結案與交付確認 (FT-3 Closure & Walkthrough)

- [x] **文檔與日誌交付**：同步追加 [CHANGELOG.md](file:///workspace/ys-codebase/CHANGELOG.md) 變更摘要。
- [x] **結構與註解檢核**：實機執行 `python yscb.py agents-workflow plan verify 2026_09_01_0607_knowledge_db_space_token_and_skill_hardening` 驗證 100% Passed。
- **結案狀態**：`Completed`
