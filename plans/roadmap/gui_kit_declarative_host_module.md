# 技術路線圖：宣告式領域無關視覺化宿主模組與雙軌 UI 擴充架構 (Roadmap)

> 主題：宣告式領域無關視覺化宿主模組與雙軌 UI 擴充架構 (`gui_kit_declarative_host_module`)  
> 歸檔日期：2026-10-30  
> 狀態：Backlog  
> 目標範疇：`module:gui-kit`（獨立擴充模組）、全生態系模組 `contributes` 視覺化擴充協議  
> 前置解鎖條件：核心模組結構化輸出契約（`--json`）標準化就緒，且進入人機雙棲視覺化協作擴充階段時啟動  
> 模型：Unknown  
> 模板版本：v1.1  

---

## 1. 背景與長期願景 (Background & Vision)

- **核心痛點與動機**：
  - 結構化 CLI 工具鏈與低延遲 IPC 派發對 AI Agent 極為友善，但人類開發者在面對高資訊密度場景（如多階調用拓撲圖譜與影響半徑對照、多層組態覆蓋矩陣、多計畫生命週期看板與背景常駐服務日誌流）時，純文字終端機存在天然的空間佈局與視覺下鑽（Drill-down）瓶頸。
- **長期願景與目標定位**：
  - 打造一套純粹作為「視覺化宿主容器與宣告式 UI 渲染引擎」的獨立擴充模組 `module:gui-kit`，將純 CLI 工具鏈延伸為「人機雙棲協作中樞」，讓任何官方或第三方模組僅需透過宣告式組態或數行無狀態 Python 函數，即可無縫長出直覺化的圖形操作介面。
- **範疇與邊界約束**：
  - **拒絕任何特化邏輯（Zero Special-Casing）**：`gui-kit` 本身不包含任何針對特定模組的硬編碼視圖或條件分支；所有模組地位完全平等，一律透過標準擴充點註冊。
  - **零前端工具鏈負擔**：模組開發者無需觸碰任何 HTML/CSS/JS 或維護前端打包管線。

---

## 2. 抽象架構原則與核心設計概念 (Architectural Principles & Concepts)

- **核心設計不變量 (Core Invariants)**：
  1. **絕對領域無關與依賴反轉（Strict Domain-Blindness & IoC）**：`gui-kit` 僅識別抽象「插槽（Slots）」、「資料契約（Data Schemas）」與「通用原子元件（UI Primitives）」，由各模組透過 `contributes` 協議自主注入導覽與視圖，並原生對接多語系字典解析與靜態 Schema 校驗。
  2. **雙軌漸進式擴充協議（Two-Tier Declarative Extensibility）**：
     - **Tier 1（零代碼純宣告）**：直接於 `contributes` JSON 中將結構化 CLI 指令（`cli://...`）綁定為資料表格、表單或單行觸發動作，並**自動繼承目標 CLI 指令之安全權限分級**（對受保護之 `[GATED]` 破壞性指令強制開啟二次確認對話框守門）。
     - **Tier 2（極簡純函數 Python 視圖）**：針對複雜多元件聯動場景，由模組提供無狀態 Python 渲染函式（`render(ctx) -> ViewTree`），透過顯式狀態容器 `ctx.state` 接收前端互動事件並觸發純函數重新求值，回傳宣告式視圖樹。
  3. **6 大標準通用原子元件庫（Domain-Blind UI Primitives）**：
     - **結構化表單與動作列 (`form` / `action_bar`)**：映射參數輸入、枚舉、語意 URI 路徑選擇器與命令觸發。
     - **資料表格與雙層矩陣 (`data_table` / `kv_matrix`)**：呈現結構化清單、多層組態覆蓋對照與單行動作回呼。
     - **拓撲網路圖與階層樹 (`network_graph` / `tree`)**：渲染 `{nodes, edges}` 互動調用圖譜與母子計畫階層樹。
     - **代碼切片與差異檢視器 (`code_viewer` / `diff_viewer`)**：支援語法高亮、行號區間預覽與外部 IDE 行號一鍵跳轉。
     - **富文本與圖表文件框 (`markdown_viewer`)**：渲染隨包手冊、計畫規格書與內嵌 Mermaid 圖表。
     - **即時串流終端與指標卡 (`log_stream` / `stat_cards`)**：呈現持續附加之輸出流與常駐運行指標。
- **概念機制與互動協議 (Conceptual Mechanism)**：
  - **雙軌動作派發橋接（Dual-Track Execution Bridge）**：針對支援常駐熱派發之輕量查詢指令，走毫秒級 Hot-IPC 通道取得 JSON 渲染；針對耗時或涉及環境異動之指令，則以非同步串流子進程執行並將即時輸出推播至 `log_stream` 元件。
  - **同源渲染與雙模視窗宿主（Unified Render Core & Multi-Host Shell）**：底層統一採用輕量本地 Web 渲染核，外層容器預設提供**「獨立原生桌面視窗模式」**（OS WebView + Native Bridge 支援系統原生檔案選擇器與外部 IDE 喚起），並於無頭（Headless）、遠端 SSH 或容器環境自動無縫降級為**「IDE 內嵌 / 純瀏覽器端點模式」**。

---

## 3. 解鎖條件與演進構想 (Unlock Criteria & Evolution Stages)

- **前置解鎖條件與觸發時機**：
  - 核心生態系模組之 CLI 結構化輸出契約（`--json`）標準化覆蓋完畢，且團隊進入人機視覺化協作介面擴充階段時啟動。
- **階段演進構想 (High-Level Stages)**：
  1. **Stage 1（擴充點 Schema 與雙模宿主基座）**：建立 `gui-kit` 之 `contributes` Schema 契約、雙軌動作派發橋接器（Hot-IPC + 非同步串流子進程）與雙模視窗容器（Desktop WebView / Headless Web）。
  2. **Stage 2（6 大通用原子元件與 Tier 1/Tier 2 渲染引擎）**：實作 6 大領域無關 UI Primitives、CLI 安全等級自動確認映射，以及 Tier 2 Python `render(ctx)` 狀態重繪閉環。
  3. **Stage 3（隨插即用熱擴充與開發套件整合）**：結合模組目錄熱監聽實現安裝新模組後導覽列即時浮現，並於模組骨架生成器提供最小化 `gui` 擴充範本。
