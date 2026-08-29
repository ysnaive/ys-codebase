# 需求討論說明書 (Semantic Requirements Discovery)

> 功能名稱：knowledge-db 模組 SPICE 網表語系解譯器 (SpiceParser) 整合  
> 建立日期：2026-08-29  
> 所屬主計畫：無  
> 狀態：Confirmed  
> 計畫類型：Feature  
> 模板版本：v1.2  

---

## 1. 使用者原始需求與意圖 (User Intent)

- **原始陳述**：我想幫 agents-workflow 添加 spice (.cir .sp) 語系解譯器；調研 spice 語法，目標與本次開發直接完成完整解譯器。
- **核心目標**：在生態系中建立工業級完整功能的 SPICE 語意解譯器，完整解析 `.cir`, `.sp`, `.spice`, `.net`, `.cdl` 網表檔案，提取子電路 (`.subckt`)、元件模型 (`.model`)、參數 (`.param`)、包含指令 (`.include`/`.lib`) 與元件實例 (`X...`, `M...`) 至 UnifiedSymbol 體系，使 `knowledge-db search` 能秒級精準檢索電路網表。
- **邊界排除 (Explicitly Excluded)**：
  - 不包含電路數值模擬矩陣求解器（如 SPICE AC/DC/TRAN 瞬態數值運算）。
  - 不更動 `agents-workflow` 或 `core` 模組的 Public API。

---

## 2. 核心討論與決策紀錄 (Discussion & Decisions)

- **[P00:DR-01] 模組架構歸屬決策**：程式碼語法解析與 AST 符號提取統一由 `knowledge-db`（`source/knowledge-db/knowledge_db/parsers/`）承接，於該模組新增 `SpiceParser(BaseParser)` 並註冊至 `ParserRegistry`。
- **[P00:DR-02] 支援副檔名矩陣決策**：完整涵蓋五大 SPICE/EDA 網表副檔名：`.cir`, `.sp`, `.spice`, `.net`, `.cdl`。
- **[P00:DR-03] Schema 擴充決策**：於 `schema.py` 之 `LanguageType` 新增 `SPICE = "spice"`。
- **[P00:DR-04] 語法預處理狀態機決策**：Stage 1 邏輯行聚合器精準處理行首 `+` 接續，同時保留原始代碼行號區間 (`line_number` ~ `end_line`)；相容 SPICE 行首 `*` 與行尾 `;` / `$` 註解，並支援前置連續註解萃取為 Docstring。
- **[P00:DR-05] 階層式符號映射決策**：
  - `.subckt ... .ends` ➔ `SymbolKind.CLASS`，內部子元件與局部參數聚合為 `members: List[MemberInfo]`。
  - `.model` ➔ `SymbolKind.STRUCT`。
  - `.param` ➔ `SymbolKind.VARIABLE` / `CONSTANT`。
  - `.include` / `.lib` / `.global` ➔ `SymbolKind.MACRO`。
  - 頂層子電路實例 `X...` ➔ `SymbolKind.FUNCTION` / `VARIABLE`。
- **[P00:DR-06] 計畫分流分級決策**：本任務涉及核心 Parser 新增、Schema 擴充與多方言相容驗證，確立以 **Level 1 (Full Track)** 完整推進。

---

## 3. 開放議題與確認紀錄

- [x] 確認目標模組歸屬為 `knowledge-db`。
- [x] 確認完成 R01 語法調研並建立工業級解譯器設計。
- [x] 確認計畫分流為 Level 1 (Full Track)。
