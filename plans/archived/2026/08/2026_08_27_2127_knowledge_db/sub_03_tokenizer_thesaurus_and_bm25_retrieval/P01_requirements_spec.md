# 需求規格說明書 (Requirements Specification)

> 功能名稱：knowledge-db 子計畫 03: 分詞、同義詞與 BM25 語意檢索引擎 (Tokenizer, Thesaurus & BM25 Retrieval)  
> 建立日期：2026-08-28  
> 所屬主計畫：`plans://2026_08_27_2127_knowledge_db/`  
> 狀態：Confirmed  
> 依據 P00：[P00_semantic_requirements.md](./P00_semantic_requirements.md)  
> 模板版本：v1.4  

---

## 1. 功能需求清單 (Functional Requirements)

| 需求編號 | 需求名稱 | 詳細規格描述 | 優先級 | 對應 P00 語意 / 決策 |
| :--- | :--- | :--- | :---: | :--- |
| **FR-01** | **代碼/文檔混合分詞器 (`CodeTokenizer`)** | 實作純 Python 正則與狀態分詞器：<br/>1. 程式碼標識符拆解（`camelCase`、`snake_case`、`ALL_CAPS`、縮寫混合，保留原始詞與子詞）。<br/>2. CJK 中文字元單字與 2-gram 滑動窗口切分。<br/>3. 中英文通用停用詞與純標點過濾。 | P0 | [P00:DR-01] |
| **FR-02** | **雙層同義詞擴展引擎 (`ThesaurusEngine`)** | 實作同義詞索引與查詢擴展器：<br/>1. 內建通用軟體工程中英對照詞庫（`create/init/new/建立`, `search/query/find/搜尋` 等）。<br/>2. 支援動態合併專案與空間自訂同義詞庫 (`ThesaurusConfig`)。<br/>3. 提供 `expand_query(tokens: List[str]) -> List[str]` 進行雙向查詢擴展。 | P0 | [P00:DR-01] |
| **FR-03** | **倒排索引資料模型與建置 (`InvertedIndex`)** | 實作多欄位倒排索引結構：<br/>1. 記錄每個 Term 對應之 Posting 清單（`doc_id`, `field_term_freqs`, `doc_length`）。<br/>2. 計算文件集合總數 $N$ 與平均欄位長度 $\text{avgdl}$。<br/>3. 計算詞條 IDF 逆向文件頻率。 | P0 | [P00:DR-02] |
| **FR-04** | **多欄位加權 BM25 評分引擎 (`BM25Engine`)** | 實作 Okapi BM25 核心評分公式（$k_1=1.5, b=0.75$）：<br/>1. 支援多欄位自訂加權（預設 `name: 3.5`, `signature: 2.0`, `members: 2.0`, `docstring: 1.5`）。<br/>2. 精確全字符號名稱匹配額外享有 **2.0x 置頂加權**。 | P0 | [P00:DR-02] |
| **FR-05** | **複合條件過濾器 (`QueryFilter`)** | 支援檢索條件過濾：包含指定空間清單 (`spaces`)、程式語言 (`languages`)、符號類型 (`kinds`)、最低分數門檻 (`min_score`) 與回傳數量上限 (`limit`, 預設 20)。 | P0 | [P00:DR-03] |
| **FR-06** | **結構化檢索結果 (`SearchResult`)** | 定義不可變 `@dataclass` 檢索結果，封裝命中符號 (`symbol`)、評分 (`score`)、命中關鍵詞 (`matched_terms`)、所屬空間 (`space`) 與上下文摘要片段 (`snippet`)。 | P0 | [P00:DR-03] |
| **FR-07** | **倒排索引序列化與持久化快取** | 支援將空間建立之 `InvertedIndex` 匯出為 JSON 快取檔案 (`storage://knowledge-db/indices/<space>.index.json`)，並支援秒級載入還原。 | P0 | [P00:DR-02] |
| **FR-08** | **CLI 語意檢索指令 (`search`)** | 在 `scripts/cli.py` 新增 `search <query> [--space=name] [--kind=type] [--lang=py] [--limit=10]` 指令，支援命令列快速語意搜尋並以格式化表格輸出。 | P0 | [P00:DR-03] |

---

## 2. 邊界與異常情況 (Edge Cases & Failure Modes)

| 邊界編號 | 情境說明 | 預期防禦與處理行為 |
| :--- | :--- | :--- |
| **EC-01** | **輸入空字串或純空白/標點之查詢 Query** | `CodeTokenizer.tokenize` 回傳空清單 `[]`；檢索引擎安全回傳空結果 `[]`，不引發異常。 |
| **EC-02** | **查詢詞未命中任何倒排索引 Term** | 各 Term 評分為 0，檢索引擎安全回傳空結果 `[]`。 |
| **EC-03** | **文件長度為 0 或欄位為空 (Docstring/Signature 為空)** | BM25 計算時安全處理除以零或長度為 0 情況，使用 `max(1, doc_len)` 防止浮點數除以零。 |
| **EC-04** | **輸入超長 Query（> 500 字元）或大量重複單字** | Tokenizer 自動去重或截斷過長詞條，計算上限受保護，單次搜尋耗時維持在 `< 30ms`。 |
| **EC-05** | **多個詞群同義詞互相循環參照** | `ThesaurusEngine` 使用集合 (`Set`) 進行查詢擴展，防止無窮遞迴與重複擴展。 |
| **EC-06** | **特殊符號/正則字元作為 Query（如 `*`, `?`, `[`, `(`）** | Tokenizer 採字符安全提取，不使用未轉義正則進行字串比對，徹底防止正則注入或崩潰。 |
| **EC-07** | **未建立索引之空間發起檢索** | 拋出結構化 `KnowledgeDBError` 或自動回退至即時解析建立。 |
| **EC-08** | **多空間聯集檢索評分正規化** | 跨空間檢索時共用統一評分標準，按加權總分降序全局排序。 |

---

## 3. 非功能需求 (Non-Functional Requirements)

| 需求編號 | 類別 | 指標與量化約束 |
| :--- | :--- | :--- |
| **NFR-01** | **零外部相依 (Zero External Dependency)** | 100% 純 Python 原生標準庫（`math`, `re`, `collections`, `dataclasses`, `json` 等），嚴禁 jieba、scikit-learn、nltk 等第三方套件。 |
| **NFR-02** | **檢索延遲與記憶體效率** | 萬級符號索引（10,000 Symbols）常駐記憶體 `< 30MB`，單次 BM25 多欄位檢索延遲 `< 20ms`。 |
| **NFR-03** | **測試品質守門** | 單元測試 100% 繼承 `YSCBTestCase`，覆蓋分詞、同義詞、倒排索引與 BM25 評分，模組跑測 100% Passed。 |
| **NFR-04** | **模組邊界與 Dogfooding** | 源碼 100% 位於 `source/knowledge-db/`，路徑存取透過 Core URI 協議。 |

---

## 4. 知識庫與踩坑紀錄查閱 (Known Gotchas & CAUTIONs)

- > [!IMPORTANT]
  > **零外部庫分詞實踐**：嚴禁依賴 jieba 等 C 擴展或外部字典。中文字元使用單字 + 2-gram 滑動切分已具備優異之召回率與詞組精確度；程式碼標識符透過駝峰/底線正則切分。

- > [!WARNING]
  > **BM25 IDF 計算防負數**：當詞條出現在過半數文件時，標準 $\ln((N - n + 0.5)/(n + 0.5))$ 可能出現負值，必須加上平滑截斷 $\ln(1 + (N - n + 0.5)/(n + 0.5))$ 確保權重始終大於 0。
