# knowledge-db 倒排索引與 BM25 語意檢索引擎指南 (Retrieval Guide)

> 模組名稱：`knowledge-db`  
> 核心模組：`knowledge_db.retrieval`  
> 演算法：多欄位加權 Okapi BM25 + 平滑 IDF + Exact Match Boost  

---

## 📌 1. 檢索引擎架構

`knowledge-db` 檢索引擎透過建立多欄位倒排索引 (`InvertedIndex`)，將代碼與文檔符號提取為結構化倒排表，並透過 `BM25Engine` 進行多欄位加權評分與條件過濾。

---

## 📐 2. BM25 多欄位加權評分公式

### 2.1 欄位加權權重
| 欄位名稱 | 權重 | 說明 |
| :--- | :---: | :--- |
| **`name`** | **3.5** | 類別/函式/巨集名稱或文檔標題 (最高優先級) |
| **`signature`** | **2.0** | 函式或類別宣告簽名 (含參數與型別) |
| **`members`** | **2.0** | 類別內部公開/保護方法與成員欄位 |
| **`docstring`** | **1.5** | 文檔說明、段落內文或註解說明 |

### 2.2 平滑 IDF 公式
為防止高頻詞出現負分數，IDF 計算採用平滑截斷：
$$\text{IDF}(q) = \ln\left(1 + \max\left(0, \frac{N - n(q) + 0.5}{n(q) + 0.5}\right)\right)$$

### 2.3 Exact Match 2.0x 置頂加權
當使用者輸入之查詢字串與符號之 `name` 完全精確一致時，加權總分額外乘上 **2.0x 置頂係數**，確保精準查詢時目標符號絕對置頂。

---

## 🛠️ 3. CLI 語意檢索指令

```powershell
# 1. 全空間聯集檢索
python yscb.py knowledge-db search PIDController

# 2. 限定空間檢索
python yscb.py knowledge-db search "狀態機更新" --space=project_main

# 3. 限定符號類型或程式語言
python yscb.py knowledge-db search "Controller" --kind=class --lang=cpp --limit=5
```

---

## 💻 4. Python SDK 檢索呼叫

```python
from knowledge_db.retrieval import InvertedIndex, BM25Engine, QueryFilter
from knowledge_db.tokenizer import CodeTokenizer
from knowledge_db.thesaurus import ThesaurusEngine

# 1. 建立倒排索引
tokenizer = CodeTokenizer()
index = InvertedIndex(space_name="main")
index.build(symbols, tokenizer=tokenizer)

# 2. 執行檢索
engine = BM25Engine(tokenizer=tokenizer, thesaurus=ThesaurusEngine())
flt = QueryFilter(languages=["python", "cpp"], limit=10)

results = engine.search("馬達驅動", index=index, filter_cfg=flt)
for r in results:
    print(f"[{r.score:.2f}] {r.symbol.name} ({r.symbol.file_path}:{r.symbol.line_number})")
```
