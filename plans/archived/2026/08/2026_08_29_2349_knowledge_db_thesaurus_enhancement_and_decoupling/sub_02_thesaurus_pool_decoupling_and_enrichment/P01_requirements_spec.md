# 需求規格說明書 (Requirements Specification)

> 功能名稱：sub_02_thesaurus_pool_decoupling_and_enrichment  
> 建立日期：2026-08-29  
> 所屬主計畫：2026_08_29_2349_knowledge_db_thesaurus_enhancement_and_decoupling  
> 狀態：Confirmed  
> 依據 P00：[P00_discuss.md](./P00_discuss.md)  
> 模板版本：v1.5  

---

## 1. 功能需求清單 (Functional Requirements)

| 需求編號 | 需求名稱 | 詳細規格描述 | 優先級 | 對應 P00 語意 |
| :--- | :--- | :--- | :---: | :--- |
| **FR-01** | `ThesaurusEngine` 源碼硬編碼詞表徹底解耦 | 徹底移除 `thesaurus.py` 內部之 `BUILTIN_THESAURUS` 靜態常數。`ThesaurusEngine` 初始化時為純淨無狀態容器，支援接收 `ThesaurusConfig` 或三個自訂集合 (`custom_groups`, `custom_aliases`, `custom_related`)，無傳參時預設為純淨空容器。 | P0 | [P00:DR-01] |
| **FR-02** | `core.contribute` 標準管道詞庫聚合與工廠方法 | 依循 `core.contribute` 標準跨模組聚合協議（由 `core.contributes` 提供或 `SpaceManager` 統一載入），實作 `SpaceManager.create_thesaurus_engine(extra_config=None)` 工廠方法，動態收集全系統已註冊之同義詞、別名與關聯詞並裝配 `ThesaurusEngine`。 | P0 | [P00:DR-01] |
| **FR-03** | 六大維度初始宣告式詞彙庫豐富化 (`contributes/knowledge-db.json`) | 於 `source/knowledge-db/contributes/knowledge-db.json` 建立高品質宣告式詞庫，完整涵蓋以下 6 大維度：<br/>1. **常用日用語/軟工動名詞** (20+ 組雙向同義詞，涵蓋 CRUD、查詢、讀取、儲存、更新、刪除、配置、狀態、控制、引擎、錯誤、測試、格式、轉換、路由、解析、標籤、路徑、符號、類別、函式、導引手冊等)。<br/>2. **C / C++ 術語** (指標/指針、引用/參照、模板/範本、巨集/宏、標頭檔、建構/解構子、多型/虛擬、命名空間、動態記憶體配置，以及 `cpp => c, cxx, hpp`, `raii`, `stl`, `smart_ptr` 等別名)。<br/>3. **C# 術語 (CSharp)** (屬性/特性、委派/委託、非同步/異步、反射、列舉器、擴充方法、依賴注入，以及 `csharp => cs, dotnet, clr`, `linq` 等別名)。<br/>4. **Python 術語** (裝飾器、生成器、型別標註、魔術方法、虛擬環境、推導式、模組/套件，以及 `python => py, pyd, pyi`, `pydantic`, `dataclass` 等別名)。<br/>5. **SPICE 術語** (網表、子電路、模型/參數、節點/接腳、暫態分析、交流分析、直流分析，以及 `ngspice/hspice => spice, circuit, netlist`, `mosfet` 等別名)。<br/>6. **資電類學系術語 (EE / CS / VLSI / Embedded / Controls)** (邏輯閘/正反器、時脈、匯流排/總線、頻寬、中斷/ISR、類比/ADC/DAC、數位訊號處理/DSP/FFT、靜態時序/STA、嵌入式/MCU、狀態機/FSM，以及 `fpga => hdl, verilog, vhdl, rtl`, `vlsi => ic, layout, gds`, `riscv` 等別名)。 | P0 | [P00:DR-02] |
| **FR-04** | 檢索引擎預設組態連動 | `BM25Engine` 或 `KnowledgeEngine` 初始化時若未顯式傳入 `thesaurus`，自動透過 `SpaceManager.create_thesaurus_engine()` 動態加載已聚合之詞庫，確保 CLI 與 SDK 開箱即用。 | P0 | [P00:DR-01] |

---

## 2. 邊界與異常情況 (Edge Cases & Failure Modes)

| 邊界編號 | 情境說明 | 預期防禦與處理行為 |
| :--- | :--- | :--- |
| **EC-01** | Contributes 無同義詞宣告時之預設安全防禦 | 當環境完全無任何 contributes 宣告（或為純空物件）時，`create_thesaurus_engine()` 安全返回純淨的 `ThesaurusEngine`，不引發異常，查詢時僅依原始詞進行檢索。 |
| **EC-02** | 模組間同義詞群組重複宣告 (Duplicate Signatures) | `SpaceManager` 載入多模組 contributes 時，自動進行簽名正規化去重，防止相同詞組重複註冊。 |
| **EC-03** | 舊測試案例與代碼向後相容 | 既有呼叫 `ThesaurusEngine()` 之單元測試若未傳入詞庫，行為依預設空容器運作，不拋出錯誤。 |

---

## 3. 非功能需求 (Non-Functional Requirements)

| 需求編號 | 類別 | 指標與量化約束 |
| :--- | :--- | :--- |
| **NFR-01** | 程式碼純淨度與解耦性 | 原始碼 `thesaurus.py` 零業務詞表硬編碼，所有詞彙 100% 透過 JSON 宣告式資產管理。 |
| **NFR-02** | 載入效能 | 詞庫 JSON 載入與聚合耗時 $< 2\text{ ms}$，記憶體常駐開銷 $< 100\text{ KB}$。 |

---

## 4. 知識庫與踩坑紀錄查閱 (Known Gotchas & CAUTIONs)

- **`[!NOTE]`** 
  - `knowledge-db` 在微核心體系中同時扮演 Target 模組與 Donor 模組，自身宣告之 `source/knowledge-db/contributes/knowledge-db.json` 會在 `core.contributes` 掃描時自動被納入聚合。
