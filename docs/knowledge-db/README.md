---
target: "Knowledge-DB"
doc_type: "readme"
status: "active"
source_paths:
  - "yscb://source/knowledge-db/knowledge_db/engine.py"
  - "yscb://source/knowledge-db/knowledge_db/pipeline.py"
  - "yscb://source/knowledge-db/knowledge_db/config.py"
  - "yscb://source/knowledge-db/scripts/cli.py"
related_docs:
  - "./architecture.md"
  - "./retrieval.md"
  - "./DESIGN_NOTES.md"
last_updated: "2026-10-15"
---

# Knowledge Database 模組手冊 (Knowledge-DB Overview)

> 模組名稱：`knowledge-db`  
> 職責定位：YS-Codebase 專案代碼與文檔語意知識庫基礎設施，提供多來源空間宣告、雙軌聚合、`unified.meta.bin` 原生二進位快照與 JIT / `KnowledgeDBServiceWorker` 熱自癒、Tree-sitter 宣告式多語言 AST 解析、BM25 + FastEmbed ONNX 雙軌向量 RRF 複合檢索與靜態調用圖譜分析服務。

---

## 1. 模組定位與願景 (Vision & Goals)

`knowledge-db` 模組旨在為 YS-Codebase 生態體系建立高效、高內聚、強韌的語意檢索與代碼拓撲核心設施。主要能力包括：
- **多空間治理 (Space Management)**：支援多模組聯動注入 (`module://<donor>/contributes/knowledge-db.json`) 與專案 `config/knowledge-db/contribute.json` 雙軌階層覆蓋。
- **全空間聯集處理 (Union Scope)**：無單一 `default_space` 強制約定，全系統以所有有效空間之聯集作為全域處理範圍，並對重疊實體檔案進行 100% 唯一解析去重。
- **極速二進位快照與雙軌熱自癒 (`unified.meta.bin` & Hot Healing)**：採用 Magic `YFP1` + `struct` 原生二進位快照搭配 `os.scandir` 微秒級變更嗅探；支援前台 JIT 差量熱修補與背景常駐 `KnowledgeDBServiceWorker` (500ms 防抖) 自動熱自癒。
- **Tree-sitter 宣告式 AST 解析 (Universal AST)**：基於 `TreeSitterDriver` 與 S-Expression (`.scm`) 查詢規則，透過零特權自貢獻 (`contributes.knowledge-db.languages`) 原生支援 Python、C、C++、C#、JavaScript、TypeScript、Markdown、SPICE、HTML、CSS 等 10 大語言符號與調用點提取。
- **雙軌 RRF 複合檢索與平滑降級 (Hybrid Search)**：結合中英混排分詞 (`MultilingualTokenizer`)、三階加權同義詞擴展、多欄位加權 BM25 與 FastEmbed ONNX 離線向量推論（動態維度解析，預設 `BAAI/bge-small-zh-v1.5` 為 `512-dim`），透過倒數排名融合 (RRF $k=60$) 精準召回，並具備 100% 剛性平滑降級純 BM25 保證。
- **跨檔案調用圖譜與影響面分析 (Call Graph & Impact)**：基於 `networkx.DiGraph` 與四階 FQN / Import 作用域消歧，支援上游調用者 (`callers`)、下游被調用者 (`callees`) 與多階重構爆炸半徑 (`impact`) 追蹤。

---

## 2. 意圖導向三級複雜度矩陣 (3-Tier View Matrix)

本模組檢索與拓撲指令（`search`、`callers`、`callees`、`impact`）全面支援三級意圖複雜度與高密度 JSON 輸出（搭配 8,000 字元動態預算階梯衰減與 `UniversalRedundancyFilter` 切片去重）：

| 複雜度層級 (Tier) | 觸發旗標 | 適用情境與終端輸出 | Agent 推薦 `--json` 格式 |
| :--- | :---: | :--- | :--- |
| **Tier 1: 極簡大綱 (Simple)**<br/>*(預設模式)* | *(無旗標)*<br/>`--simple` | 僅列出命中檔案、符號名稱、行號區間與分數，零代碼負擔。 | **超緊湊 JSON** (`--json`)：<br/>Token 消耗 $< 50$ Tokens，適合快速存在性確認。 |
| **Tier 2: 內文瀏覽 (Preview)**<br/>*(Agent 探索首選)* | `-s` / `--snippet`<br/>`--preview` | 一步到位取得帶行號之 AST 代碼切片、簽名與 Docstrings。 | **高密度業務 JSON** (`--json -s`)：<br/>剪除雜湊 ID 與除錯欄位，資訊密度高達 86%+。 |
| **Tier 3: 全量除錯 (Detail)** | `-d` / `--detail`<br/>`--verbose` | 包含 40 碼 SHA-1、BM25 分詞矩陣 (`matched_terms`) 與全量屬性。 | **全量除錯 JSON** (`--json -d`)：<br/>保留完整 Schema 與 2-space 縮排。 |

---

## 3. CLI 快速上手 (Quick Start)

系統收斂為 8 大正交標準指令集：`status`, `index`, `search`, `callers`, `callees`, `impact`, `clean`, `model`。

```bash
# 1. 查看所有已註冊空間、快取、索引狀態與增量快照差異 (--scan / --diff)
python yscb.py knowledge-db status
python yscb.py knowledge-db status --scan

# 2. 一鍵全管線索引建置 (掃描 -> AST 提取 -> 倒排索引 -> 調用圖譜 -> 向量特徵)，支援導出 Bundle
python yscb.py knowledge-db index --all
python yscb.py knowledge-db index --export ./output/project.bundle.json

# 3. 向量推論模型生命週期管理 (狀態查詢與顯式預載)
python yscb.py knowledge-db model status
python yscb.py knowledge-db model download

# 4. 執行 BM25 + 向量雙軌複合檢索 (預設為 Simple 單行排版，支援自動懶建置與 JIT 熱自癒)
python yscb.py knowledge-db search PIDController
python yscb.py knowledge-db search "狀態機更新" --kind=class --limit=5

# 5. 代碼/文檔分流檢索 (--ftype 與 -s / --snippet 預覽代碼切片與 Docstring 摘要)
python yscb.py knowledge-db search "PIDController" --ftype=py --json -s
python yscb.py knowledge-db search "開發規範" --ftype=md --json -s

# 6. 查詢符號上游調用者 (Who calls me?)
python yscb.py knowledge-db callers "InvertedIndex.load_binary" --json -s

# 7. 查詢符號內部調用之下游被調用者 (Whom do I call?)
python yscb.py knowledge-db callees "KnowledgeEngine.build_unified_index" --json -s

# 8. 分析重構影響面擴散拓撲 (Blast Radius Impact)
python yscb.py knowledge-db impact "InvertedIndex.patch_incremental" --depth=2 --json

# 9. 清理特定或全空間之二進位快照、Bundle、倒排索引、圖譜與向量快取
python yscb.py knowledge-db clean --all
```

---

## 4. Python SDK 快速上手 (`KnowledgeEngine`)

```python
from knowledge_db import KnowledgeEngine

# 初始化統一門面 SDK
engine = KnowledgeEngine()

# 1. 檢視系統狀態 (自 unified.meta.bin 微秒級載入)
status = engine.status()
print("Total spaces:", status["total_spaces"])

# 2. 執行多欄位複合語意搜尋 (未建索引或變更時自動觸發 JIT 熱自癒)
results = engine.search("PID 控制器速度輸出", limit=5, tier="snippet")
for res in results:
    sym = res.symbol
    print(f"[{res.score:.2f}] {sym.kind.upper()}: {sym.name} ({sym.file_path}:{sym.line_number})")
    print(f"  簽名: {sym.signature}")
    print(f"  命中: {', '.join(res.matched_terms)}")

# 3. 調用圖譜與影響面查詢 (輕量 JIT 解耦，不觸發向量推論)
callers = engine.callers("InvertedIndex.load_binary", tier="snippet")
callees = engine.callees("IndexingPipeline.build_unified_index", tier="snippet")
impact = engine.impact("UnifiedSymbol", max_depth=2)

# 4. 手動全量建置索引或清理快取
engine.build_unified_index(force=True)
engine.clean()
```

---

## 5. 相關技術文件指針

- 📐 **系統架構設計**：[architecture.md](./architecture.md)
- 🔌 **擴充點注入指南**：[contributes_guide.md](./contributes_guide.md)
- 🧩 **多語言解析器指南**：[parsers.md](./parsers.md)
- 📦 **語意打包引擎指南**：[bundler.md](./bundler.md)
- 🔤 **分詞與同義詞指南**：[tokenizer.md](./tokenizer.md)
- 🔍 **語意檢索引擎指南**：[retrieval.md](./retrieval.md)
- 🕸️ **符號調用圖譜與引用拓撲**：[call_graph_and_reference_index.md](./call_graph_and_reference_index.md)
- ⚡ **細粒度增量熱重載與常駐 Worker**：[incremental_hot_reload.md](./incremental_hot_reload.md)
- 🛡️ **設計決策與工程妥協手冊**：[DESIGN_NOTES.md](./DESIGN_NOTES.md)
- ⚙️ **Server 常駐與熱重載服務專題**：[雙軌熱重載與常駐服務架構專題](../server/hot_reload_and_services.md)

---

## 6. 組態配置與向量環境參考 (`KnowledgeDBConfig` & Environment)

### 6.1 雙層運作組態設定 (`config.project.json` / `config.local.json`)

本模組運作組態遵循 YSCB 2x2 組態矩陣，位於 `config://knowledge-db/config.project.json`（團隊共享）與 `config://knowledge-db/config.local.json`（本機覆蓋，優先權高於 project），可透過 `python yscb.py config set knowledge-db <key> <val>` 進行設定：

| 設定鍵值 (Key) | 預設值 (Default) | 型態 | 說明 |
| :--- | :--- | :---: | :--- |
| **`enable_vector_search`** | `true` | `bool` | 是否啟用 FastEmbed 向量語意檢索與特徵提取。設為 `false` 則跳過向量化並強制使用純 BM25 詞彙檢索模式。 |
| **`embedding_model`** | `"BAAI/bge-small-zh-v1.5"` | `str` | 指定 FastEmbed ONNX 嵌入模型名稱（預設模型為 `512-dim`，支援中英多語言）。 |
| **`jit_vector_timeout_seconds`** | `5.0` | `float` | JIT 增量熱自癒時 10 符號動態探針之超時臨界值（秒）。若推估耗時超過此值，自動熔斷退回純 BM25 模式以保障檢索瞬發響應。 |
| **`max_threads`** | `"auto"` | `str` / `int` | 向量推論與 ONNX Runtime 執行緒上限。預設 `"auto"` 自動限制為 `min(2, max(1, cpu_count // 2))` 以防止 CPU 排程飢餓。 |

### 6.2 向量嵌入與作業系統環境注意事項

- **動態維度解析 (Dynamic Dimension Resolution)**：`EmbeddingService` 徹底淘汰硬編碼維度常數，統一以實際加載之 FastEmbed 模型實例原生屬性 (`model.embedding_size`) 作為唯一真理來源（預設 `BAAI/bge-small-zh-v1.5` 為 `512-dim`），保證二進位快取比對與檢索維度 100% 相容。
- **離線權重探針先行 (`Probe First`)**：初始化時先以純本機路徑探測 `.onnx` 權重是否存在；若尚未執行 `model download`，絕不發起任何未認證網路請求，立即平滑退回純 BM25 檢索並於 `stderr` 輸出 `[GUARD]` 指引。
- **Windows / Anaconda 環境需求**：ONNX Runtime 依賴 Microsoft Visual C++ 2015-2022 執行期（VC++ runtime $\ge 14.4x$）。若遇 `WinError 1114`（動態連結庫初始化例行程序失敗），可透過 `conda install -c conda-forge vc14_runtime` 或安裝官方最新 VC++ Redistributable 修復。
- **符號連結權限警告抑制**：系統已預設配置 `HF_HUB_DISABLE_SYMLINKS_WARNING=1`，防止在 Windows 非管理員模式下觸發 Hugging Face Hub 的 `WinError 1314` 符號連結警告並保護 `--json` 通道純淨。

