# 技術路線圖：工作流宣告式階段拓撲引擎與可插拔領域擴充架構 (Roadmap)

> 主題：工作流宣告式階段拓撲引擎與可插拔領域擴充架構 (`declarative_track_schema_and_domain_packs`)  
> 歸檔日期：2026-11-05  
> 狀態：Proposed  
> 目標範疇：`agents-workflow`（階段拓撲狀態機、結構檢核引擎與 `contributes` 領域擴充契約）  
> 前置解鎖條件：[Tier 3 - 排序 #6] 承接 #5 (ast_compile_pipeline_and_kdb_doc_governance Stage 1~2) 完成編譯器下沉後，與其 Stage 3 協同推進工作流骨幹純化與 agents-workflow-coding 領域包抽離  
> 模型：Gemini 4 Argon (Low)  
> 模板版本：v1.1  

---

## 1. 背景與長期願景 (Background & Vision)

- **核心痛點與動機**：
  - **階段拓撲與檢核邏輯存在硬編碼條件分支**：現行工作流引擎雖支援多種計畫模式（`full`, `fast`, `umbrella`, `revision`, `research`, `roadmap`），但其階段轉換順序、檔名匹配規則與檢核條件仍以條件分支內建於核心引擎中。
  - **跨領域擴充缺乏可插拔接口**：當未來面對非純軟開發場景（如系統企劃與數值設計 `design`、遊戲引擎資產管線 `unity`、機構與電子工程 `cad` / `spice`）時，外部領域模組無法宣告自訂的階段拓撲（Phase DAG）、專屬模板與領域驗收鉤子（Gate Validators）。
- **長期願景與目標定位**：
  - 將 `module:agents-workflow` 純化為乾淨的工作流骨幹框架與通用 CLI 工具，透過表驅動 `TrackSpec` 與 `contributes` 擴充契約，將領域專屬之 `plan` 軌道、階段模板、檢核器與技能改由外部領域包注入（例如現有純程式碼性質之研發流程聚合下沉至 `agents-workflow-coding`，未來可平行擴充 `agents-workflow-unity`、`agents-workflow-pixel-art` 等專業領域包），並與 `ast_compile_pipeline_and_kdb_doc_governance` 之統一編譯管線協同運作。
- **範疇與邊界約束**：
  - 涵蓋工作流骨幹 `TrackSpec` 表驅動重構、`agents-workflow-coding` 等外部領域包 `contributes` 注入契約、階段感知提示詞路由（Phase-Scoped Routing）、跨領域子計畫混合編排（Cross-Track Umbrella），以及防範 JSON DSL 複雜度膨脹之邊界規範。

---

## 2. 抽象架構原則與核心設計概念 (Architectural Principles & Concepts)

- **核心設計不變量 (Core Invariants)**：
  - **骨幹純化與領域包正交注入（Pure Backbone & Contributed Domain Packs）**：`agents-workflow` 本體僅保留跨領域通用的計畫生命周期狀態機、CLI 調度器與基礎容器契約；具體領域之研發軌道（如軟體開發 `agents-workflow-coding`、遊戲引擎 `agents-workflow-unity`、美術資產 `agents-workflow-pixel-art`）一律以標準 `contributes` 插件形式注入。
  - **拒絕 JSON DSL 圖靈化（Python `TypedDict` / `dataclass` + 扁平 JSON 資源映射）**：嚴禁將複雜的狀態轉移條件分支、動態邏輯或巢狀運算塞入靜態 `contributes/*.json`（避免違反 Greenspun 第十定律而喪失 IDE 型別安全與重構能力）。內部狀態機與複雜領域驗收邏輯一律以 Python 原生型別結構（`TrackSpec` `dataclass` / `TypedDict`）與可調用 Hook 函式實作；外部 `contributes` JSON 僅負責扁平的靜態資源路徑（模板 URI、必填章節清單、驗證器入口符號 `code.symbol://`）註冊。
  - **階段感知按需路由（Zero Idle Token Overhead）**：僅在 `plan status --resume` 進入特定 Track 與階段時動態輸出該階段專屬指引，平時不佔用常駐 Prompt Token。
- **概念機制與互動協議 (Conceptual Mechanism)**：
  - **雙層檢核分離**：將驗證管線拆分為「通用結構檢核層（Core Structural Verifier，負責標頭、必填章節與追溯鏈）」與「可插拔領域驗證鉤子（Contributed Gate Validators，透過 `code.symbol://` 掛載 Python 檢核函式）」。
  - **Cross-Track Umbrella 混合編排**：允許同一 `Umbrella` 主計畫下的不同 `sub_XX` 子計畫各自宣告並運行不同領域的 `TrackSpec`（例如 `sub_01` 走企劃或美術 Track、`sub_02` 走軟體開發 `coding` Track）。

---

## 3. 解鎖條件與演進構想 (Unlock Criteria & Evolution Stages)

- **前置解鎖條件與觸發時機**：
  - 與 `ast_compile_pipeline_and_kdb_doc_governance` 協同演進；於底層核心與知識庫基礎問題處理完畢後啟動。
- **階段演進構想 (High-Level Stages)**：
  1. **Stage 1（Python `TrackSpec` 表驅動狀態機與 `contributes` 領域擴充契約）**：以 Python 型別化 `TrackSpec` 重構內部狀態解析與結構驗證器，開放扁平 `contributes` 擴充點（註冊靜態模板、階段拓撲與 Python Validator 符號）。
  2. **Stage 2（`agents-workflow-coding` 領域聚合下沉與 Cross-Track Umbrella）**：將純軟開發專屬之 `P01~P07` 計畫規範與檢核邏輯抽離為標準領域注入包，實作按需階段提示詞輸出與跨 Track 子計畫狀態聚合，通過既有全量單元測試驗證零退化。
  3. **Stage 3（非純軟領域擴充包實戰孵化）**：結合下游場景孵化 `agents-workflow-unity`、`agents-workflow-pixel-art` 等領域擴充包。
