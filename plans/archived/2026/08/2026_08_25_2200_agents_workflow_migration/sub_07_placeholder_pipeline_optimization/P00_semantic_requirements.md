# 語意需求說明書 (Phase 0: Semantic Requirements)

> 功能名稱：佔位符解析管線優化 (Placeholder Pipeline Optimization)  
> 建立日期：2026-08-26  
> 所屬主計畫：[2026_08_25_2200_agents_workflow_migration](../umbrella_overview.md)  
> 狀態：Confirmed  
> 模板版本：v1.3  

---

## 1. 原始意圖與核心痛點 (Problem Statement)

1. **Agent 模板與規範尋址盲區**：
   - 目前 `DevelopmentStandards.md` 與各工作流中規定「產出文件必須 100% 嚴格鏡像標準模板結構」，但未給出模板實體或相對路徑指針。
   - Agent 面對 `view_file` 工具時，若無明確路徑，容易退化為大語言模型記憶拼湊（憑空臆測），破壞「零臆測 (Zero Speculation)」與格式一致性。
2. **語意協議與物理工具鏈之鴻溝**：
   - 模組原始資產（Source Assets）必須使用通用語意 URI（`module.root://`、`workflow.templates://`）以維持與宿主專案路徑解耦。
   - 但 Agent 工具（`view_file`）與 IDE Markdown 預覽器只認本機實體相對路徑。
   - 預留之路徑佔位符 `__#{uri}__` 尚未接入即時轉譯管線，導致物化產物無法直接原生跳轉與讀取。

---

## 2. 核心架構共識與標準管線語意 (The 6-Stage Semantic Pipeline)

工廠編譯發布管線標準化為以下 6 大階段：

```text
[1. 啟動] ──► [2. 段落佔位符解析] ──► [3. 釋出環境解析] ──► [4. URI 佔位符解析] ──► [5. 文件產出] ──► [6. 結束]
```

### 管線階段語意與職責分工：

1. **階段 1：啟動 (Startup & Manifest Aggregation)**
   - 搜集全系統已安裝模組貢獻之 `contributes`（`export`、`insert`、`token`）。
   - 初始化編譯器狀態機與執行期上下文 `ExecutionContext`。
2. **階段 2：段落佔位符解析 (Stage 1: Content & Block Token Resolution)**
   - 專注解算 `__@{token}__` 內容插入佔位符（`const` / `uri` / `computed`）。
   - 執行 5-Step 多輪遞迴狀態機收斂與殘留標籤安全抹除。
   - 中繼產物物化寫入 **`cache.root://agents-workflow/resolved_contents/`**。
3. **階段 3：釋出環境解析 (Stage 2A: Release Environment Resolution)**
   - **`release_target` 貢獻體系與 Schema 定案**：
     - 模組可在 `manifest.json` 中宣告 `release_target`，定義各類別資產之投影規則：
       ```json
       {
         "name": "antigravity",
         "description": "Google Antigravity IDE 原生 Slash Commands 與標準規範輸出",
         "projections": {
           "workflow": {
             "target_dir": "project://.agents/workflows",
             "extension": ".md",
             "header": [
               "---",
               "description: {export.description}",
               "---"
             ]
           },
           "template": {
             "target_dir": "project://.agents/templates",
             "extension": ".md"
           },
           "standard": {
             "target_dir": "project://.agents/standards",
             "extension": ".md"
           }
         }
       }
       ```
     - **純文字/陣列 Header 模板**：採用所見即所得之 `header: str | list`，支援 `{export.description}`、`{export.name}` 等巨集動態插值，零語法綁定與零外部庫依賴。
     - **組態升級 (`config.project.json`)**：
       - 移除原寫死之 `"ide": []`，改用 `"release_targets": []` 儲存啟用之 target 名稱清單（例 `["antigravity"]`），支援多環境同時輸出。
   - **原生特化開關治理 (Native Switches in config.project.json)**：
     - **`enable_agents_md`** (bool, 預設 true)：控制專案根目錄 `project://AGENTS.md` 軟合併注入 (`<!-- YSCB_AGENTS_BEGIN -->...<!-- YSCB_AGENTS_END -->`)。
     - **`enable_project_changelog`** (bool, 預設 true)：控制專案根目錄 `project://CHANGELOG.md` 之啟用與結案追溯。
     - 不開放過度設計之通用 Integrations 宣告，收斂為 `agents-workflow` 原生特化處理。
4. **階段 4：URI 佔位符解析 (Stage 2B: URI Placeholder & Relative Path Rewriting)**
   - 讀取 Stage 1 快取中繼產物，掃描所有 `__#{uri}__` 路徑標籤。
   - 依據當前 `release_target` 之**三層重映射階層**，動態計算相對於該 Target 目標檔案之**本機實體相對路徑 (`os.path.relpath`)**：
     - **Tier 1 (宣告發布集合 Exports)**：依該 Target 之拓撲映射表精確計算（如 `../templates/P00.md`）。
     - **Tier 2 (專案級語意協議 URIs)**：專案級協議（`project://`, `docs://`, `plans://`）調用 Core 解析並計算相對路徑。
     - **Tier 3 (未知/未決協議)**：安全降級兜底，保持原樣並發出 Warning。
5. **階段 5：文件產出 (Stage 2C: Artifact Materialization & Distribution - 原子發布語意)**
   - **`release` 原子操作 4 步交易語意**：
     - **步驟 1 (過往發布狀態清理)**：檢查 `storage://agents-workflow/release_manifest.json` 是否有過往發布清單。若存在，依紀錄精確清理過往產出檔案與殘留孤立檔案；若不存在則繼續。
     - **步驟 2 (提前解算發布清單)**：對所有已啟用的 `release_targets` 提前完整解算所有檔案之「目標路徑 ➔ 渲染內容」映射。若出錯立即中止，絕不污染專案檔案。
     - **步驟 3 (更新持久清單)**：原子寫入本次最新發布檔案清單至 `storage://agents-workflow/release_manifest.json`。
     - **步驟 4 (建立目錄並落地內容)**：建立目標目錄，原子覆蓋寫入檔案，並依 `enable_agents_md` 執行 `AGENTS.md` 軟合併。
6. **階段 6：結束 (Teardown & Completion)**
   - 統計並輸出全環境發布成果摘要（各 Target 產出檔案數、耗時）。
   - 釋放暫存資源，平穩退出。

---

## 3. CLI 指令體系規範 (CLI Interface Specification)

| 指令語法 | 核心職責說明 | 行為細節與邊界防禦 |
| :--- | :--- | :--- |
| **`python yscb.py agents-workflow release`** | 發布所有已啟用的釋出目標 | 剛性發布 `config.project.json` 中配置的所有 `release_targets`，不支援 `--target` 參數，保證發布一致性。 |
| **`python yscb.py agents-workflow release-target --list`** | 查詢釋出目標清單與啟用狀態 | 列出全系統可用 Targets，標註 `[ENABLED]` / `[DISABLED]`，並對「已配置但未找到注入定義」之 Target 標註 `[ORPHAN / NOT FOUND]`。 |
| **`python yscb.py agents-workflow release-target --add <target>`** | 啟用指定釋出目標 | 將 `<target>` 寫入 `config.project.json` 之 `release_targets`，並**自動觸發 `release`** 執行發布。 |
| **`python yscb.py agents-workflow release-target --remove <target>`** | 停用指定釋出目標 | 自 `release_targets` 移除 `<target>`，並**自動觸發 `release`**（自動精確清理該 Target 舊檔案）。 |
| **`python yscb.py agents-workflow tokens`** | 查詢全系統 Token 清單 | 列出全系統已註冊之插入佔位符清冊與說明。 |
| **`python yscb.py agents-workflow list`** | 查詢全系統 Exports 清冊 | 列出所有模組導出之 Standards, Workflows, Templates 清單。 |

---

## 4. 範疇邊界 (Scope Boundaries)

- **包含**：
  - 新增 `release_target` Contributes 貢獻規範與純文字 `header` 模板。
  - 重構 `config.project.json`：移除 `"ide": []`，引入 `"release_targets": []`，維護 `enable_agents_md` 與 `enable_project_changelog`。
  - 實作 `storage://agents-workflow/release_manifest.json` 持久化與原子 4 步 `release` 清理/落地機制。
  - 實作 CLI：`release`, `release-target --list|--add|--remove`。
  - 重構 `ArtifactCompiler` 實現 6 步標準管線。
  - 將中繼輸出目錄重導向至 `cache.root://agents-workflow/resolved_contents/`，清理原 `exports/`。
  - 更新核心資產中所有的模板與規範引用連結（全面採用 `__#{uri}__`）。
  - 單元與端對端測試覆蓋 CLI 指令、原子發布、多 Target 釋出與路徑轉譯。
- **不包含**：
  - 專案外任意非 YSCB 協議 URL 之外部網路解析。

---

## 5. 決策紀錄 (Decision Records)

- **[SUB07:DR-01]** 刪除原 `module.root://agents-workflow/exports` 目錄，轉為標準微內核快取。
- **[SUB07:DR-02]** 定案標準 6 步語意編譯發布管線：啟動 ➔ 段落佔位符解析 ➔ 釋出環境解析 ➔ URI 佔位符解析 ➔ 文件產出 ➔ 結束。
- **[SUB07:DR-03]** 確立「模組內部資產維持語意 URI 解耦，對齊 Agent/人類執行期物化為本機相對路徑」原則。
- **[SUB07:DR-04]** 確立 URI 佔位符三層重映射階層：Tier 1 (Target Exports 拓撲表) ➔ Tier 2 (Core 專案協議) ➔ Tier 3 (未知安全降級)。
- **[SUB07:DR-05]** 引入 `release_target` 貢獻體系（純文字 header 模板）與多環境輸出支援，`config.project.json` 升級為 `"release_targets": []`。
- **[SUB07:DR-06]** 收斂混合注入為原生特化開關：保留 `enable_agents_md` 與 `enable_project_changelog`，不開放過度設計之通用 Integrations。
- **[SUB07:DR-07]** 定案 CLI 指令體系 (`release`, `release-target --list|--add|--remove`) 與基於 `storage://` 的 4 步原子發布/清理語意。
