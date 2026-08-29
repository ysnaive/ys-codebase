# knowledge-db 分詞與同義詞擴展指南 (Tokenizer & Thesaurus Guide)

> 模組名稱：`knowledge-db`  
> 核心模組：`knowledge_db.tokenizer`、`knowledge_db.thesaurus`  
> 依賴：100% Python 原生標準庫 (Zero External Dependency)  

---

## 📌 1. 概述與混合分詞架構

`knowledge-db` 分詞子系統專為軟體工程代碼標識符與中英文文檔設計，不依賴外部 C 擴展或第三方字典（如 jieba/nltk），具備極致純淨度與跨平台確定性。

### 核心分詞策略 (`CodeTokenizer`)
1. **代碼標識符拆解 (CamelCase & SnakeCase)**：
   - 駝峰拆解：`PIDController` ➔ `["pid", "controller", "pidcontroller"]`
   - 縮寫保護：`getHTTPResponse` ➔ `["get", "http", "response", "gethttpresponse"]`
   - 底線拆解：`user_id_v5` ➔ `["user", "id", "v5", "user_id_v5"]`
2. **CJK 中文字元 1-gram + 2-gram 滑動窗口**：
   - 兼顧單字召回率與詞組精確度：`"狀態機更新"` ➔ `["狀", "態", "機", "狀態", "態機", "更新", "狀態機"]`
3. **停用詞過濾與標點過濾**：
   - 自動過濾中英文高頻功能詞（`在`, `的`, `與`, `the`, `is`, `for`, `with` 等）。

---

## 🔄 2. 雙層三階同義詞與關聯詞擴展引擎 (`ThesaurusEngine`)

### 2.1 內建通用軟體工程詞庫
模組內建 18 組軟工常用雙向中英對照同義詞：
- `["建立", "創建", "初始化", "建置", "create", "init", "initialize", "new", "build", "construct"]`
- `["搜尋", "檢索", "查詢", "尋找", "search", "query", "find", "lookup", "retrieval"]`
- `["狀態", "現狀", "status", "state"]`
- `["控制", "控制器", "control", "controller"]`
- `["引擎", "核心", "engine", "core"]`

### 2.2 三階加權展開管線 (Three-Tier Weighted Expansion)
為了在大幅提升檢索廣度 (Recall) 的同時完全不稀釋首屏精準度 (Precision)，`ThesaurusEngine` 採用三階加權展開架構：

| 層級 (Tier) | 類型 | 權重 | 說明 |
| :--- | :---: | :---: | :--- |
| **Tier 1** | **原始詞 (Original)** | **`1.0`** | 使用者查詢輸入之原始詞條，享完整基礎 BM25 分數與 Exact Match 置頂加權。 |
| **Tier 2** | **雙向同義詞 (Synonym)**<br/>**單向別名 (Alias)** | **`0.6`** | 雙向等價替換詞（`搜尋 <=> search`）與單向特化別名（`ngspice => spice`），以 0.6 衰減係數杜絕查詢漂移。 |
| **Tier 3** | **領域關聯詞 (Related)** | **`0.25`** | 領域關聯與上下游術語（`parser <-> ast <-> lexer`），作為底層微弱加分與寬鬆召回。 |

### 2.3 權重衝突解決原則 (Max-Weight Retention)
若同一個詞條同時由多個路徑被命中（例如既是原始詞又是其他詞展開之同義詞/關聯詞），系統剛性保留最高權重（$1.0 > 0.6 > 0.25$）。

---

## 💻 3. Python SDK 使用範例

```python
from knowledge_db.tokenizer import CodeTokenizer
from knowledge_db.thesaurus import ThesaurusEngine

# 1. 混合分詞
tokenizer = CodeTokenizer()
tokens = tokenizer.tokenize("在 PIDController 中計算速度")
print("Tokens:", tokens)
# 輸出: ['pid', 'controller', 'pidcontroller', '計', '算', '計算', '速度', '計算速度']

# 2. 三階加權同義詞、別名與關聯詞擴展
thesaurus = ThesaurusEngine(
    custom_groups=[["底盤", "chassis", "drivetrain"]],
    custom_aliases={"ngspice": ["spice", "circuit"]},
    custom_related=[["parser", "ast", "lexer"]],
)

# 2a. 加權展開 (返回 List[WeightedToken])
weighted_tokens = thesaurus.expand_query_weighted(["ngspice", "parser"])
for wt in weighted_tokens:
    print(f"Term: {wt.term}, Weight: {wt.weight}, Kind: {wt.kind}")

# 2b. 向後相容扁平展開 (返回 List[str])
flat_tokens = thesaurus.expand_query(["搜尋", "底盤"])
print("Expanded:", flat_tokens)
```

