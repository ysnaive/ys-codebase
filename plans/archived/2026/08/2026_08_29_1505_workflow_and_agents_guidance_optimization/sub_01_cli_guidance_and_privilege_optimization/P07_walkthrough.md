# 成果展示與結案報告 (Walkthrough)

> 功能名稱：`sub_01_cli_guidance_and_privilege_optimization`  
> 建立日期：2026-08-29  
> 所屬主計畫：`workflow_and_agents_guidance_optimization` (Umbrella Level 2)  
> 狀態：Completed  
> 模板版本：v1.4  

---

## 1. 變更概述 (Executive Summary)

- **核心功能落地**：
  1. **CLI 宣告 Schema 擴充與三級權限分級**：在 `contributes.core.commands` 擴充 `tier` (`safe` / `conditional` / `gated`) 與 `phases` (適用 SOP 階段清單) 元資料，並於全生態系 4 大模組 26 個指令完成補齊與收斂。
  2. **動態 CLI 防呆手冊與 Phase JIT 提示產生器**：在 `core.providers` 實作 `get_agents_cli_guild`（輸出帶 🟢/🟡/🔴 標籤之對照表）與 `get_phase_cli_guild`（依 Phase 動態過濾推薦指令與守門禁令）。
  3. **Knowledge-DB 搜尋鐵律與 `--ftype` 決策樹**：非侵入式於 `KnowledgeAgentsStandards.md` 強化日常搜尋強制工具替代，確立代碼搜尋 `--ftype=c,cpp,py` 與文檔搜尋 `--ftype=md` 分流決策樹。
  4. **ContextInit 與 Standards 職責解耦與純化**：`ContextInit.md` 聚焦於 `AgentsStandards` 核心防呆反射，消除對下游模組的硬編碼；`AgentsStandards.md` 剛性純化為四大全域防呆，將 SOP 階段操作敘事精準歸位至 `DevelopmentStandards.md`。
  5. **消除軟合併遞迴與外層重複標題**：移除 `agents-workflow` 對 `AGENTS_STANDARDS` 的自引用 `insert`，消滅 `AGENTS.md` 內部重複區塊與外層多餘 H1 標題。

---

## 2. 變更檔案清單 (Changed Files Inventory)

| 檔案路徑 | 變更類型 | 變更說明 |
| :--- | :---: | :--- |
| `source/core/contributes.format.md` | Modify | 補充 `commands` 之 `tier` 與 `phases` 宣告規範說明 |
| `source/core/core/providers.py` | Modify | 實作三級權限表格渲染 `get_agents_cli_guild` 與 JIT 過濾器 `get_phase_cli_guild` |
| `source/core/tests/test_cli_guild.py` | Modify | 新增 FT-01~02、ET-01~02 單元測試，覆蓋三級權限與邊界容錯 |
| `source/core/contributes/core.json` | Modify | 標註 9 大宿主指令之 `tier` 與 `phases`，優化 `install` 與 `config` 之 pros/cons |
| `source/dev/contributes/core.json` | Modify | 標註 11 大 dev 工具鏈指令之 `tier` 與 `phases` |
| `source/knowledge-db/contributes/core.json` | Modify | 標註 6 大 knowledge-db 指令之 `tier` 與 `phases` |
| `source/knowledge-db/assets/KnowledgeAgentsStandards.md` | Modify | 強化日常搜尋強制工具替代與 `--ftype` 決策樹 |
| `source/agents-workflow/contributes/core.json` | Modify | 標註 7 大 agents-workflow 指令之 `tier` 與 `phases` |
| `source/agents-workflow/contributes/agents-workflow.json` | Modify | 移除 `AGENTS_STANDARDS` 自引用 `insert` 項目，徹底消除遞迴軟合併 |
| `source/agents-workflow/agents_workflow/publisher.py` | Modify | 優化全新 `AGENTS.md` 初始化模板，避免外層重複 H1 標題 |
| `source/agents-workflow/assets/standards/AgentsStandards.md` | Modify | 剛性純化為核心防呆四重奏，剝離特定 SOP 階段操作敘事 |
| `source/agents-workflow/assets/standards/DevelopmentStandards.md` | Modify | 補充模板註解剝除規範與 Phase 7 / FT-3 結案 `plan verify` 檢核鐵律 |
| `source/agents-workflow/assets/standards/AgentsCliGuild.md` | Modify | 剝離底部靜態重複章節，回歸 100% 動態表格生成 |
| `source/agents-workflow/assets/workflows/ContextInit.md` | Modify | 解耦模組專屬敘述，泛化為模組特化紀律指引 |
| `source/agents-workflow/assets/templates/P07_walkthrough.md` | Modify | 追加 Section 6 計畫結構合規檢核清單 |
| `source/agents-workflow/assets/templates/fast_track_plan.md` | Modify | 追加 FT-3 計畫結構合規檢核清單 |
| `docs/knowledge-db/README.md` | Modify | 補充 `--ftype` 分流檢索範例 |

---

## 3. 測試與品質驗證結果 (Verification & Quality Audit)

- **自動化測試通過率**：全生態系四大模組 **208 / 208 Passed (100% Ready)**
  - `core` 模組：`59/59 Passed` (0.911s)
  - `dev` 模組：`50/50 Passed` (3.581s)
  - `knowledge-db` 模組：`59/59 Passed` (1.366s)
  - `agents-workflow` 模組：`40/40 Passed` (9.328s)
  - 靜態合規檢核 (`dev check`)：4/4 模組 100% `PASSED`
- **實機 UX / 人工驗證**：
  - [x] `AgentsCliGuild.md` 三級權限標籤 (🟢/🟡/🔴) 渲染清晰，守門邊界明確。
  - [x] `ContextInit.md` 熱啟動簡報乾淨聚焦，SOP 0~7 成功遞延至開立計畫時精讀。
  - [x] `AGENTS.md` 單一 H1 標題、純粹全域防呆四重奏 + 知識庫搜尋鐵律與決策樹。
  - [x] `AgentsStandards.md` 剛性純化，非剛性 SOP 操作敘事 100% 歸位至 `DevelopmentStandards.md`。

---

## 4. 📚 知識庫文檔交付驗收對齊表 (Documentation Delivery Audit)

| 維度 | 文件路徑 | 交付狀態 | 驗收重點 |
| :---: | :--- | :---: | :--- |
| **維度 1 (規範)** | `source/core/contributes.format.md` | ✅ 已交付 | `commands` 之 `tier` 與 `phases` 宣告規格說明。 |
| **維度 2 (指南)** | `source/agents-workflow/assets/standards/DevelopmentStandards.md` | ✅ 已交付 | 模板註解剝除規範與 Phase 7 實機 `plan verify` 檢核鐵律。 |
| **維度 3 (知識庫)** | `docs/knowledge-db/README.md` | ✅ 已交付 | 補充 `--ftype` 分流檢索使用範例。 |

---

## 5. 推薦 Commit 訊息 (Conventional Commit Format)

```text
feat(cli-guidance): implement 3-tier privilege CLI guild, JIT phase guidance, and standards crystallization

- Extend contributes.core.commands schema with 'tier' (safe/conditional/gated) and 'phases'
- Implement get_agents_cli_guild (3-tier table) and get_phase_cli_guild in core.providers
- Enforce mandatory Knowledge-DB search tool substitution with --ftype decision tree
- Decouple ContextInit from downstream module details and focus on AgentsStandards warmup
- Crystallize AgentsStandards into pure core guardrails and eliminate soft-merge duplication
- Add plan verify compliance gate to Phase 7 / FT-3 and documentation comment stripping rule
```

---

## 6. 計畫結構合規檢核 (Plan Compliance Verification)

- [x] **結構與註解檢核**：實機執行 `python yscb.py agents-workflow plan verify 2026_08_29_1505_workflow_and_agents_guidance_optimization/sub_01_cli_guidance_and_privilege_optimization` 驗證 100% Passed。
