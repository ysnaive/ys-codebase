# 成果展示與結案報告 (Walkthrough)

> 功能名稱：跨模組組態體檢教練 (/how-to-config-yscb)、互動式上手領航教練 (/how-to-yscb) 與專案角色邊界錨點建設 (Onboarding & Config Coaching Skills)  
> 建立日期：2026-10-24  
> 所屬主計畫：[2026_10_23_1314_agents_workflow_aci_and_delegation_evolution](../umbrella_overview.md)  
> 狀態：Completed  
> 模型：Gemini 4 Argon (Low)  

> 模板版本：v1.4  

---

## 1. 變更概述 (Executive Summary)

- **核心功能落地**：
  1. **`PROJECT_ROLE_AND_BOUNDARIES` 空間邊界錨點與 `context-init` 熱啟動提取 (`FR-01`)**：於 `AgentsStandards.md` 頂部（`## 1. 核心原則` 之前）增設獨立行錨點 `` `__@{PROJECT_ROLE_AND_BOUNDARIES}__` ``；同步更新 `context-init/SKILL.md` 熱啟動提取規則與底部 `/how-to-yscb`、`/how-to-config-yscb` 指引（專案層級之 `project_role.md` 與 `testing_guide.md` 交由 `/how-to-config-yscb` 實機探勘草擬與確認後代寫）。
  2. **跨模組組態體檢與自適應配置教練 (`/how-to-config-yscb`) (`FR-02`)**：建立 `how-to-config-yscb/SKILL.md` 與 `HOW_TO_CONFIG_MODULES` 動態聚合錨點，落實四步閉環（Step 1 自動空間探勘與健康檢查、Step 2 全綠健康短路 `All-Green Short-Circuit` 與單次探勘三位一體對齊草案 `First-Party Trinity Alignment` 含動態解析二層物化唯讀空間、Step 3 引導寫入與 `contributes check` / `compile` / `release` 三步驗證守門、Step 4 潔淨對話切換提示）。
  3. **互動式上手與實戰領航教練 (`/how-to-yscb`) (`FR-03`)**：建立 `how-to-yscb/SKILL.md` 與 `HOW_TO_YSCB_MODULES` 動態聚合錨點，內建資深教練角色切換（`Coach / Mentor Persona` 與極簡狀態卡豁免）、雙入口自適應領航（無參數呈現模組總覽與開放式 `A~D` 切入角度選單 vs. 帶具體問題跳過選單直接解答）、兩階段漸進式知識調度（先依內建速查面板秒答，追問深層細節時按需讀取隨包手冊）、純唯讀教練護欄與新對話一鍵啟動指令塊。
  4. **四大核心模組指南片段與擴充點註冊 (`FR-04`, `NFR-01`)**：於 `core`、`dev`、`server`、`knowledge-db` 四大模組各新增 15~25 行之三要素結構 `assets/config_guide.md` 與 `assets/usage_guide.md`（底部皆含單反引號包覆之隨包手冊連結 `` [`<mod> 隨包手冊`](`__#{module://<mod>/README.md}__`) ``），並完成 `contributes/agents-workflow.json` 與 `_manifest.md` 註冊。
  5. **編譯器跨模組 Sibling Fallback、Token 雙欄位相容與宿主 NTFS 歷史大寫目錄正名 (`FR-05`, `NFR-02`)**：修正 `ArtifactCompiler._resolve_source_path()` 針對跨模組 `module://<mod>/...` 自動解析至同級兄弟模組目錄；修正 `scripts/cli.py:tokens()` 同時支援 `value` 與 `name` 欄位；並對宿主 NTFS 歷史遺留大寫目錄（`source/{core,dev,server,knowledge-db}/Scripts` 與 `docs/Core`）完成一次性兩段式正名，根除跨平台 `virtiofs` 大小寫雙影與 `--sync` 解壓衝突。

---

## 2. 變更檔案清單 (Changed Files Inventory)

| 檔案路徑 | 變更類型 | 變更說明 |
| :--- | :---: | :--- |
| `ys_codebase/source/agents-workflow/agents_workflow/compiler.py` | Modify | `_resolve_source_path()` Step 2 新增跨模組 `module://<mod>/...` sibling fallback 解析 |
| `ys_codebase/source/agents-workflow/scripts/cli.py` | Modify | `tokens()` 同時支援讀取 `value` 或 `name` 欄位 |
| `ys_codebase/source/agents-workflow/assets/standards/AgentsStandards.md` | Modify | 頂部新增 `` `__@{PROJECT_ROLE_AND_BOUNDARIES}__` `` 獨立行錨點 |
| `ys_codebase/source/agents-workflow/assets/skills/context-init/SKILL.md` | Modify | 新增專案角色與空間邊界提取要點及 `/how-to-yscb`、`/how-to-config-yscb` 提示 |
| `ys_codebase/source/agents-workflow/assets/skills/how-to-config-yscb/SKILL.md` | New | 建立專案空間自適應配置與跨模組組態體檢教練技能 |
| `ys_codebase/source/agents-workflow/assets/skills/how-to-yscb/SKILL.md` | New | 建立生態系互動式上手與實戰領航教練技能 |
| `ys_codebase/source/agents-workflow/contributes/agents-workflow.json` | Modify | 匯出 `how-to-config-yscb`、`how-to-yscb` 並註冊 `PROJECT_ROLE_AND_BOUNDARIES`、`HOW_TO_CONFIG_MODULES`、`HOW_TO_YSCB_MODULES` |
| `ys_codebase/source/{core,dev,server,knowledge-db}/assets/{config_guide.md,usage_guide.md}` | New | 建立四大核心模組之設定體檢指南與使用速查面板（共 8 檔，各 15~25 行） |
| `ys_codebase/source/{core,dev,server,knowledge-db}/contributes/{agents-workflow.json,_manifest.md}` | New / Modify | 註冊四大模組對 `HOW_TO_CONFIG_MODULES` 與 `HOW_TO_YSCB_MODULES` 之注入，並為 `knowledge-db` 補齊 `value: "KNOWLEDGE_DB_SPACE"` |
| `ys_codebase/source/agents-workflow/tests/{test_plans_model_record.py,test_compiler.py}` | Modify | 新增 `test_ft_10_sub04_onboarding_and_config_coaching_skills` 與 `test_resolve_source_path_cross_module_and_tokens_cli` |
| `ys_codebase/source/agents-workflow/README.md`、`docs/agents-workflow/{README.md,user_guide.md,DESIGN_NOTES.md}` | Modify | 同步更新三層文檔與 `[DN-AW-13]` |

---

## 3. 測試與品質驗證結果 (Verification & Quality Audit)

- **自動化測試通過率**：5 大模組沙盒回歸測試與 `@build` 熱同步 **595/595 (100.0%)** 全數通過（`core`: 193/193、`dev`: 79/79、`server`: 40/40、`knowledge-db`: 150/150、`agents-workflow`: 133/133）；`dev check --all` (`5/5 PASS`)、`contributes check` (`14 files PASS`)。
- **實機 UX / 人工驗證**：`UX-01` 經開發者確認 **`[測試通過]`**；支柱三 Pre-UX 唯讀冷眼盲審 Subagent 回傳 `REVIEW_STATUS: PASSED`。

---

## 4. SOP Review 三層文檔與品質審查 (Three-Tier Review)

### 4.1 三層文檔交付對齊表
| 維度 | 文件路徑 | 交付狀態 | 驗收重點 |
| :--- | :--- | :---: | :--- |
| **宏觀 (Macro)** | `CHANGELOG.md` | 已完成 | 已追加 `sub_04_onboarding_and_config_coaching (Completed)` 完整變更摘要 |
| **中觀 (Meso)** | `docs/agents-workflow/README.md`、`ys_codebase/source/agents-workflow/README.md` | 已完成 | 同步更新 16 項技能清冊、Slash 指令表與新增之 3 個擴充錨點說明 |
| **中觀 (Meso)** | `docs/agents-workflow/user_guide.md` | 已完成 | 新增 §7 互動式配置教練 (`/how-to-config-yscb`)、實戰領航 (`/how-to-yscb`) 與 `PROJECT_ROLE_AND_BOUNDARIES` 指南 |
| **中觀 (Meso)** | `docs/agents-workflow/DESIGN_NOTES.md` | 已完成 | 新增 `[DN-AW-13]` 記錄跨模組多捐贈者導覽錨點、兩階段隨包手冊調度與 Sibling Fallback 防坑設計 |
| **微觀 (Micro)** | `compiler.py`、`cli.py` | 已完成 | 維護清晰之步驟註解與跨模組路徑解析說明 |

### 4.2 品質與清理檢核
- [x] **代碼清理**：無死代碼、無除錯 print/log、無敷衍之 quick-and-dirty hack。
- [x] **測試完整覆蓋**：所有單元測試與整合測試 100% 通過，無跳過或被破壞之斷言。

---

## 5. 推薦 Commit 訊息 (Conventional Commit Format)

```text
feat(agents-workflow,ecosystem): add /how-to-config-yscb, /how-to-yscb, PROJECT_ROLE_AND_BOUNDARIES anchor, and 4-module guides (sub_04)
```

---

## 6. 計畫結構合規檢核 (Plan Compliance Verification)

- [x] **完成狀態確認**：所有前置階段、代碼實作、SOP 審查與測試驗證均已落實完成，本檔其餘檢核項已勾選 `[x]` 且頂部標頭 `> 狀態：` 已設為 `Completed`。
- [x] **結構與註解檢核（最終守門）**：最後實機執行 `python yscb.py agents-workflow plan verify <plan_name>` 驗證 100% Passed（若檢出未通過項則原地修正重驗）。

