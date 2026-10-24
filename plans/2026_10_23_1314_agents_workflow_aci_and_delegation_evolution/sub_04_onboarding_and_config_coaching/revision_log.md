# 修訂紀錄書 (Revision Log)

> 功能名稱：sub_04_onboarding_and_config_coaching  
> 建立日期：2026-10-24  
> 所屬主計畫：2026_10_23_1314_agents_workflow_aci_and_delegation_evolution  
> 狀態：Completed  
> 模型：Gemini 4 Argon (High)  

> 模板版本：v1.0  

---

## 1. 修訂紀錄清單 (Revision Entries)

### [REV-01] 跨平台宿主 NTFS 與 Linux `virtiofs` 歷史大寫目錄正名及 `.modules_stale` 殘留清理
- **修訂類別**：Parameter / DX
- **涉及檔案**：
  - `ys_codebase/source/{core,dev,server,knowledge-db}/scripts/`
  - `docs/core/`
- **修訂摘要**：排查 `dev test --sync` 與 `reload` 時偶發 `[Errno 5] Input/output error` 與 `.modules_stale` 殘留之根因——宿主 Windows NTFS 歷史遺留大寫主檔名（`Scripts`、`Core`）與 Linux `virtiofs` 小寫查找並存，導致 `os.listdir`/`os.walk` 同時回傳指向同一 Inode 之大小寫雙影並打入 `.build.zip`。透過兩段式更名（`scripts -> _tmp -> scripts`、`core -> _tmp -> core`）將宿主底層主檔名徹底刷新為全小寫，重打乾淨 `.build.zip` 並清理暫態 `.modules_stale` 與 `ys_codebase/build` 目錄，全專案驗證 `0` 大小寫碰撞。
- **驗證結果**：五大模組 `dev test <mod> -q --sync`（共 595 項測試）與 `python yscb.py reload` 100% 通過且無任何殘留目錄。

### [REV-02] 全量複檢對齊原始 Roadmap 訴求：移除靜態預建片段並補齊雙星技能與四模組指南契約
- **修訂類別**：UI/UX/DX / Docs
- **涉及檔案**：
  - `ys_codebase/config/agents-workflow/contribute.json`
  - `ys_codebase/source/agents-workflow/contributes/agents-workflow.json`
  - `ys_codebase/source/agents-workflow/assets/skills/how-to-config-yscb/SKILL.md`
  - `ys_codebase/source/agents-workflow/assets/skills/how-to-yscb/SKILL.md`
  - `ys_codebase/source/{core,dev,server,knowledge-db}/assets/{config_guide.md,usage_guide.md}`
  - `ys_codebase/source/agents-workflow/tests/test_plans_model_record.py`
  - `plans/2026_10_23_1314_agents_workflow_aci_and_delegation_evolution/sub_04_onboarding_and_config_coaching/{P00_discuss.md,P01_requirements_spec.md,P02_architecture_plan.md,P03_api_spec.md,P04_implementation_plan.md,P05_task.md,P06_test_plan.md,P07_walkthrough.md}`
- **修訂摘要**：
  1. **還原未配置基線**：移除開發階段靜態預建之 `project_role.md` 與 `testing_guide.md` 及其於 `ys_codebase/config/agents-workflow/contribute.json` 之掛載，確保交由 `/how-to-config-yscb` 實機探勘、草擬並於開發者確認後代寫。
  2. **對齊 `/how-to-config-yscb` 細節**：對齊 Roadmap 原文 Frontmatter `description`；增補 `agents-workflow` 自身組態體檢項（`paths.*` vs `release_targets` 雙層分流）；落實「防呆 1」嚴禁硬編碼 `.agents/` 或 `.claude/`，改為依 `release_target` 從 `contributes` 的 `projections` 動態解析二層物化唯讀空間；明確定義 `project_role.md` 極簡三要素模板（① 開發者角色與專案使命、② 本體業務空間與 `/discuss` 優先級 1~2 聚焦、③ 外部工具包黑盒底盤 `.modules/` 等）。
  3. **對齊 `/how-to-yscb` 細節**：對齊 Roadmap 原文 Frontmatter `description`；增補「YSCB 資深教練／導師 (Coach / Mentor Persona)」角色切換與極簡狀態卡格式豁免（採漸進式單一主題對話）；還原入口 A 開放式提問「你想從什麼角度了解這套工具？」與完整角度 A~D（含角度 D：`/auto`、`/pause`、`/skill-creator`、`/skill-optimizer`）。
  4. **對齊四大模組注入片段三要素與連結格式**：將 `config_guide.md` 統一為「① 組態項目與用途、② 健康度檢查條件、③ 隨包設定手冊語意連結」，`usage_guide.md` 統一為「① 模組定位與適用時機、② 標準用法速查 (Golden Recipes)、③ 隨包手冊語意連結」，並以 Markdown 連結包裹 `config://` 語意路徑，消除單獨 `__${...}__` 編譯後外層反引號剝除問題。
- **驗證結果**：`dev check --all`、`contributes check`、`dev test agents-workflow -q --sync` (133/133 Passed)、`agents-workflow compile` (0 Error/0 Warning) 與 `agents-workflow release --force` 100% 通過。

---

## 2. 結案與合規檢核 (Completion & Compliance Checklist)

- [x] **修訂與驗證完畢**：所有修訂項目均已實作並通過測試或驗證，無殘留死代碼或除錯資訊。
- [x] **日誌與文檔同步**：已同步更新計畫內 `changelog.md` 與相關 `docs/` 知識庫文檔；若包含使用者可感知之重要變更，依比例原則追加至專案根目錄 `CHANGELOG.md`。
- [x] **標頭狀態更新**：完成上述檢核並將本清單其餘項勾選 `[x]` 後，將頂部標頭 `> 狀態：` 更新為 `Completed`。
- [x] **結構合規檢核（最終守門）**：最後實機執行 `python yscb.py agents-workflow plan verify <plan_name>` 驗證 100% Passed（若檢出未通過項則原地修正重驗）。

