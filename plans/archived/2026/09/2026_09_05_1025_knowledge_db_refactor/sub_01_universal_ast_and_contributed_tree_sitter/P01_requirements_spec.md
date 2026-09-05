# 需求規格說明書 (Requirements Specification)

> 功能名稱：sub_01_universal_ast_and_contributed_tree_sitter  
> 建立日期：2026-09-05  
> 所屬主計畫：2026_09_05_1025_knowledge_db_refactor  
> 狀態：Confirmed  
> 依據 P00：[P00_discuss.md](./P00_discuss.md)  
> 模板版本：v1.5  

---

## 1. 功能需求清單 (Functional Requirements)

| 需求編號 | 需求名稱 | 詳細規格描述 | 優先級 | 對應 P00 語意 |
| :--- | :--- | :--- | :---: | :--- |
| **FR-01** | 遞迴階層 Universal AST 模型 | 核心符號定義為 `UnifiedSymbol`，具備 `id`、`name`、`fqn`（全限定名）、`kind`、`file_path`、`line_number`、`end_line`、`scope_path`、`parent_id`、`children`（子符號列表）。廢除次等之 `MemberInfo`，所有符號節點均為遞迴一等公民；對外保留 `members` 屬性映射以確保向後相容。 | P0 | [P00:DR-01] |
| **FR-02** | 結構化簽名與 Search Payload 內聚 | 符號支援結構化簽名參數解析（名稱、型別標註、預設值、回傳型別），並內聚 `search_payload`（包含 Name、Signature、Docstring、前 10 行精煉代碼），供後續 BM25 與向量模組直接秒級消費。 | P0 | [P00:DR-02] |
| **FR-03** | `contributes.knowledge_db` 外掛註冊協議 | 制定 YSCB 語意擴充規格，各模組可於 `contribute.json` 聲明 `languages` 清冊（含 `id`、`extensions`、`mode`、`grammar`、`query_file` 與 `custom_kinds`）。實作動態發現與語言註冊表 (`LanguageRegistry`)。 | P0 | [P00:DR-03] |
| **FR-04** | Tree-sitter S-Expression 宣告式查詢驅動器 | 引入 `tree-sitter`，實作通用 `TreeSitterDriver`；透過讀取各語言專屬之 `.scm` 查詢規則（如 `@definition.function`、`@symbol.name`、`@symbol.signature`、`@symbol.docstring`）自動萃取並組裝出標準 `UnifiedSymbol` 樹。 | P0 | [P00:DR-04] |
| **FR-05** | 零特權內建自貢獻與手刻 Regex 解析器淘汰 | 徹底刪除 `parsers/` 下 2,000 行手刻正則狀態機。核心不 hardcode 任何內建語言解析特權；Python, C, C++, JS/TS, C#, Markdown 全數編寫為 `.scm` 規格並由 `knowledge-db` 自身之 `contributes` 區塊宣告自貢獻；特化 DSL (如 SPICE) 採編程化 custom parser 外掛註冊。 | P0 | [P00:DR-05]<br/>[P00:DR-06] |
| **FR-06** | 序列化與增量快取無損對接 | `UnifiedSymbol` 支援雙向無損之 `to_dict()` 與 `from_dict()` 序列化，無縫對接既有之 Gzip / JSON 快取存取與 SHA-1/mtime 增量指紋掃描管線。 | P0 | [P00:DR-01] |
| **FR-07** | 手刻解析器與多餘測試案例清理 | 徹底清理 `parsers/` 下所有歷史手刻正則實作檔案；盤點並清理 `tests/` 中針對舊有手刻正則特性、私有實作或 `MemberInfo` 私有斷言之多餘/過時測試用例，重構為基於 Universal AST 的清晰簡潔測試套件。 | P0 | [P00:DR-05]<br/>[P00:DR-06] |

---

## 2. 邊界與異常情況 (Edge Cases & Failure Modes)

| 邊界編號 | 情境說明 | 預期防禦與處理行為 |
| :--- | :--- | :--- |
| **EC-01** | 程式碼語法錯誤或殘缺檔案 | 充分利用 Tree-sitter 的 Error Recovery 容錯機制，解析並提取殘缺語法中已識別之合法符號，嚴禁拋出未捕獲之異常中斷主進程。 |
| **EC-02** | 缺少 Grammar 套件或依賴未安裝 | 若某模組宣告之語言對應之 Tree-sitter grammar 尚未在微環境安裝，系統記錄警告日誌並優雅跳過該語言檔案，嚴禁中斷整體掃描與其餘語言解析。 |
| **EC-03** | S-Expression 查詢語法錯誤或檔案遺失 | 若外掛指定之 `.scm` 語法有誤或路徑遺失，記錄診斷錯誤並隔離該語言解析器，不影響其他語言正常運作。 |
| **EC-04** | 超大型單檔 (>10,000 行) 或超深巢狀結構 | 解析與樹狀走訪時加入遞迴深度防護，防止超深巢狀導致 Python Call Stack 溢出。 |
| **EC-05** | 未註冊之副檔名與純文字檔案 | 面對無對應 Parser 的副檔名，依附副檔名與 Content-Type 自動忽略或以純文字/文檔章節提取兜底，回傳空符號清單。 |

---

## 3. 非功能需求 (Non-Functional Requirements)

| 需求編號 | 類別 | 指標與量化約束 |
| :--- | :--- | :--- |
| **NFR-01** | 解析效能 | Tree-sitter 底層 C/C++ 綁定執行速度，千行程式碼解析耗時須 $\le 10\text{ms}$，較手刻正則提升 3~5 倍以上。 |
| **NFR-02** | 相依性治理 | `tree-sitter` 及其 grammar 嚴格透過 `source/knowledge-db/manifest.json` 之 `pip_dependencies` 宣告，由 `yscb.venv://` 私有微環境統一管理。 |
| **NFR-03** | 記憶體與快取體積 | 優化符號樹節點資料結構，全庫 10,000 個符號快取序列化體積須控制於 $\le 5\text{MB}$。 |
| **NFR-04** | 對外 API 相容性 | 對外暴露之 `UnifiedSymbol` 欄位與 CLI JSON 格式 100% 保持相容，既有 130 個測試中涉及符號讀取的案例無痛適配。 |

---

## 4. 知識庫與踩坑紀錄查閱 (Known Gotchas & CAUTIONs)

- **`[!NOTE]`**：Tree-sitter Python 綁定自 0.22 版本起重構了 API 契約（`Language` 與 `Parser` 介面），需明確宣告相容之版本範圍（如 `tree-sitter>=0.21.3,<0.24.0`），並使用預編譯二進位 Wheel，確保在 Windows 與 Linux 環境下均能無障礙安裝。
- **`[!CAUTION]`**：廢除 `MemberInfo` 時，需在 `UnifiedSymbol` 上提供 `@property def members(self) -> List[MemberInfo]` 動態適配層，避免下游依賴舊屬性時引發 `AttributeError`。
