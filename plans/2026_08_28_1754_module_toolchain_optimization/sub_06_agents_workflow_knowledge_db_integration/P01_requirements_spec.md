# 需求規格說明書 (Requirements Specification)

> 功能名稱：Knowledge-DB 與 Agents-Workflow 雙向 Contributes 聯動與 Space 解耦 (Knowledge-DB & Agents-Workflow Bidirectional Contributes & Space Decoupling)  
> 建立日期：2026-08-28  
> 所屬主計畫：`plans://2026_08_28_1754_module_toolchain_optimization/` (sub_06)  
> 狀態：Confirmed  
> 依據 P00：[P00_semantic_requirements.md](./P00_semantic_requirements.md)  
> 模板版本：v1.4  

---

## 1. 功能需求清單 (Functional Requirements)

| 需求編號 | 需求名稱 | 詳細規格描述 | 優先級 | 對應 P00 語意 |
| :--- | :--- | :--- | :---: | :--- |
| **FR-01** | `knowledge-db` 預設空間清空 | `source/knowledge-db/configurable/contribute.json` 預設移除 `project_main` 等硬編碼路徑，維持為空字典 (`spaces: {}`, `thesaurus: []`)，達成模組通用與零硬編碼假設。 | P0 | [P00:核心概念 1] |
| **FR-02** | `agents-workflow` 貢獻 `docs` 空間 | 於 `source/agents-workflow/contributes/knowledge-db.json` 宣告 `spaces.docs`（`include: ["workflow.docs://"]`, `exclude: ["**/__pycache__/**", "**/.git/**"]`），由工作流模組向知識庫宣告文檔空間。 | P0 | [P00:核心概念 1] |
| **FR-03** | 宿主專案特化 `source` 空間宣告 | 於本專案 `config/knowledge-db/contribute.json` 宣告 `spaces.source`（`include: ["project://source", "project://ys_codebase"]`），由宿主專案向知識庫宣告源碼空間。 | P0 | [P00:核心概念 1] |
| **FR-04** | `AgentsStandards.md` 補齊擴充錨點 | 於 `source/agents-workflow/assets/standards/AgentsStandards.md` 底部補齊 `__@{AGENTS_STANDARDS}__`，並於 `agents-workflow.json` 之 `token` 陣列宣告 `token: "AGENTS_STANDARDS"`。 | P0 | [P00:核心概念 2] |
| **FR-05** | `knowledge-db` 平鋪標準資產建立 | 於 `source/knowledge-db/assets/` 建立平鋪資產：`KnowledgeAgentsStandards.md`（檢索優先紀律、Docstring 防護）、`phase00_guild.md`、`research_guild.md`（調研引導 `search` 查找）、`phase07_guild.md`（結案引導 `index` 更新）。 | P0 | [P00:核心概念 3, 4] |
| **FR-06** | `knowledge-db` 對 `agents-workflow` 之 Contributes 宣告 | 於 `source/knowledge-db/contributes/agents-workflow.json` 宣告 `insert` 映射，分別將上述資產注入至 `AGENTS_STANDARDS`、`RESEARCH_AGENTS_GUILD`、`PHASE00_AGENTS_GUILD` 與 `PHASE07_AGENTS_GUILD`。 | P0 | [P00:核心概念 3, 4] |

---

## 2. 邊界與異常情況 (Edge Cases & Failure Modes)

| 邊界編號 | 情境說明 | 預期防禦與處理行為 |
| :--- | :--- | :--- |
| **EC-01** | 未安裝 `knowledge-db` 模組時執行 `agents-workflow release` | `ArtifactCompiler` 遇到未匹配之 Token 錨點時自動清除殘留標籤，產出乾淨之 `AGENTS.md`，不產生殘留字串或錯誤。 |
| **EC-02** | 專案尚未建立 `workflow.docs://` 實體目錄 | `knowledge-db` 在掃描 `docs` 空間時，`FingerprintScanner` 識別為空或略過不存在之路徑，不拋出未捕獲異常。 |
| **EC-03** | `AgentsStandards.md` 雙層軟合併保護 | 即使注入了 `KnowledgeAgentsStandards.md`，`AGENTS.md` 的 Section 4 自訂章節仍 100% 完好保留。 |

---

## 3. 非功能需求 (Non-Functional Requirements)

| 需求編號 | 類別 | 指標與量化約束 |
| :--- | :--- | :--- |
| **NFR-01** | 零代碼修改 (Zero Python Logic Drift) | 100% 透過 Contributes JSON 宣告與 Markdown 資產實現，零修改現有 Python 業務代碼。 |
| **NFR-02** | 發布效能 (Release Performance) | `agents-workflow release` 處理多模組 Contributes 雙階編譯時，總耗時增加量 $< 50\text{ms}$。 |
| **NFR-03** | 測試覆蓋率 (Regression Readiness) | 全生態系 4 大模組沙盒回歸跑測維持 100% Passed。 |

---

## 4. 知識庫與踩坑紀錄查閱 (Known Gotchas & CAUTIONs)

- **`[!NOTE]` 空間宣告職責分離**：`knowledge-db` 作為獨立微內核不應假設專案具備特定源碼目錄，專案自身的源碼空間由 `config/knowledge-db/contribute.json` 宣告，工作流文檔空間由 `agents-workflow` 貢獻。
- **`[!IMPORTANT]` 資產平鋪原則**：所有資產直接放置於 `source/knowledge-db/assets/` 下，簡化 URI 參照路徑 (`module://knowledge-db/assets/<file>.md`)。
