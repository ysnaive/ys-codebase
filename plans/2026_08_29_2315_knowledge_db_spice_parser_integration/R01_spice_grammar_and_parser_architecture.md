# 專題調研報告 (Research Report)

> 功能名稱：knowledge-db 模組 SPICE 網表語系解譯器 (SpiceParser) 整合  
> 調研主題：SPICE 全語法規格與高精度解譯器架構設計 (R01_spice_grammar_and_parser_architecture)  
> 建立日期：2026-08-29  
> 所屬主計畫：無  
> 狀態：Completed  
> 模板版本：v1.0  

---

## 1. 背景痛點與調研目標

SPICE (Simulation Program with Integrated Circuit Description) 網表廣泛應用於積體電路設計、模擬與版圖驗證。在 EDA 專案中，網表包含複雜的階層式子電路 (`.subckt`)、元件模型 (`.model`)、參數 (`.param`) 與龐大的元件拓撲。
本次調研目標為設計生產級、高容錯且高效能的 `SpiceParser`，直接整合入 `knowledge-db`，達成全語法與多方言相容。

---

## 2. 候選方案評估矩陣 (Candidate Options Matrix)

| 方案 | 架構描述 | 優點 | 缺點 / 代價 | 結論 |
| :--- | :--- | :--- | :--- | :---: |
| **方案 A：外部庫包裝 (PySPICE / spicelib)** | 引入第三方 Python SPICE 解析套件 | 既有成熟實作 | 增加外部重度依賴、不相容 UnifiedSymbol、跨平台安裝成本高 | ❌ 否決 |
| **方案 B：純正則正向遍歷 (Regex Scanner)** | 針對每行進行簡單正則比對 | 實作簡單快速 | 無法處理跨行接續 (`+`)、嵌套作用域、行號漂移與方言容錯 | ❌ 否決 |
| **方案 C（推薦）：雙階段階層狀態機 (Two-Stage State Machine)** | Stage 1 邏輯行聚合器 + Stage 2 作用域狀態機 | 100% 零外部依賴、精確行號追蹤、支援所有方言註解、深度提取階層成員 | 需撰寫完整預處理與狀態機單元測試 | ✅ **採納** |

---

## 3. SPICE 語法標準與方言相容矩陣

1. **換行接續符號**：行首第一個非空白字元為 `+`，代表與上一行指令合併。Stage 1 聚合為邏輯行並記錄 `line_number` (起始行) 與 `end_line` (結束行)。
2. **註解體系**：
   - 行首 `*`：整行註解，若緊鄰宣告上方則萃取為 Docstring。
   - 行內 `;` (ngspice/LTspice) 或 `$` (HSPICE)：截斷行尾註解。
3. **大小寫不敏感**：全語法關鍵字與名稱在狀態機比對時採 case-insensitive，保留原始大小寫輸出。
4. **階層作用域**：
   - 頂層作用域 (Global Scope)：`.param`, `.model`, `.include`, `.lib`, `.global`, 頂層 `X...` 實例。
   - 子電路作用域 (Subcircuit Scope)：`.subckt <name> <pins...> [params...]` ➔ 內部包含子元件 `X...`, `M...`, `Q...`, `R...` 等，聚合至 `members: List[MemberInfo]`，遇 `.ends` 閉合。

---

## 4. 關鍵架構結論與出口轉化

- **出口分流**：直接回填至 Phase 0，即刻升級為 **Level 1 (Full Track)** 實作計畫。
- **落腳點**：`source/knowledge-db/knowledge_db/parsers/spice_parser.py`。
