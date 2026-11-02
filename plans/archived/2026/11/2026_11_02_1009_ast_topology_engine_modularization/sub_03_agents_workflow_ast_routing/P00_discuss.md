# 需求與設計討論 (Requirements & Design Discussion) — `agents-workflow` 與 `knowledge-db-search` 技能對齊 `yscb ast` 路由與文檔更新 (`sub_03`)

> 功能名稱：agents-workflow 與 knowledge-db-search 技能對齊 yscb ast 路由與文檔更新
> 建立日期：2026-11-02
> 所屬主計畫：2026_11_02_1009_ast_topology_engine_modularization
> 狀態：Confirmed
> 模型：Gemini 4 Argon (Low)

---

## 1. 使用者原始需求與意圖 (User Intent)

- **業務目標**：在 `sub_01`（`module:ast@1.0.0.0` 獨立建立）與 `sub_02`（`module:knowledge-db@1.3.0.0` AST 消費遷移）完成後，更新 `module:knowledge-db` 貢獻之 `knowledge-db-search` 技能與隨包引導、`module:ast` 之 `agents-workflow` 貢獻引導、`module:agents-workflow` 之 `session-trace` 盲讀豁免解析器與技能參考文檔，以及 `docs/knowledge-db/`、`docs/ast/` 與根目錄 `CHANGELOG.md`，並透過 `agents-workflow compile` + `release` 將物化技能與 `AGENTS.md` 同步至工作區。
- **核心前提約束**：
  1. 維持單一檢索與導航入口技能 [`knowledge-db-search`](file:///workspace/ys-codebase/ys_codebase/source/knowledge-db/assets/skills/knowledge-db-search/SKILL.md)（`[P00:DR-05]`），避免頂層路由表膨脹。
  2. 於技能內建立明確的「三階段漏斗檢索與結構推理」規範：
     - **Stage 1（未知座標 / 全文與語意檢索）**：`python yscb.py knowledge-db search <query> --limit=10 --json`
     - **Stage 1.5（已知檔案之結構大綱與跨分部姊妹檔探索）**：`python yscb.py ast outline <file> [--public|--private|--static|--non-static|--methods|--fields|--types|--merged] [--json]`
     - **Stage 2（精準行號區段讀取）**：`StartLine` / `EndLine` 區段讀取。
     - **呼叫拓撲與爆炸半徑推理**：`python yscb.py ast <callers|callees|impact> <symbol> [--json]`（支援同名異載群組展開與帶參數簽名過濾）。
  3. 同步更新 `_trace_parser.py`，使 Agent 執行 `yscb.py ast <outline|callers|callees|impact>` 時同樣重設 `consecutive_source_reads = 0` 並標記 `has_recent_kdb_query = True`（豁免後續 $\le 160$ 行精準區段讀檔之盲讀計數）。

---

## 2. 核心討論與決策紀錄 (Discussion & Decisions)

### 2.1 定案前五維度防放水反詰掃描 (Pre-Confirmation 5-Dimension Probe)
1. **既有資產查重與復用**：
   - `knowledge-db` 已於 `ys_codebase/source/knowledge-db/contributes/agents-workflow.json` 註冊 `knowledge-db-search` 技能與 `usage_guide.md`、`research_guide.md`、`phase00_guide.md`、`phase07_guide.md`、`config_guide.md`；直接原地升級該組資產並於 `ys_codebase/source/ast/contributes/agents-workflow.json` 新增 `ast` 模組之 `HOW_TO_YSCB_MODULES` 與 `HOW_TO_CONFIG_MODULES` 注入。
2. **預設值與隱性副作用**：
   - `_trace_parser.py` 原本僅檢測 `"knowledge-db" in cmd_line and any(k in cmd_line for k in ("search", "callers", "callees", "impact"))`。當 `outline / callers / callees / impact` 移至 `yscb.py ast` 後，若不擴充 `_trace_parser.py`，Agent 先跑 `yscb.py ast outline <file>` 再執行區段讀檔會被誤判為 `unindexed_blind_reads`。擴充涵蓋 `ast` 指令可消除此副作用。
3. **生命週期與拆卸冪等性**：
   - 嚴格遵守二層物化唯讀鐵律：所有變更皆寫入 `ys_codebase/source/{knowledge-db,ast,agents-workflow}/`，再透過 `@build` 安裝與 `python yscb.py agents-workflow release` 冪等物化至 `.agents/skills/`。
4. **跨切面與全域契約不變量**：
   - `contributes check` 與 `agents-workflow compile` Stage 1 / Stage 2 必須 0 Warning、0 Error。
5. **顯式排除邊界 (Out-of-Scope)**：
   - 不新增獨立的 `ast-search` 技能（維持 `knowledge-db-search` 單一入口）。

### 2.2 核心架構決策紀錄 (`[P00:DR-*]`)
- **[P00:DR-01] `knowledge-db-search` 三階段漏斗與 `yscb ast` 指令整合**：
  - 於 [`knowledge-db-search/SKILL.md`](file:///workspace/ys-codebase/ys_codebase/source/knowledge-db/assets/skills/knowledge-db-search/SKILL.md) 整合 `knowledge-db search`（Stage 1 定位未知座標）、`ast outline <file>`（Stage 1.5 單檔結構大綱、三維度正交過濾與 `[Partial Siblings]` 跨分部姊妹檔提示）及 `ast <callers|callees|impact>`（呼叫拓撲與同名異載群組定址），並更新 `knowledge-db/assets/{usage_guide,research_guide,phase00_guide,config_guide}.md`。
- **[P00:DR-02] `module:ast` 之 `agents-workflow` 貢獻註冊**：
  - 新增 [`ys_codebase/source/ast/contributes/agents-workflow.json`](file:///workspace/ys-codebase/ys_codebase/source/ast/contributes/agents-workflow.json) 與 [`ys_codebase/source/ast/assets/{usage_guide,config_guide}.md`](file:///workspace/ys-codebase/ys_codebase/source/ast/assets/usage_guide.md)，將 `module:ast` 納入 `/how-to-yscb` 與 `/how-to-config-yscb` 動態導覽。
- **[P00:DR-03] `_trace_parser.py` 支援 `yscb.py ast` 結構導航豁免與三層文檔對齊**：
  - 於 [`_trace_parser.py`](file:///workspace/ys-codebase/ys_codebase/source/agents-workflow/agents_workflow/plans/_trace_parser.py) 將 `ast` 之 `outline`、`callers`、`callees`、`impact` 納入導航查詢識別（重設 `consecutive_source_reads = 0` 並設 `has_recent_kdb_query = True`），同步更新 `code-optimizer` 技能參考、三層文檔 `docs/{knowledge-db,ast}/` 與根目錄 `CHANGELOG.md`。

---

## 3. 開放議題與確認紀錄 (Open Questions & Confirmation)

- 無開放議題，依 `/auto` 推進 `sub_03` 規格、實作、編譯發布與全量驗證。

