# 成果展示與結案報告 (Walkthrough)

> 功能名稱：開發標準規範與流程分離重構及 Contributes 文檔建立 (Standards & Workflow Separation & Contributes Doc)  
> 建立日期：2026-08-26  
> 所屬主計畫：[agents-workflow 模組全面遷移與升級 (2026_08_25_2200_agents_workflow_migration)](../umbrella_overview.md)  
> 狀態：Completed  
> 模板版本：v1.4  

---

## 1. 變更概述 (Executive Summary)

本子計畫完成了 `agents-workflow` 標準規範與流程指引的徹底解耦、`AGENTS.md` 軟合併精簡優化、專案組態開關落實以及官方擴充格式說明書（`contributes.format.md`）的建立：

1. **標準規範與開發流程資產拆分 (`FR-01`)**：
   - **`AgentsStandards.md`**：專門收斂通用核心原則（三大原則）與防呆紀律（嚴禁連發、Checkpoint 強制等待、問答 $\neq$ 推進、範疇保護、無 Log 即未驗證等）。
   - **`DevelopmentStandards.md`**：收斂專案 SOP 0~7 完整流程指引、三大分流矩陣、追溯鏈矩陣與工作目錄規範。
   - **`NewPlan.md`**：維持完整載入包含詳細 SOP 流程的 `DevelopmentStandards.md`。
2. **`AGENTS.md` 軟合併注入標的切換與 Prompt 瘦身 (`FR-02`, `NFR-03`)**：
   - `ReleasePublisher` 改為提取極簡版 `AgentsStandards.md` 注入至 `AGENTS.md` 的 `<!-- YSCB_AGENTS_BEGIN -->` 與 `<!-- YSCB_AGENTS_END -->` 區塊中。
   - `AGENTS.md` 由原先 163 行精簡至 64 行（字數縮減超過 52%），顯著降低每次與 Agent 對話之 Context / Token 負載，同時 100% 無損保留專案特化規則。
3. **Contributes 宣告與組態開關落實 (`FR-03`, `FR-04`, `FR-05`)**：
   - `manifest.json` 註冊 `AgentsStandards.md` export 與 `AGENTS_STANDARDS` Token。
   - `config.project.json` 中 `"release_targets"` 預設改為空陣列 `[]`（無），避免未指定時主動產生未預期的 IDE 目錄。
   - 完整支援 `enable_agents_md` 與 `enable_project_changelog` 開關控制。
4. **官方 Contributes 規格說明書建立 (`FR-06`)**：
   - 建立 `source/agents-workflow/contributes.format.md`，詳述 `core.uri_schemes`、`export`、`token`、`insert`、`release_target` 之宣告規範、欄位型別與使用範例。

---

## 2. 變更檔案清單 (Changed Files Inventory)

| 檔案路徑 | 變更類型 | 變更說明 |
| :--- | :---: | :--- |
| `source/agents-workflow/assets/standards/AgentsStandards.md` | **New** | 存放 Agent 必須強制遵守的通用核心原則與防呆紀律規範。 |
| `source/agents-workflow/assets/standards/DevelopmentStandards.md` | **Modify** | 移除第 1 章核心原則，保留工作目錄規範、追溯鏈、模板指針、三大分流與 SOP 0~7 流程。 |
| `source/agents-workflow/contributes.format.md` | **New** | 官方 Contributes 擴充宣告格式規格說明書。 |
| `source/agents-workflow/manifest.json` | **Modify** | 註冊 `AgentsStandards.md` export 與 `AGENTS_STANDARDS` Token 宣告。 |
| `source/agents-workflow/config.project.json` | **Modify** | 將 `"release_targets"` 預設值調整為空陣列 `[]`。 |
| `source/agents-workflow/agents_workflow/publisher.py` | **Modify** | 提取 `AgentsStandards` 注入 `AGENTS.md`、落實 `enable_agents_md: false` 守門與支援空 target 發布。 |
| `source/agents-workflow/tests/test_compiler.py` | **Modify** | 新增 `test_ft_09_dual_standards_and_publisher_config_flags` 單元測試。 |
| `docs/agents-workflow/README.md` | **Modify** | 更新模組概覽，加入雙標準資產架構與 `contributes.format.md` 索引。 |
| `docs/agents-workflow/user_guide.md` | **Modify** | 補充 `config.project.json` 開關說明與發布行為。 |
| `CHANGELOG.md` | **Modify** | 追加本次 `sub_09` 發布之高階變更紀錄。 |

---

## 3. 測試與品質驗證結果 (Verification & Quality Audit)

- **模組單元測試**：`python yscb.py dev test agents-workflow` ➔ **21/21 100% Passed**。
- **全模組沙盒端到端回歸**：`python yscb.py dev test --all` ➔ **114/114 100% Ready (47.081s)**。
- **實機 UX / 人工驗證**：開發者指示免測，實機驗證 `AGENTS.md` 軟合併成功精簡至 64 行且特化規則無損。

---

## 4. 📚 知識庫文檔交付驗收對齊表 (Documentation Delivery Audit)

| 維度 | 文件路徑 | 交付狀態 | 驗收重點 |
| :---: | :--- | :---: | :--- |
| **維度 1** | `docs/agents-workflow/README.md` | ✅ 已交付 | 更新雙標準資產定位與 `contributes.format.md` 手冊導引。 |
| **維度 2** | `docs/agents-workflow/user_guide.md` | ✅ 已交付 | 補充 `enable_agents_md` / `release_targets` 等開關說明與發布行為。 |
| **維度 4** | `source/agents-workflow/contributes.format.md` | ✅ 已交付 | 建立完整的 Contributes 擴充宣告格式規格書。 |

---

## 5. 推薦 Commit 訊息 (Conventional Commit Format)

```text
feat(agents-workflow): separate standards and workflow, optimize AGENTS.md and add contributes doc

- Extract core principles and guardrails into AgentsStandards.md
- Refactor DevelopmentStandards.md for complete SOP 0~7 workflow guide
- Update ReleasePublisher to inject minimal AgentsStandards.md into AGENTS.md
- Implement enable_agents_md and enable_project_changelog project config flags
- Set release_targets default to [] in config.project.json
- Add comprehensive contributes.format.md documentation for agents-workflow
- Pass all 114 unit and sandbox integration regression tests
```
