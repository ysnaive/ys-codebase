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

## 🔄 2. 雙層同義詞擴展引擎 (`ThesaurusEngine`)

### 2.1 內建通用軟體工程詞庫
模組內建 18 組軟工常用雙向中英對照同義詞：
- `["建立", "創建", "初始化", "建置", "create", "init", "initialize", "new", "build", "construct"]`
- `["搜尋", "檢索", "查詢", "尋找", "search", "query", "find", "lookup", "retrieval"]`
- `["狀態", "現狀", "status", "state"]`
- `["控制", "控制器", "control", "controller"]`
- `["引擎", "核心", "engine", "core"]`

### 2.2 查詢端雙向擴展 (Query Expansion)
檢索時自動將查詢詞展開至同義詞集合，例如輸入 `"搜尋底盤"` 自動展開為 `["搜尋", "search", "query", "底盤", "chassis", "drivetrain"]`，大幅提升跨語言與概念檢索召回率。

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

# 2. 同義詞擴展
thesaurus = ThesaurusEngine(custom_groups=[["底盤", "chassis", "drivetrain"]])
expanded = thesaurus.expand_query(["搜尋", "底盤"])
print("Expanded:", expanded)
# 輸出: ['搜尋', '底盤', 'search', 'query', 'chassis', 'drivetrain', ...]
```
