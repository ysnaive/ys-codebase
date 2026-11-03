# 技術路線圖：工作流宣告式階段拓撲引擎與可插拔領域擴充架構 (Roadmap)

> 主題：工作流宣告式階段拓撲引擎與可插拔領域擴充架構 (`declarative_track_schema_and_domain_packs`)  
> 歸檔日期：2026-11-03  
> 狀態：Proposed  
> 目標範疇：`agents-workflow`（階段拓撲狀態機、結構檢核引擎與 `contributes` 領域擴充契約）  
> 前置解鎖條件：實際出現非純軟開發領域專案（如企劃設計、遊戲引擎資產、硬體工程）之工作流擴充需求時啟動  
> 模型：Gemini 4 Argon (Low)  
> 模板版本：v1.1  

---

## 1. 背景與長期願景 (Background & Vision)

- **核心痛點與動機**：
  - **階段拓撲與檢核邏輯存在硬編碼條件分支**：現行工作流引擎雖支援多種計畫模式（`full`, `fast`, `umbrella`, `revision`, `research`, `roadmap`），但其階段轉換順序、檔名匹配規則與檢核條件仍以條件分支內建於核心引擎中。
  - **跨領域擴充缺乏可插拔接口**：當未來面對非純軟開發場景（如系統企劃與數值設計 `design`、遊戲引擎資產管線 `unity`、機構與電子工程 `cad` / `spice`）時，外部領域模組無法宣告自訂的階段拓撲（Phase DAG）、專屬模板與領域驗收鉤子（Gate Validators）。
- **長期願景與目標定位**：
  - 在維持軟體開發預設 Track 內建開箱即用（不物理拆包造成雙模組維護摩擦）的前提下，將工作流引擎抽象為表驅動 `TrackSpec` 架構，並開放外部領域模組按需掛載專屬 Track 與驗收器。
- **範疇與邊界約束**：
  - 涵蓋工作流內部 `TrackSpec` 表驅動重構、階段感知提示詞路由（Phase-Scoped Routing）、跨領域子計畫混合編排（Cross-Track Umbrella），以及防範 JSON DSL 複雜度膨脹之邊界規範。

---

## 2. 抽象架構原則與核心設計概念 (Architectural Principles & Concepts)

- **核心設計不變量 (Core Invariants)**：
  - **內部表驅動先行、預設 Track 內建不拆包**：現有軟體開發模式作為內建預設 `TrackSpec`，杜絕拆分為獨立模組所帶來的雙向版本同步與打包摩擦（Split-Brain Friction）。
  - **拒絕 JSON DSL 圖靈化（Python `TypedDict` / `dataclass` + 扁平 JSON 資源映射）**：嚴禁將複雜的狀態轉移條件分支、動態邏輯或巢狀運算塞入靜態 `contributes/*.json`（避免違反 Greenspun 第十定律而喪失 IDE 型別安全與重構能力）。內部狀態機與複雜領域驗收邏輯一律以 Python 原生型別結構（`TrackSpec` `dataclass` / `TypedDict`）與可調用 Hook 函式實作；外部 `contributes` JSON 僅負責扁平的靜態資源路徑（模板 URI、必填章節清單、驗證器入口符號 `code.symbol://`）註冊。
  - **階段感知按需路由（Zero Idle Token Overhead）**：僅在 `plan status --resume` 進入特定 Track 與階段時動態輸出該階段專屬指引，平時不佔用常駐 Prompt Token。
- **概念機制與互動協議 (Conceptual Mechanism)**：
  - **雙層檢核分離**：將驗證管線拆分為「通用結構檢核層（Core Structural Verifier，負責標頭、必填章節與追溯鏈）」與「可插拔領域驗證鉤子（Contributed Gate Validators，透過 `code.symbol://` 掛載 Python 檢核函式）」。
  - **Cross-Track Umbrella 混合編排**：允許同一 `Umbrella` 主計畫下的不同 `sub_XX` 子計畫各自宣告並運行不同領域的 `TrackSpec`（例如 `sub_01` 走企劃 Track、`sub_02` 走軟體開發 Track）。

---

## 3. 解鎖條件與演進構想 (Unlock Criteria & Evolution Stages)

- **前置解鎖條件與觸發時機**：
  - 無外部阻塞依賴；於實際有非純軟領域專案需求時孵化外部領域擴充包。
- **階段演進構想 (High-Level Stages)**：
  1. **Stage 1（Python `TrackSpec` 表驅動狀態機與驗證器重構）**：以 Python 型別化 `TrackSpec` 重構內部狀態解析與結構驗證器，並開放扁平 `contributes` 擴充點（註冊靜態模板與 Python Validator 符號）。
  2. **Stage 2（階段感知路由與 Cross-Track Umbrella）**：實作按需階段提示詞輸出與跨 Track 子計畫狀態聚合，通過既有全量單元測試驗證零退化。
  3. **Stage 3（首個非 Coding 領域擴充包實戰孵化）**：結合真實下游非純軟場景，以標準插件形式掛載領域專屬 Track。
