# 語意需求說明書 (Semantic Requirements Discovery)

> 功能名稱：`sub_01_cli_guidance_and_privilege_optimization`  
> 建立日期：2026-08-29  
> 所屬主計畫：`workflow_and_agents_guidance_optimization` (Umbrella Level 2)  
> 狀態：Confirmed  
> 計畫類型：Feature  
> 模板版本：v1.1  

---

## 1. 使用者原始需求與意圖 (User Intent)

- **原始陳述**：
  1. Agents 常常忘記什麼時候該執行/可以用什麼指令優化流程，有時甚至會出現越權調用（如 `release` 應只有在開發者明確授權之情況調用）。希望透過全自動動態計算方案，擴充 commands 宣告並透過 Provider 動態生成全手冊與各 Phase JIT 提示。
  2. 希望 Agent 在日常代碼搜尋時能真正將 `knowledge-db search` 當作預設優先工具，而非被動或頻繁調用原生 `grep_search`。
  3. 採用非侵入式方式，直接在 `knowledge-db` 模組自治的注入資產 (`KnowledgeAgentsStandards.md`) 中強調「🚨 絕對禁止條款」與「工具替代鐵律」，並加入帶 `--ftype` 檔案類型分流（代碼 `ftype=c,cpp,py`、文檔 `ftype=md`）的決策樹。
  4. 微調 `ContextInit.md`：減少初始化過度冗餘資訊。對話初啟時真正需要剛性完整閱讀加深記憶的是 `AgentsStandards`（防呆紀律與工具替代）；而 `DevelopmentStandards.md`（SOP 0~7 細節）則定義為開啟計畫時（`/NewPlan`）必須按需精讀。
  5. 精純化 `AgentsStandards.md`：將不屬於剛性防呆紀律的流程細節或實作說明排除，保持其 100% 聚焦於最高核心原則、絕對禁止條款、工具替代律令與守門邊界。
  6. **規範完整性無損與回歸守門**：本次從 `ContextInit` 與 `AgentsStandards` 排除之流程與指引細節，必須保證 100% 完整收斂至對應的細讀文檔（如 `DevelopmentStandards.md`、各 Phase JIT 引導 `PHASE00~07_AGENTS_GUILD` 等），確保專案知識與流程規範零遺失。
- **核心目標**：
  1. **SSOT 結構擴充**：擴充 `contributes.core.commands` 結構定義，新增 `tier`（`safe` | `conditional` | `gated`）與 `phases`（適用之 SOP 階段清單，如 `["P05", "P06", "FT-2"]`）。
  2. **三級權限分級矩陣**：
     - 🟢 `safe` (自主安全)：沙盒跑測、靜態合規預檢、知識檢索、計畫狀態查詢等，Agent 可自主主動調用。
     - 🟡 `conditional` (階段約束)：如 `--no-build` 快速單元跑測、單用例篩選 `-k`，受特定除錯與開發階段條件約束。
     - 🔴 `gated` (授權守門)：如 `dev release`、`dev bump-*`、`install --force`、`plan archive` 等高危/發布操作，嚴格限制僅在開發者 Prompt 顯式指示授權下方可執行。
  3. **動態編譯升級 (`AgentsCliGuild.md`)**：升級 `core.providers.get_agents_cli_guild()`，輸出帶有權限顏色標籤（🟢/🟡/🔴）、適用階段與防呆說明的結構化表格。
  4. **Phase-Aware JIT 動態引導注入**：提供動態 Provider（如 `get_phase_cli_guild`），供 `agents-workflow` 自動將各階段允許指令與紅線禁忌動態注入至 `PHASE00_AGENTS_GUILD` ~ `PHASE07_AGENTS_GUILD`、`FAST_TRACK_AGENTS_GUILD`、`RESEARCH_AGENTS_GUILD` 等模板註解頂部。
  5. **Knowledge-DB 日常檢索鐵律與 `--ftype` 決策樹強化 (非侵入式)**：
     - 修訂 `source/knowledge-db/assets/KnowledgeAgentsStandards.md`，納入最高等級的「🚨 執行紀律：日常代碼搜尋強制工具替代」條款，明文禁止以 `grep_search` 進行模糊探索或盲目 `list_dir` / `view_file`。
     - 加入明確的 `--ftype` 決策樹：
       - 搜索代碼：`python yscb.py knowledge-db search '<query>' --ftype=c,cpp,py -s`
       - 搜索文檔/SOP：`python yscb.py knowledge-db search '<query>' --ftype=md -s`
       - 廣義探索：`python yscb.py knowledge-db search '<query>' -s`
  6. **ContextInit 與 DevelopmentStandards 職責解耦**：
     - 修訂 `ContextInit.md`：聚焦於 `AgentsStandards`（或 `AGENTS.md`）之剛性必讀，建立最高防呆紀律反射與檢索工具替代記憶，去除初期無效 Token 負擔。
     - 將 `DevelopmentStandards.md`（SOP 0~7、追溯鏈矩陣與模板規範）明確定調為 **「開啟/推進計畫時（如 `/NewPlan`、`/Continue`）按需精讀」**。
  7. **AgentsStandards 剛性紀律純化與規範無損鏡像**：
     - 審核並修訂 `AgentsStandards.md`，將非通用硬性紀律的過度冗長流程細節剝離至 `DevelopmentStandards.md` 與對應 Phase JIT Guilds。
     - 建立剛性回歸檢核：保證被剝離之內容在對應細讀文檔 100% 完整被涵蓋，無任何規範資訊丟失。
  8. **全模組 Contributes 補齊**：更新全生態系模組（`core`, `dev`, `knowledge-db`, `agents-workflow`）之 `contributes/core.json` 宣告，全面落實分級與階段標註。
- **邊界排除 (Explicitly Excluded)**：
  - 不修改底層 CLI 指令的業務邏輯或命令列參數解析（各指令實作維持原樣）。
  - 不侵入式修改 `agents-workflow` 的通用注入框架與 Token 錨點，`knowledge-db` 的行為準則強化完全自包含於 `KnowledgeAgentsStandards.md`。
  - 維持向下相容：若第三方模組未宣告 `tier` 或 `phases`，系統自動安全 fallback（預設 `tier: conditional`, `phases: []`）。

---

## 2. 核心討論與決策紀錄 (Discussion & Decisions)

- **[P00:DR-01] 採用全自動動態計算方案**：
  捨棄手動維護多份靜態 Markdown 檔案的作法，改以 `contributes/core.json` 內的 `commands` 宣告為唯一真理來源 (SSOT)，透過 `core.providers` 自動衍生全系統手冊與各階段 JIT 模板註解。
- **[P00:DR-02] 確立三大權限級別 (3-Tier Privilege Matrix)**：
  明確劃分 `safe`（🟢 自主）、`conditional`（🟡 階段）、`gated`（🔴 守門），並於全手冊與 JIT 引導中形成統一視覺標誌與防呆守門條款。
- **[P00:DR-03] 採用模組自治非侵入式 Knowledge-DB 強制工具替代與 `--ftype` 決策樹**：
  不修改全域模板架構，直接在 `source/knowledge-db/assets/KnowledgeAgentsStandards.md` 注入最高優先級的「🚨 執行紀律：日常代碼搜尋強制工具替代」條款，並整合 `--ftype=c,cpp,py` 與 `--ftype=md` 分流指引，壓制 Agent 對原生 `grep_search` 的模糊調用慣性。
- **[P00:DR-04] ContextInit 與 DevelopmentStandards 職責分離與認知減負**：
  `ContextInit.md` 聚焦於剛性建立 `AgentsStandards` 防呆反射與基本狀態掌握；`DevelopmentStandards.md` 的 SOP 細節讀取則遞延至進入 `/NewPlan` 開啟計畫時按需執行。
- **[P00:DR-05] AgentsStandards 剛性紀律純化與規範無損鏡像**：
  精確定位 `AgentsStandards.md` 為「純剛性行為準則與防呆禁令」，將非防呆禁令之流程與操作指引無損轉移至 `DevelopmentStandards.md` 及各 Phase JIT 引導資產中，確保專案規範體系零缺漏。

---

## 3. 開放議題與確認紀錄

- [x] 確認採用全自動動態計算（`commands` 宣告 ➔ Provider 動態生成手冊與 JIT 引導）。
- [x] 確認採用非侵入式 `KnowledgeAgentsStandards.md` 內部強化與 `--ftype` 決策樹。
- [x] 確認 `ContextInit.md` 與 `DevelopmentStandards.md` 職責分離原則。
- [x] 確認 `AgentsStandards.md` 剛性純化與無損收斂至細讀文檔原則。
