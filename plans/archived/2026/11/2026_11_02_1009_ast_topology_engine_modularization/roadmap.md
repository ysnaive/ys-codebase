# 技術路線圖提案：語法樹與呼叫拓撲引擎獨立模組化 (`module:ast`)

> 主題：語法樹與呼叫拓撲引擎獨立模組化 (`module:ast`)  
> 歸檔日期：2026-11-02  
> 狀態：Proposed  
> 目標範疇：`module:ast` (New), `module:knowledge-db`, `module:file-space`, `module:agents-workflow`  
> 前置解鎖條件：`module:file-space`（通用檔案空間與指紋快取底座）完成抽離定案後啟動  
> 模型：Gemini 4 Argon (Low)  
> 模板版本：v1.2  

---

## 1. 背景與長期願景 (Background & Vision)

- **核心痛點與動機**：
  1. **語意檢索與靜態語法拓撲職責混載**：現行架構將「確定性程式碼語法樹解析、跨分部符號聚合、呼叫圖譜（Call Graph）與影響半徑分析」與「全文本分詞、BM25 及向量嵌入混合檢索」耦合於單一知識庫模組中，導致指令語意不夠直覺且模組職責邊界過寬。
  2. **重型檢索依賴與輕量結構分析綁定**：當開發者或 AI 技能僅需確定性的單檔符號大綱（Outline）或靜態呼叫拓撲（`callers` / `callees` / `impact`）時，被迫連帶承擔全文與向量檢索子系統的依賴與索引成本。
  3. **多語言特化邏輯缺乏標準隔離機制**：主流語言之官方語法樹特徵（如 C# 分部類別跨檔聚合、C++ 存取修飾符狀態繼承、Python 裝飾器提取）若散落於通用解析流程中，易造成通用解析器膨脹；反之，若將每種官方語言拆為頂層獨立發布模組，又會在統一符號模型演進時引發跨多模組鎖步發版（Lockstep Versioning）的維護災難。
- **長期願景與目標定位**：
  建立一套與 `module:file-space`（底層檔案空間與指紋底座）及 `module:knowledge-db`（上層全文與向量混合檢索引擎）嚴格正交的 **`module:ast` 靜態語法樹與呼叫拓撲核心模組**。實現「**`file-space` 管檔案與指紋 -> `ast` 管語法結構與呼叫拓撲 -> `knowledge-db` 管跨空間全文與語意搜尋**」的三階單向無環架構，並提供極簡直覺的 `yscb ast <outline|callers|callees|impact>` 領域介面。

---

## 2. 抽象架構原則與核心設計概念 (Architectural Principles & Concepts)

- **核心設計不變量 (Core Invariants)**：
  1. **三階單向依賴閉環（Strict 3-Tier Unidirectional DAG）**：
     - **Layer 1（`module:file-space`）**：負責空間幾何定義（`include / exclude`）與檔案變更指紋快照。
     - **Layer 2（`module:ast`）**：僅依賴 `core` 與 `file-space`；專責將程式碼檔案解析為結構化符號樹（`UnifiedSymbol`）、執行跨檔同型別聚合與建立雙向呼叫圖譜（`CallGraph`），**100% 不反向依賴 `knowledge-db` 或任何全文/向量檢索組件**。
     - **Layer 3（`module:knowledge-db`）**：依賴 `core`、`file-space` 與 `ast`；不再自行解析程式碼語法樹，而是直接消費 `module:ast` 產出的結構化符號流，結合文檔空間解析結果，專注於建立多欄位 BM25 與向量混合檢索索引。
  2. **「內建官方方言隔離 + 外部非主流語言擴充」雙軌語言治理（Dialect Isolation without Module Explosion）**：
     - 主流語言統一收錄於 `module:ast` 內部的獨立方言處理器（`dialects/<lang>`）中，嚴格遵守「一語言一隔離單元」，通用主幹嚴禁出現特定語言名稱之條件分支；同時保留完整的宣告式 `contributes` 語言註冊協定。
  3. **按需語法依賴自舉（On-Demand Grammar Provisioning）**：
     - `module:ast` 基底僅宣告核心解析器框架依賴；各語言對應之底層 Grammar 套件依專案空間實際掃描到的檔案副檔名動態按需安裝與載入。
  4. **零重複解析與單一符號快取共享（Single-Parse Symbol Sharing）**：
     - 同一份程式碼在單次變更週期內僅由 `module:ast` 解析一次並持久化為符號與圖譜快照；`module:knowledge-db` 建立搜尋索引時直接讀取該符號快照。
- **下游實戰專案 (`uitk.net`) 4 項關鍵工程邊界補強**：
  1. **同名異載（Method Overloads）與泛型簽名的確定性定址語法**：匹配到同一型別下的多個重載時預設視為同一群組一併列出（標註各自重載簽名與檔案行號）；唯有跨不同型別才退回歧義清單提示，並支援帶參數型別之精確過濾。
  2. **`yscb ast outline` 針對 `partial class` 的「跨分部姊妹檔提示」**：檢測到型別具邏輯聚合分部群組時，自動附帶 `[Partial Siblings]` 提示列出其餘分部檔案。
  3. **按需語法依賴自舉的「執行期純淨度與離線圍欄」**：安裝輸出強制導向 `stderr` 或日誌檔以保證 `--json` 100% 純淨；無網路且缺少特定 Grammar 時發出結構化 Warning 並優雅略過該語言 AST 解析。
  4. **跨模組快取失效與 JIT 連鎖同步協議 (`file-space` -> `ast` -> `knowledge-db`)**：Pull-Based JIT 水位線協議，維持「0 手動 index、隨改隨查」的熱自癒體驗。

---

## 3. 解鎖條件與演進構想 (Unlock Criteria & Evolution Stages)

- **Stage 1：方言介面純化與確定性符號定位解耦**（收斂 `DialectAdapter`，切斷拓撲查詢對 `BM25Engine` 的反向依賴）。
- **Stage 2：建立 `module:ast` 並完成 `callers / callees / impact / outline` 遷移**。
- **Stage 3：`module:knowledge-db` 轉型為純粹的上層混合檢索消費者**。
- **Stage 4：AI 工作流技能全面對接 `yscb ast`**。

