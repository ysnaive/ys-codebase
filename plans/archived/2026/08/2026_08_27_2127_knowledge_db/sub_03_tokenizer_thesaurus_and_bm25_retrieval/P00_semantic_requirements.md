# 語意需求說明書 (Semantic Requirements Discovery)

> 功能名稱：knowledge-db 子計畫 03: 分詞、同義詞與 BM25 語意檢索引擎 (Tokenizer, Thesaurus & BM25 Retrieval)  
> 建立日期：2026-08-28  
> 所屬主計畫：`plans://2026_08_27_2127_knowledge_db/`  
> 狀態：Confirmed  
> 計畫類型：Feature  
> 模板版本：v1.1  

---

## 1. 使用者原始需求與意圖 (User Intent)

- **原始陳述**：接續 `knowledge-db` 主計畫之子計畫 03（`sub_03_tokenizer_thesaurus_and_bm25_retrieval`）。基於 `sub_01`（空間管理與 Schema）與 `sub_02`（多語言解析器與 Bundle 打包）之產物，構建代碼與文檔專用的高效語意檢索引擎。
- **核心目標**：
  1. **代碼/文檔混合分詞器 (`CodeTokenizer`)**：
     - 支援 CJK 中文字元切分（單字 + 2-gram 相鄰雙字滑動窗口）。
     - 支援程式碼標識符智能切分（`camelCase`、`PascalCase`、`snake_case`、`ALL_CAPS_MACRO`、數字與縮寫混合如 `V5_PID_Controller`）。
     - 支援中英文停用詞過濾與小寫標準化。
  2. **雙層同義詞擴展引擎 (`ThesaurusEngine`)**：
     - 內建標準軟體工程通用同義詞庫（如建置、搜尋、狀態、處理等中英雙向對照）。
     - 動態合併專案/空間層級自訂同義詞庫（`ThesaurusConfig`）。
     - 支援查詢端詞條雙向擴展（Query Expansion）。
  3. **多欄位加權 BM25 倒排索引與檢索引擎 (`InvertedIndex` & `BM25Engine`)**：
     - 構建記憶體與磁碟倒排索引（`Term ➔ Posting List: (doc_id, field_frequencies, doc_length)`）。
     - 實作 BM25 演算法（$k_1 = 1.5, b = 0.75$），支援多欄位加權評分（例如：`name: 3.5`, `signature: 2.0`, `members: 2.0`, `docstring: 1.5`）。
     - 實作精確名稱匹配置頂加權 (Exact Match Boost)。
     - 支援複合條件過濾器 `QueryFilter`（`spaces`, `languages`, `kinds`, `min_score`, `limit`）。
     - 輸出結構化 `SearchResult`（含評分、命中詞列表與關鍵摘要高亮）。
  4. **零外部相依 (Zero External Dependency)**：100% 採用純 Python 3.9+ 原生標準庫（`math`, `re`, `collections`, `dataclasses`, `json` 等）。
- **邊界排除 (Explicitly Excluded)**：
  - 統一門面 SDK (`KnowledgeEngine`) 與 agents-workflow 深入注入連動留待 `sub_04` 實作。

---

## 2. 核心討論與決策紀錄 (Discussion & Decisions)

### [P00:DR-01] 代碼/中文混合分詞策略 (CodeTokenizer)
- **切分流程**：
  1. 正則切分標點與空白。
  2. 對英文與程式碼識別碼進行駝峰/底線切分：
     - `getHTTPResponse` ➔ `["get", "http", "response", "gethttpresponse"]`（保留原始完整 token 與拆解子 token）。
     - `PIDController` ➔ `["pid", "controller", "pidcontroller"]`。
  3. 對 CJK 中文字元進行 1-gram 與 2-gram 滑動：
     - `"狀態機"` ➔ `["狀", "態", "機", "狀態", "態機", "狀態機"]`。
  4. 統一轉為小寫並過濾長度小於 1 或停用標點符號。

---

### [P00:DR-02] BM25 多欄位加權與評分公式
- **BM25 參數**：$k_1 = 1.5, b = 0.75$。
- **欄位加權權重 (Field Weights)**：
  - `name` (符號名稱 / 標題)：權重 **3.5**
  - `signature` (函式/類別宣告簽名)：權重 **2.0**
  - `members` (成員名稱與簽名)：權重 **2.0**
  - `docstring` (文檔說明 / 註解)：權重 **1.5**
- **精確匹配加權 (Exact Match Boost)**：若 Query 與符號 `name` 完全一致，分數額外乘上 **2.0** 加權以確保直擊命中目標置頂。

---

### [P00:DR-03] 檢索結果資料模型 (`SearchResult`)

```python
@dataclass(frozen=True)
class SearchResult:
    symbol: UnifiedSymbol                            # 命中之統一符號模型
    score: float                                     # BM25 加權總分
    matched_terms: List[str]                         # 命中的查詢詞/同義詞
    space: str                                       # 所屬知識庫空間
    snippet: str = ""                                # 摘要或高亮片段
```

---

## 3. 開放議題與確認紀錄

- [x] **確認 1 (分詞策略與 2-gram 窗口)**：CJK 採用單字 + 2-gram，程式碼保留全詞與拆解子詞，兼顧召回率與精確度。
- [x] **確認 2 (BM25 欄位權重預設值)**：Name 3.5, Signature 2.0, Member 2.0, Docstring 1.5 與 2.0x Exact Boost。
- [x] **確認 3 (內建通用同義詞庫)**：內建常用軟工通用詞庫並動態合併專案/空間自訂擴展。
