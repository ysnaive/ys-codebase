# 需求討論說明書 (Semantic Requirements Discovery)

> 功能名稱：sub_02_skills_architecture  
> 建立日期：2026-08-31  
> 所屬主計畫：2026_08_31_1718_agents_workflow_architecture_optimization  
> 狀態：Confirmed  
> 計畫類型：Feature  
> 模板版本：v1.2  

---

## 1. 使用者原始需求與意圖 (User Intent)

- **原始陳述**：
  - 「現在本模組設計有一核心問題，缺少工作流 與 剛性定義之間的 skills，導致在 AGENTS.md 填充太多內容，比如 knowledge db 注入的關於搜尋工具的段落，應可以濃縮成，當需要運行任何搜尋需求 -> 使用 knowledge db skill，現在才幾個模組，當前 Agents.md 已膨脹到約 2~3k token，這不太健康」
  - 「源 sub 02 拆分為，Skills 架構，原內容優化遷移改至 Sub Plan 03」
  - 「開始前先等等，先進行 SKILL 規範調研，現 SKILL 於 Agents IDE 具體有哪些內容可定義? 怎麼定義? 結合 ClaudeCode/Codex/AntigravityIDE 進行綜合調研」
  - 「現在看來，要完整支援 skill 輸出，該類型的注入應另 provider 提供資料夾路徑而不是單個檔案」
  - 「不是隔離問題，是要根據 codex 官方需求路徑設定」
- **核心目標**：
  - 完成跨平台（Antigravity / Claude Code / Codex）Skills 規範綜合調研（已產出 [`R01_skills_specification_research.md`](./R01_skills_specification_research.md)）。
  - 本子計畫（Sub-Plan 02）專注於 **Skills 基礎架構與目錄級投影編譯管線** 的建立。
  - 在 `agents-workflow` 核心擴充 `export.type = "skill"` 之宣告與編譯支援，**Provider 支援提供 Skill 整個資料夾路徑**（包含 `SKILL.md`、`references/`、`scripts/` 等所有附帶資產）。
  - 在 `release_target` 中支援 `projections.skill` 投影規則（支援 `{export.name}` 目錄巨集插值與自訂 Header），實現將生態系模組的 Skills 目錄結構完整遞迴編譯並發布至 IDE 規範目錄。
  - 根據官方標準修正 `codex` Target 投影路徑至 `project://.agents/`。
  - 更新 `source/agents-workflow/contributes.format.md` 規格手冊。
- **邊界排除 (Explicitly Excluded)**：
  - 各生態系模組（如 `knowledge-db`）現有 `AGENTS_STANDARDS` 內容之重構、下沉遷移至 Skills 與 `AGENTS.md` 實質瘦身作業，明確排除於本子計畫，統一於 **Sub-Plan 03** 執行。

---

## 2. 核心討論與決策紀錄 (Discussion & Decisions)

- **[P00:DR-01] 確立三層金字塔資產治理體系（源自 R01 調研）**：
  - **Tier 1: Rules (剛性守門)**：`AGENTS.md` / `CLAUDE.md`，100% 常駐，僅保留極限禁令與防呆，體積極致精簡（< 500 tokens）。
  - **Tier 2: Skills (隨選領域秘笈)**：`.agents/skills/<name>/`，漸進式揭露（Progressive Disclosure），僅元數據（name/description）常駐（~40 tokens），正文與子目錄手冊隨選加載。
  - **Tier 3: Workflows (宏觀作業流程)**：`.agents/workflows/*.md`，顯式指令與生命週期管線。
- **[P00:DR-02] Export 規範擴充 `type: "skill"` 與目錄級 Provider 支援**：
  - 允許生態系模組在 `contributes.agents-workflow.export` 中宣告 `type: "skill"`，且 `source` **直接指向 Skill 目錄**（亦相容單檔路徑），例：
    ```json
    {
      "type": "skill",
      "name": "knowledge-db",
      "source": "module.root://assets/skills/knowledge-db",
      "description": "知識庫檢索與語意搜尋工作流指南，提供 AST 切片檢索、調用圖譜與依賴拓撲分析之最佳實踐。"
    }
    ```
- **[P00:DR-03] 編譯器目錄走訪與遞迴 Stage 1/Stage 2 解算**：
  - `ArtifactCompiler` 檢測到 `source` 為目錄時，自動遞迴走訪其下所有檔案（`SKILL.md`、`references/*.md`、`scripts/*` 等）。
  - 對文字檔案執行 Stage 1 Token 展開與 Stage 2 URI 解析，並在中繼快取中完整保留相對目錄層級。
- **[P00:DR-04] Release Targets 投影支援 `projections.skill` 與官方路徑對齊**：
  - `ReleasePublisher.build_deployment_map` 支援解析 `target_dir` 中的 `{export.name}` / `{export.basename}` 巨集。
  - 依各平台官方標準規範預設三大 IDE 內建 Targets 之投影設定：
    - `antigravity`: `"projections": { "skill": { "target_dir": "project://.agents/skills/{export.name}", "extension": ".md" } }`
    - `claude`: `"projections": { "skill": { "target_dir": "project://.claude/skills/{export.name}", "extension": ".md" } }`
    - `codex`: `"projections": { "skill": { "target_dir": "project://.agents/skills/{export.name}", "extension": ".md" } }`（官方標準：專案工作區工作流與技能皆位於 `project://.agents/`）
- **[P00:DR-05] 發布交易、雙軌 Manifest 與 Gitignore 支援**：
  - `ReleasePublisher` 發布整個 Skill 目錄結構（含所有子目錄與關聯檔案），支援 Diff 比對、雙軌 Manifest 追蹤與 Pruning。
  - `.gitignore` 同步管線精確忽略 `.agents/skills/<name>/` 下所有發布產物，不整目錄忽略 `.agents/` 以保護使用者自訂檔案。

---

## 3. 開放議題與確認紀錄

- [x] **[2026-08-31]** 確認 Sub-Plan 02 需求討論、R01 調研報告與官方標準路徑定稿（狀態：Confirmed）。
