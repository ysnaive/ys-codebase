# 需求規格說明書 (Requirements Specification)

> 功能名稱：sub_05_agents_workflow_skill_unification  
> 建立日期：2026-10-14  
> 所屬主計畫：2026_10_14_1224_deep_audit_and_ecosystem_refinement  
> 狀態：Confirmed  
> 模板版本：v1.4  

---

## 1. 功能需求清單 (Functional Requirements)

- [ ] **FR-01 (資產 Schema 純化與相容容錯)**：修改 `_format.json`，將 `ExportAssetDef.type` 純化為 `enum(standard, template, skill)!`；`compiler.py` 在遇到歷史 `workflow` 宣告時自動轉譯為 `skill` 並輸出通知。
- [ ] **FR-02 (內建 8 大 Workflows 遷移為 Skills)**：將 `assets/workflows/` 中的 8 個工作流完整遷移為 `assets/skills/<name>/SKILL.md` 標準結構，補齊標準 YAML Frontmatter，並移除 `assets/workflows/` 目錄。
- [ ] **FR-03 (Contributes 導出宣告與投影收斂)**：修改 `source/agents-workflow/contributes/agents-workflow.json`，將 8 大工作流改為 `type: "skill"` 導出宣告；自 `release_target`（antigravity, claude, codex）之 `projections` 中徹底移除 `workflow` 投影節點。
- [ ] **FR-04 (專案級 BumpRevision 工作流遷移)**：將 `config/agents-workflow/workflows/BumpRevision.md` 遷移為 `config/agents-workflow/skills/bump-revision/SKILL.md`，並更新 `config/agents-workflow/contribute.json` 為 `type: "skill"`。
- [ ] **FR-05 (舊發布目錄自動安全清理)**：`publisher.py` 在執行發布交易（Release Transaction）時，自動檢測目標專案之 `.agents/workflows` 目錄，若存在則安全清理，徹底杜絕殭屍工作流檔案殘留。
- [ ] **FR-06 (標準規範與超連結全面對齊)**：修改 `AgentsStandards.md`、`DevelopmentStandards.md` 及相關規範，將所有指向 `.agents/workflows/*.md` 的連結對齊至 `.agents/skills/<name>/SKILL.md`。
- [ ] **FR-07 (單元測試套件全面適配)**：更新 `test_compiler.py`、`test_publisher.py` 等測試，使測試斷言完全適配純 Skill 架構。

---

## 2. 邊界與異常情況 (Edge Cases & Failure Modes)

- **EC-01 (遇到歷史模組宣告 workflow 類型)**：`compiler.py` 在 Stage 0 自動轉譯為 `skill` 並輸出 warning，確保第三方擴充向下相容。
- **EC-02 (舊版 .agents/workflows 殘留)**：`publisher.py` 在發布前自動排查並清理舊目錄，防止殭屍檔案污染。

---

## 3. 非功能需求 (Non-Functional Requirements)

- **NFR-01 (命令列與 Agent 觸發無縫性)**：遷移後之 Skill 套件必須符合各 IDE 官方 Skill 規範，支援自然語意觸發與相容 Slash Commands。
- **NFR-02 (零回歸驗證)**：全生態系 550 項單元測試必須保持 100% 通過（0 失敗 0 警告）。

---

## 4. 知識庫與踩坑紀錄查閱 (Known Gotchas & CAUTIONs)

- **`[!CAUTION]`** 遷移為 Skill 時，每個 `SKILL.md` 必須包含合法 YAML frontmatter（包含 `name` 與 `description`），缺少將導致平台無法識別。


