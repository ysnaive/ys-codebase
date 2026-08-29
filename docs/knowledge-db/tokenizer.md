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

## 🔄 2. 宣告式詞庫與多跳鏈式加權擴展引擎 (`ThesaurusEngine`)

### 2.1 源碼解耦與 Contributes 宣告式詞庫
`ThesaurusEngine` 為 100% 源碼解耦之純淨無狀態容器，內部零硬編碼詞表。所有預設詞庫由 `source/knowledge-db/contributes/knowledge-db.json` 透過 `core.contributes` 管道宣告與注入，涵蓋六大核心維度：
1. **常用日用語與軟工作業動名詞** (建立/查詢/讀取/儲存/更新/刪除/啟動/停止/暫停/恢復/快取/重試/鎖定/註冊/比較等)。
2. **C / C++ 術語** (指標、引用、模板、巨集、標頭檔、建構/解構子、多型、命名空間、記憶體配置，以及 `cpp`, `raii`, `stl`, `smart_ptr` 等別名)。
3. **C# 術語 (CSharp)** (屬性、委派、非同步/異步、反射、列舉器、擴充方法、依賴注入，以及 `csharp`, `linq` 等別名)。
4. **Python 術語** (裝飾器、生成器、型別標註、魔術方法、虛擬環境、推導式、模組/套件，以及 `python`, `pydantic`, `dataclass` 等別名)。
5. **SPICE 電路網表術語** (網表、子電路、模型/參數、節點/接腳、暫態/交流/直流分析，以及 `ngspice`, `hspice`, `mosfet` 等別名)。
6. **資電類學系術語 & 常用演算法** (邏輯閘/正反器、時脈、匯流排、頻寬、中斷/ISR、類比/ADC/DAC、DSP/FFT、STA時序、嵌入式/MCU、狀態機/FSM，以及 **A* 尋路/Dijkstra/拓撲排序/動態規劃DP/廣度深度搜尋BFS/DFS/紅黑樹/雜湊表** 等)。

### 2.2 三階加權展開與多跳鏈式傳播管線 (Multi-Hop Transitive Chaining)
為了在大幅提升檢索廣度 (Recall) 的同時完全不稀釋首屏精準度 (Precision)，`ThesaurusEngine` 採用三階加權展開與多跳鏈式傳播架構：

```text
[使用者輸入查詢] ──> Tier 1: 原始詞 (Weight: 1.0)
                           │
                           ├──> Tier 2: Hop 1 雙向同義詞 / 單向別名 (Weight: 0.6)
                           │         │
                           │         └──> Tier 3: Hop 2 領域關聯詞 (Weight: 0.25)
                           │                   │
                           └───────────────────┴──> Tier 3: Hop 3 關聯詞同義反查 (Weight: 0.25)
```

| 層級 (Tier) | 類型 | 權重 | 說明 |
| :--- | :---: | :---: | :--- |
| **Tier 1** | **原始詞 (Original)** | **`1.0`** | 使用者查詢輸入之原始詞條，享完整基礎 BM25 分數與 Exact Match 置頂加權。 |
| **Tier 2** | **雙向同義詞 (Synonym)**<br/>**單向別名 (Alias)** | **`0.6`** | 雙向等價替換詞（`搜尋 <=> search`）與單向特化別名（`ngspice => spice`, `astar => pathfinding`），以 0.6 衰減係數杜絕查詢漂移。 |
| **Tier 3** | **領域關聯詞 (Related)** | **`0.25`** | 跨語言領域關聯與上下游術語（`尋路 ➔ astar ➔ dijkstra ➔ 最短路徑`），作為底層微弱加分與寬鬆召回。 |

### 2.3 權重衝突解決原則 (Max-Weight Retention)
若同一個詞條同時由多個路徑被命中（例如既是原始詞又是其他詞展開之同義詞/關聯詞），系統剛性保留最高權重（$1.0 > 0.6 > 0.25$）。

---

## 💻 3. Python SDK 使用範例

```python
from knowledge_db.tokenizer import CodeTokenizer
from knowledge_db.space import SpaceManager
from knowledge_db.thesaurus import ThesaurusEngine

# 1. 混合分詞
tokenizer = CodeTokenizer()
tokens = tokenizer.tokenize("在 PIDController 中計算速度")
print("Tokens:", tokens)

# 2. 透過 SpaceManager 工廠裝配完整詞庫之 ThesaurusEngine
sm = SpaceManager()
engine = sm.create_thesaurus_engine()

# 2a. 多跳鏈式加權展開 (輸入中文 "尋路" 自動鏈式展開至 astar, dijkstra, 最短路徑)
weighted_tokens = engine.expand_query_weighted(["尋路"])
for wt in weighted_tokens:
    print(f"Term: {wt.term:<12} Weight: {wt.weight:<4} Kind: {wt.kind}")

# 2b. 向後相容扁平展開 (返回 List[str])
flat_tokens = engine.expand_query(["搜尋", "底盤"])
print("Expanded:", flat_tokens)
```

