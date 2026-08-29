# 需求規格說明書 (Requirements Specification)

> 功能名稱：knowledge-db 模組 SPICE 網表語系解譯器 (SpiceParser) 整合  
> 建立日期：2026-08-29  
> 所屬主計畫：無  
> 狀態：Confirmed  
> 依據 P00：[P00_discuss.md](./P00_discuss.md)  
> 模板版本：v1.5  

---

## 1. 功能需求清單 (Functional Requirements)

| 需求編號 | 需求名稱 | 詳細規格描述 | 優先級 | 對應 P00 語意 |
| :--- | :--- | :--- | :---: | :--- |
| **FR-01** | SPICE 副檔名識別與 Schema 擴充 | 於 [`schema.py`](file:///H:/UseFolder/CodeRepo/ys_codebase/ys_codebase/source/knowledge-db/knowledge_db/schema.py#L35-L43) 之 `LanguageType` 新增 `SPICE = "spice"`；`SpiceParser.can_parse()` 支援 `.cir`, `.sp`, `.spice`, `.net`, `.cdl`（大小寫不敏感）。 | P0 | [P00:DR-02]<br/>[P00:DR-03] |
| **FR-02** | Stage 1 語法預處理與行聚合狀態機 | 處理行首 `+` 多行接續邏輯行重構，同時精確追蹤原始起始與結束行號 (`line_number` ~ `end_line`)；相容行首 `*`、行尾 `;` 與 `$` 註解剝離；支援緊鄰宣告上方之連續 `*` 註解萃取為符號 `docstring`。 | P0 | [P00:DR-04] |
| **FR-03** | Stage 2 核心點指令語意符號提取 | 1. 子電路 `.subckt <name> <pins...> [params...] ... .ends` 提取為 `SymbolKind.CLASS`，內部子元件/模型/參數聚合為 `members`。<br/>2. 元件模型 `.model <name> <type> (...)` 提取為 `SymbolKind.STRUCT`。<br/>3. 參數 `.param <name>=<val>` 提取為 `SymbolKind.VARIABLE` / `CONSTANT`。<br/>4. 指令 `.include`, `.lib`, `.global` 提取為 `SymbolKind.MACRO`。 | P0 | [P00:DR-05] |
| **FR-04** | 網表元件實例提取與層級映射 | 1. 頂層子電路實例 `X...` 提取為 `SymbolKind.FUNCTION` / `VARIABLE`。<br/>2. 子電路內部之電晶體 (`M...`, `Q...`)、二極體 (`D...`)、被動元件 (`R...`, `C...`, `L...`) 與實例 (`X...`) 作為 `MemberInfo` 結構化嵌入對應 subckt 之 `members` 清單。 | P0 | [P00:DR-05] |
| **FR-05** | ParserRegistry 動態調度與檢索整合 | 於 [`registry.py`](file:///H:/UseFolder/CodeRepo/ys_codebase/ys_codebase/source/knowledge-db/knowledge_db/parsers/registry.py#L23-L29) 註冊 `SpiceParser` (優先級 100)；`knowledge-db search` CLI 支援 SPICE 檔案之符號檢索與 `-s` 程式碼切片即時預覽。 | P0 | [P00:DR-01] |

---

## 2. 邊界與異常情況 (Edge Cases & Failure Modes)

| 邊界編號 | 情境說明 | 預期防禦與處理行為 |
| :--- | :--- | :--- |
| **EC-01** | 跨多行 `+` 接續夾雜空行與行尾註解 | 連續多行 `+` 接續中若夾雜空行或行尾 `;` / `$` 註解，聚合器需正確剝離註解並合併參數運算式，`end_line` 正確映射為末端接續行。 |
| **EC-02** | 未閉合 Subcircuit 異常網表 | 網表若出現 `.subckt` 但未找到 `.ends`（如檔案非正常截斷或直接遇到 `.end`），狀態機自動封裝當前 subckt 至檔案末端，不拋出未捕獲例外。 |
| **EC-03** | 混合式多方言註解與大小寫混雜 | 同一檔案同時存在 `*` (行首)、`;` (ngspice 行尾)、`$` (HSPICE 行尾) 與大小寫混雜關鍵字（`.SubCkt`, `.MODEL`, `params:`）時，狀態機能穩健正規化識別。 |
| **EC-04** | 空檔案、純註解或無符號網表 | 檔案為空、僅有首行標題或純註解時，回傳空清單 `[]`，不產生任何例外。 |

---

## 3. 非功能需求 (Non-Functional Requirements)

| 需求編號 | 類別 | 指標與量化約束 |
| :--- | :--- | :--- |
| **NFR-01** | 零外部依賴與解析效能 | 100% 採用純 Python 標準庫實作，零引入第三方外部依賴；單檔 10,000 行 SPICE 網表解析時間低於 200ms。 |
| **NFR-02** | 測試覆蓋與品質守門 | `SpiceParser` 單元測試套件涵蓋所有 FR 與 EC 案例（100% Passed）；全生態系回歸測試 (`dev test --all`) 100% 通過。 |

---

## 4. 知識庫與踩坑紀錄查閱 (Known Gotchas & CAUTIONs)

- **`[!NOTE]` 首行標題行 (Title Line) 容錯**：傳統 SPICE 網表第 1 行若為純文字電路描述（非 `.`、非 `*`、非標準元件字母前綴），解析器應視為標題/註解忽略，避免誤判為異常語法。
- **`[!CAUTION]` 大小寫不敏感與符號名稱保留**：狀態機比對指令關鍵字時一律採用大寫/小寫正規化比對，但存入 `UnifiedSymbol.name` 與 `UnifiedSymbol.signature` 時保留原始大小寫，確保代碼檢索切片保真。
- **`[!NOTE]` 1M vs 1MEG 單位語意**：SPICE 語法中 `1M` 為 1 毫 ($10^{-3}$)，`1MEG` 為 1 百萬 ($10^6$)，參數簽名原樣提取不做數值有損轉換。
