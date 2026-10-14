# 方案討論與技術對齊書 (Discussion & Alignment)

> 功能名稱：sub_04_docs_standards_and_docstring_alignment  
> 建立日期：2026-10-14  
> 所屬主計畫：2026_10_14_1224_deep_audit_and_ecosystem_refinement  
> 狀態：Confirmed  
> 模板版本：v1.2  

---

## 1. 使用者原始需求與意圖 (User Intent)

在歷經 `sub_01` (Core/Host)、`sub_02` (Dev/Server) 與 `sub_03` (Knowledge-DB/Agents-Workflow) 的全面架構與底層修復後，系統原始碼與測試已達到 100% 綠燈（550/550 Tests Pass）。
然而，審計報告 `R01` 揭露專案文檔體系存在嚴重的「文檔實作分叉」與「歷史殘留」，具體包含：
1. **URI 協議失真**：`STANDARDS.md` 記載已廢除的 `temp://`、`module.root://`，且未對齊 `module.mirror://` 與現行 `uri list`。
2. **過期指令殘留**：`docs/knowledge-db/` 仍殘留已廢除之 `knowledge-db scan` 與 `knowledge-db bundle` 指令教學；`docs/dev/` 未收錄 `release-check --all` 與最新測試選項。
3. **缺失模組 README**：`source/server/` 缺少模組根目錄 `README.md`。
4. **架構說明滯後**：`docs/server/` 未記錄 Worker `ServiceManager` 常駐服務納管架構。
5. **Frontmatter 與規格不齊**：部分文檔缺少標準 YAML frontmatter。
6. **Roadmap 狀態失聯**：`plans/roadmap/` 中諸多已實作功能（如常駐 Worker、8 大指令收斂等）仍標記為規劃中或進行中。

---

## 2. 核心討論與決策紀錄 (Discussion & Decisions)

### 方案 A：僅修正筆誤與死連結 (淺層修補 - 拒絕)
- 僅修正 `DN-09` 標題筆誤與幾處明顯死連結。
- 缺點：留下架構失真文檔，誤導後續接手的開發者與 AI Agent，違反「檔案為唯一真理 (SSOT)」原則。

### 方案 B：全庫文檔系統化梳理與三層對齊 (全面對齊 - 採納)
- **維度 1：專案通用標準 (`docs/_project/STANDARDS.md`)**：
  全面對齊當前真實 URI 協議集，補齊規範說明。
- **維度 2：各模組專屬文檔 (`docs/core/`, `docs/dev/`, `docs/server/`, `docs/knowledge-db/`, `docs/agents-workflow/`)**：
  - 修正筆誤與過期範例。
  - 補齊 `source/server/README.md`。
  - 淘汰舊版指令，對齊最新 8 大標準指令集與 Worker 架構。
- **維度 3：策略路線圖 (`plans/roadmap/`)**：
  全面梳理已落地功能狀態，建立可信的演進追溯。

---

## 3. 開放議題與確認事項 (Open Issues)

1. `docs/_project/STANDARDS.md`
2. `docs/core/` (包含 `DESIGN_NOTES.md`, `SEMVER.md` 等)
3. `docs/dev/` (包含 `DESIGN_NOTES.md`, `CLI_COMMANDS.md` 等)
4. `source/server/README.md` (新建) 與 `docs/server/`
5. `docs/knowledge-db/` (包含 `bundler.md`, `CLI_REFERENCE.md` 等)
6. `docs/agents-workflow/`
7. `plans/roadmap/`

