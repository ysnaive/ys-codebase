# 語意需求說明書 (Semantic Requirements Discovery)

> 功能名稱：`sub_02_uri_placeholders_and_workflow_path_healing`  
> 建立日期：2026-08-29  
> 所屬主計畫：`workflow_and_agents_guidance_optimization` (Umbrella Level 2)  
> 狀態：Confirmed  
> 計畫類型：Bug Fix / Refactor  
> 模板版本：v1.1  

---

## 1. 使用者原始需求與意圖 (User Intent)

- **原始陳述**：
  1. 在執行 `/ContextInit` 時，Agent 嘗試以 `view_file` 讀取文檔指定路徑失敗，觸發了非預期的 `knowledge-db search` 與路徑探勘。
  2. 經地毯式掃描發現，工作流文檔中供 Agent 在專案根目錄讀取的檔案指引，誤用了以當前文檔位置為基準的 `__#{...}__`（本地相對路徑），物化後生成 `../../AGENTS.md` 或 `../.yscb/standards/...`，在 Agent 工作目錄（專案根目錄）下必然發生 404 FileNotFound。
  3. 發現編譯器 `compiler.py` 在 Stage 2 URI 解算時，無差別對所有代碼塊包回反引號（`f"`{inner}`"`），導致非穿插類型之純佔位符（如 `[Link](`__#{uri}__`)`）解算後錯誤殘留反引號（`[Link](`../path.md`)`），破壞 Markdown 超連結規範與原生點擊跳轉。
  4. 資產中存在少量非標準或舊版協議前綴殘留（如 `plans://`、`archive://`）。
  5. 需於主計畫 `2026_08_29_1505_workflow_and_agents_guidance_optimization` 下開立子計畫，系統性完成編譯器修復、工作流路徑指引校正、協議前綴治癒與自引用物化同步。
- **核心目標**：
  1. **Stage 2 佔位符解析完全替代修復 (Compiler Fix)**：
     - 在 `ArtifactCompiler.resolve_stage2_uri` 中引入「純佔位符 (Standalone/Non-embedded)」與「行內穿插 (Inline/Embedded)」的二分判定。
     - 若代碼塊為純佔位符（`__#{uri}__` 或 `__${uri}__`），解算後完全替代並剝除外層反引號，直接返回純路徑字串。
     - 若為行內穿插代碼（如命令列 `python __${...}__ run`），解算內部佔位符後維持外層反引號。
     - 確保 Markdown 超連結 `[Link](`__#{uri}__`)` 能編譯為合規之標準 Markdown `[Link](../path.md)`。
  2. **工作流讀檔指引佔位符協議校正 (Workflow Path Healing)**：
     - 將所有工作流中供 Agent 於專案根目錄調用 `view_file` 讀取的檔案路徑，由 `__#{...}__` 全面修正為 `__${...}__` (Project Relative URI)。
     - 確保物化至 `.agents/workflows/` 後，路徑均相對於專案根目錄（如 `AGENTS.md`、`.agents/.yscb/standards/AgentsCliGuild.md`、`docs/_project/STANDARDS.md`），使 Agent 能直接無阻礙讀取。
  3. **語意協議前綴全量修復 (Typo URI Healing)**：
     - `DocumentationStandards.md`：`plans://` ➔ `workflow.plans://`
     - `P07_walkthrough.md`：`plans://` ➔ `workflow.plans://`
     - `umbrella_overview.md`：`archive://` ➔ `workflow.archived://`
  4. **回歸驗證與 Dogfooding 同步 (Verification & Sync)**：
     - 全量執行模組單元測試與 `test/run_regression.py` 回歸測試，維持 100% Passed。
     - 重新編譯發布物化至 `.agents/`，實測驗證 `/ContextInit` 讀檔動線 100% 根目錄直達。
- **邊界排除 (Explicitly Excluded)**：
  - 不變更語意 URI 協議的核心解析機制（`core.uri` SDK 保持原樣）。
  - 不變更 `contributes` 的資料規格與 Hook 擴充體系。
  - 不變更各工作流的核心 SOP 步驟與邏輯流程。

---

## 2. 核心討論與決策紀錄 (Discussion & Decisions)

- **[P00:DR-01] Stage 1 與 Stage 2 佔位符反引號處理對齊**：
  對齊 Stage 1 與 Stage 2 的反引號吞噬機制。當 code span 內部字串為單一完整之 `__#{uri}__` 或 `__${uri}__` 時，判定為純路徑字串求值，解算後不包回反引號；若包含其他前綴/後綴字元（如指令文字），則保留反引號。
- **[P00:DR-02] 工作流中 Agent 執行動線剛性使用 `__${...}__`**：
  明確界定 `__#{...}__` 僅用於純文檔內部相對超連結（Markdown 跳轉），所有涉及 Agent / CLI 在終端專案根目錄下執行的檔案讀取與調用指引，一律剛性使用 `__${...}__`。
- **[P00:DR-03] 全生態系資產靜態掃描與無損修復**：
  在 source 空間完成所有資產源碼之佔位符與前綴修復，透過標準 4-Stage Pipeline 構建、驗證並物化同步至消費空間。
- **[P00:DR-04] 確定性文檔讀取失效阻斷鐵律 (Deterministic Document Read Guardrail)**：
  於 `AgentsStandards.md` 注入剛性規範，嚴禁在讀取 SOP/指引明確指定之確定性檔案失敗時，自主發起同義詞或模糊搜尋來掩蓋路徑缺陷，必須立即停步向開發者呈報錯誤。

---

## 3. 開放議題與確認紀錄

- [x] **[確認]** 是否將 `compiler.py` 的 Stage 2 反引號剝除邏輯列入修復範疇？ ➔ 是，已確認為 compiler Stage 2 實作缺漏。
- [x] **[確認]** 工作流中引導 Agent 讀取檔案的動線是否全面切換至 `__${...}__`？ ➔ 是，確保專案根目錄執行零阻礙。
- [ ] **[待確認]** 本階段 P00 語意需求是否確認無誤，可正式定稿 (Confirmed) 並推進至分流評估與後續階段？
