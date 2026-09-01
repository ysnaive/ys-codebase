# 需求討論說明書 (Semantic Requirements Discovery)

> 功能名稱：sub_01_existing_injection_mode_optimization  
> 建立日期：2026-08-31  
> 所屬主計畫：2026_08_31_1718_agents_workflow_architecture_optimization  
> 狀態：Confirmed  
> 計畫類型：Refactor  
> 模板版本：v1.2  

---

## 1. 使用者原始需求與意圖 (User Intent)

- **原始陳述**：
  - `release target 添加 AgentsStandards.md 的投影目標，不再常駐預設輸出至 project://AGENTS.md`
  - `因牽涉到軟合併問題，此為特化設定，固定映射源是 AgentsStandards，增量添加於 release_target { agents_md: "" ("" = 不輸出) }，並移除 config 中的 enable_agents_md 設定`
  - `[P00:DR-03，要把另外兩個的也預設好`
- **核心目標**：
  - **宣告式 `agents_md` 欄位**：在 `release_target` 定義中增量添加 `agents_md: "<path_or_uri>"` 欄位。固定映射來源為 `AgentsStandards.md`，當 `agents_md` 為空字串 `""` 或未指定時不輸出，指定路徑時（例 `"project://AGENTS.md"` 或 `"project://CLAUDE.md"`）對該目標檔案執行軟合併。
  - **移除全域組態**：徹底從 `config.project.json` 中移除 `enable_agents_md` 設定，消除常駐硬編碼特殊處理。
  - **三大預設 Target 規範路徑配置**：
    - `antigravity` ➔ `project://AGENTS.md`
    - `claude` ➔ `project://CLAUDE.md`
    - `codex` ➔ `project://AGENTS.md`
  - **統一發布與清理生命週期**：將軟合併檔案納入 Release Target 的雙軌 Manifest 追蹤集合，在 Target 停用或更換時具備乾淨的清理與自愈能力。
- **邊界排除 (Explicitly Excluded)**：
  - 本子計畫專注於現有 `release_target` 結構優化與發布流水線解耦。
  - Skills 體系引入與 `knowledge-db` 等模組規範大幅下沉保留於 `sub_02` 實施。

---

## 2. 核心討論與決策紀錄 (Discussion & Decisions)

- **[P00:DR-01] `release_target` 增量添加 `agents_md` 欄位取代全域 `enable_agents_md`**：
  - **設計規格**：在 `contributes/agents-workflow.json`（及各模組 declared release targets）之 `release_target` 物件中新增 `agents_md` 欄位：
    - `agents_md: "<uri_or_path>"` ➔ 發布時將 `AgentsStandards.md` 軟合併至指定路徑。
    - `agents_md: ""` (或省略) ➔ 該 Target 不輸出規範檔。
  - **全域組態退場**：從 `config://agents-workflow/config.project.json` 徹底移除 `enable_agents_md`，發布引擎完全依據啟用的 `active_targets` 中各 Target 的 `agents_md` 宣告運作。
- **[P00:DR-02] 軟合併生命週期納入雙軌 Manifest**：
  - 軟合併目標檔案（若有生成）納入該 Target 之 `published_files` 追蹤集合，支援雙軌 Diff 短路檢測與停用時之安全 Pruning。
- **[P00:DR-03] 三大 IDE Targets 預設值配置**：
  - **`antigravity`**：`"agents_md": "project://AGENTS.md"`
  - **`claude`**：`"agents_md": "project://CLAUDE.md"`
  - **`codex`**：`"agents_md": "project://AGENTS.md"`

---

## 3. 開放議題與確認紀錄

- [x] **開放議題 1 (Schema 設計)**：已確認於 `release_target` 物件層級增量添加 `agents_md: ""` 欄位，固定映射源為 `AgentsStandards.md`。
- [x] **開放議題 2 (全域組態清理)**：已確認完全移除 `config.project.json` 中的 `enable_agents_md` 設定。
- [x] **開放議題 3 (三大預設 Target 配置)**：已確認 `antigravity` (`project://AGENTS.md`)、`claude` (`project://CLAUDE.md`) 與 `codex` (`project://AGENTS.md`) 之預設路徑。
