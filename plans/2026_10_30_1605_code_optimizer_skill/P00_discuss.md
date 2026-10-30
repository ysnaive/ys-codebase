# 需求討論說明書 (Semantic Requirements Discovery)

> 功能名稱：2026_10_30_1605_code_optimizer_skill  
> 建立日期：2026-10-30  
> 所屬主計畫：N/A  
> 狀態：Confirmed  
> 模型：Gemini 4 Argon (High)  

> 計畫類型：Feature  
> 模板版本：v1.2  

---

## 1. 使用者原始需求與意圖 (User Intent)

- **原始陳述**：評估下游提供之《`code-optimizer` 核心架構設計提案報告》，並納入 `agents-workflow` 核心標準技能體系；要求完全不主動觸發（僅由開發者手動顯式觸發）、開始前先向開發者詢問檢視範圍（全專案 / 單一模組 / 單一檔案，且大範圍包含小範圍分析項目）與生命週期模式（`Mode A` 收斂期 vs. `Mode B` 維護期，不由 Agent 自行猜測，且 `Mode B` 下若嚴格確認純屬內部工具函式亦允許破壞性收斂），並先行建立調研計畫（`R01`）完成靜態診斷後向開發者詢問流轉出口。
- **核心目標**：
  1. 於 `ys_codebase/source/agents-workflow/assets/skills/code-optimizer/` 建立 `SKILL.md` 與漸進式揭露 `references/` 資產（涵蓋探索與子代理委派契約、跨語言五維度靜態診斷矩陣 `D1~D5`、六大通用軟工重構策略庫 `S1~S6` 及防過度設計四大紅線）。
  2. 落實 **100% 純手動觸發** 與 **前置雙維度定錨（包含式三層範圍 × 開發者裁定之 `Mode A / Mode B` 生命週期）**。
  3. 標準化對接 `agents-workflow` 之 **調研計畫 (`Research Plan`: `P00` + `R01` + `changelog.md`) $\to$ 三大流轉出口裁決（出口 ① 原地升級 `Fast Track` / `Full Track` / `Umbrella` 實作、出口 ② 轉入 `Roadmap` / `TODO`、出口 ③ `Concluded` 維持現狀結案）** 閉環。
  4. 於 `contributes/agents-workflow.json` 註冊 `code-optimizer` 技能導出與 Stage 1 擴充錨點 `CODE_OPTIMIZER_STANDARDS`，導入 Stage 2 宿主專有名詞佔位符（`` `__%{agent_tool.*}__` ``），並同步更新 `development-sop`、`skill-creator` 錨點地圖、三層文檔與單元測試。
- **邊界排除 (Explicitly Excluded)**：
  - 不掛載於 `AGENTS.md` 被動條件路由表（`AGENTS_SKILL_ROUTING`），嚴禁在日常開發流程中自動攔截觸發。
  - 不負責測試案例設計與存量測試集純化（交由 `testing-sop` 正交處理）。
  - 不負責 AI 技能目錄（`SKILL.md`）審查與 A/B 評測（交由 `skill-optimizer` 正交處理）。
  - 不將業務程式碼結構重構導向 `Revision Plan`（`Revision Plan` 嚴格限於非業務邏輯之表層修訂）。
- **架構影響範圍**：
  - `ys_codebase/source/agents-workflow/assets/skills/code-optimizer/`（新增 `SKILL.md` 與 `references/`）
  - `ys_codebase/source/agents-workflow/contributes/agents-workflow.json` 與 `_manifest.md`（新增 `code-optimizer` export 與 `CODE_OPTIMIZER_STANDARDS` token）
  - `ys_codebase/source/agents-workflow/assets/skills/development-sop/SKILL.md`（§1 中樞導流新增 `code-optimizer` 指針）
  - `ys_codebase/source/agents-workflow/assets/skills/skill-creator/`（更新全系統標準 Stage 1 錨點數量與列表）
  - `ys_codebase/source/agents-workflow/tests/test_compiler.py`（或對應子系統測試檔，擴充 `code-optimizer` 資產與錨點驗證）
  - `docs/agents-workflow/{README.md,user_guide.md}`（同步技能清單與使用指南）

---

## 2. 核心討論與決策紀錄 (Discussion & Decisions)

- **[P00:DR-01] 100% 純手動觸發與主動指令型極簡 `description` 契約**：
  - `code-optimizer` 採純顯式呼叫設計，不寫入 `AgentsStandards.md` 條件式技能分流導航矩陣。
  - Frontmatter 與 `contributes/agents-workflow.json` 之 `description` 遵循主動指令型極簡契約：`針對既有業務程式碼執行五維度靜態診斷、業務階段邏輯聚合與行為無損重構。僅於顯式輸入 /code-optimizer 時觸發，嚴禁主動觸發。`；詳細正向適用情境與負向排除邊界收錄於 `SKILL.md` 內文並由 `development-sop/SKILL.md` 中樞導流。
- **[P00:DR-02] 步驟 1 前置雙維度定錨（包含式三層範圍 × 開發者顯式指定 `Mode A / Mode B`）**：
  - 觸發 `/code-optimizer` 後，在建立調研計畫與掃描代碼前，若開發者未明確指定，強制先向開發者詢問確認：
    1. **檢視範圍（包含式階層 `全專案 ⊃ 單一模組 ⊃ 單一檔案`）**：大範圍完整包含小範圍之微觀診斷與重構策略（例如單一模組或全專案分析均包含模組內各檔案的 `S1` 業務階段拆解、`S2` 無狀態邏輯剝離、`S3~S5` 收斂與 `S6` 拆檔，並向上疊加跨檔/跨模組耦合與入口治理）。
    2. **生命週期模式（嚴禁 Agent 自行猜測）**：由開發者明確指定為 **`Mode A：收斂期 / 允許破壞性清理 (Convergence Mode)`**（強制單一正統入口、零容忍清除過渡別名與轉發層，同步更新所有調用點）或 **`Mode B：維護期 / 嚴守向下相容 (Compatibility Mode)`**（對外公開入口與插件契約強制門面重匯出保持 100% 簽名相容；但**若經全空間調用圖譜與匯出清單「嚴格查驗」確認純屬內部工具函式且 0 外部跨模組調用，則同樣直接執行破壞性收斂與清理**，嚴禁為純內部工具函式保留冗餘轉發層）。
- **[P00:DR-03] 先建調研計畫 (`R01`) 落檔診斷報告、後詢問三大流轉出口之標準閉環**：
  - 確認範圍與 `Mode A/B` 後，依 JIT 原則於 `plans/` 建立調研計畫（`P00_discuss.md` + `R01_code_optimization_audit.md` + `changelog.md`）。
  - 探索階段結合量化規模門檻調度支柱一唯讀探索子代理（單檔 $> 400$ 行、$\ge 3$ 檔或跨模組多階調用追蹤時委派子代理，回傳 $\le 400$ Tokens 結構化表格，嚴禁傾倒原始碼；子代理嚴格依開發者拍板之 `Mode A/B` 盤點調用點與公開契約）。
  - 將 `D1~D5` 病灶座標表（P0/P1/P2）與 `S1~S6` 重構處方箋落檔於 `R01_code_optimization_audit.md`，呈遞極簡調研診斷卡並強制 End Turn，詢問開發者選擇三大流轉出口：
    - **出口 ① 立即升級實作**：將 `R01` 標記 `Concluded`，依範圍與變更規模原地無痛升級為 `Fast Track`（$\le 100$ 行、0 公開 API 變更）、`Full Track`（追加 `P01~P07`）或 `Umbrella`（全專案多模組拆分子計畫），執行無損重構、回歸測試與 Before/After 量化對照。
    - **出口 ② 轉入技術儲備**：將重構藍圖登錄至 `/roadmap` 或 `/todo` 並標記 `R01` 為 `Concluded`。
    - **出口 ③ 維持現狀結案**：健康度良好無須動刀，標記 `R01` 與 `P00` 為 `Concluded` / `Completed` 歸檔留存。
- **[P00:DR-04] 漸進式揭露拓撲、Stage 1 `CODE_OPTIMIZER_STANDARDS` 錨點與 Stage 2 宿主專有名詞對接**：
  - 採用 `SKILL.md` 主控層（內建 `D1~D5` 與 `S1~S6` 速查索引表、四大防過度設計紅線與步驟檢核表）搭配單層 `references/`（`exploration-and-delegation.md`、`diagnostic-matrix.md`、`refactoring-playbook.md`），確保按階段精準讀取。
  - 於 `contributes/agents-workflow.json` 新增第 24 個標準 Stage 1 Token `CODE_OPTIMIZER_STANDARDS`（置於 `code-optimizer/SKILL.md` 尾部），供各專案注入專屬 `D5` 架構慣例與驗證指令；內文工具指稱全面採用 `` `__%{agent_tool.*}__` `` 支援多平台投影。

---

## 3. 開放議題與確認紀錄

- **[已確認] 觸發與計畫流轉模式**：100% 純手動觸發（`/code-optimizer`），先建立調研計畫產出 `R01` 診斷報告，完成後向開發者詢問三大流轉出口。
- **[已確認] 前置雙維度詢問（包含式範圍 × 生命週期模式）**：開始前向開發者確認檢視範圍（全專案 ⊃ 單一模組 ⊃ 單一檔案）與生命週期模式（`Mode A` vs. `Mode B` 由開發者指定，不由 Agent 自行判斷）。
- **[已確認] `Mode B` 內部工具函式收斂規則**：`Mode B` 下若經嚴格查驗確認為純內部工具函式（非公開匯出契約且 0 外部跨模組調用），允許直接執行破壞性變更與收斂。

