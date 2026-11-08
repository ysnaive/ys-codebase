---
target: "Knowledge-DB"
doc_type: "readme"
status: "active"
source_paths:
  - "yscb://source/knowledge-db/knowledge_db/engine.py"
  - "yscb://source/knowledge-db/knowledge_db/pipeline.py"
  - "yscb://source/knowledge-db/knowledge_db/service.py"
  - "yscb://source/knowledge-db/knowledge_db/embedding.py"
  - "yscb://source/knowledge-db/knowledge_db/config.py"
  - "yscb://source/knowledge-db/scripts/cli.py"
related_docs:
  - "./architecture.md"
  - "./retrieval.md"
  - "./DESIGN_NOTES.md"
last_updated: "2026-11-08"
---

# Knowledge Database 模組手冊 (Knowledge-DB Overview)

> 模組名稱：`knowledge-db`  
> 職責定位：YS-Codebase Layer 3 混合語意檢索核心模組，建立於 `core.space`（Layer 1 邏輯檔案空間與指紋底座）與 `module:ast`（Layer 2 靜態語法樹、雙層分部符號與呼叫拓撲引擎）之上；透過單次解析符號共享（Single-Parse Symbol Sharing）直接消費 `ASTSnapshot`，專責提供多欄位加權 BM25 與 FastEmbed ONNX 雙軌向量 RRF 複合檢索（含空間權重 `space_weights` 加成）及兩階段常駐背景自癒服務。

---

## 1. 模組定位與願景 (Vision & Goals)

`knowledge-db` 模組與 `core.space`、`ast` 共同構成嚴格三階單向無環圖（`core.space -> ast -> knowledge-db`）：
- **三階單向 DAG 與單次解析符號共享 (`module:ast` `ASTSnapshot`)**：語法樹解析、7 大官方方言隔離 (`dialects/<lang>`)、C# `partial class` 雙層分部聚合、單檔大綱 (`yscb ast outline`) 與呼叫拓撲 (`yscb ast callers/callees/impact`) 統一由 [`module:ast`](../ast/README.md) 負責；`knowledge-db` 直接讀取 `ASTEngine.ensure_jit_synced()` 產出之 `ASTSnapshot` 與 `CallGraphIndex`，**零重複 AST 解析**。
- **跨模組空間協同與顯式 Opt-in 檢索加權 (`core.space` & `space_weights`)**：空間目錄幾何統一委由微內核 `core.space` (`contributes/core.json` 與 `config/core/contribute.json`) 雙軌聚合；`knowledge-db` 則採**顯式 Opt-in 權重制**，唯有於 `space_weights`（如 `source: 1.0`, `docs: 1.2`, `plans: 0.85`）明確宣告權重的空間才會納入資料庫索引與檢索（未宣告權重的空間，如純雲端同步空間，自動排除於資料庫索引之外）。
- **全空間聯集處理 (Union Scope)**：無單一 `default_space` 強制約定，全系統以所有有效空間之聯集作為全域處理範圍，並對重疊實體檔案進行 100% 唯一解析去重。
- **`YFP2` + `acked_ast_generation` 雙水位線與受管雙階段背景 Worker (`knowledge-db-worker`)**：透過 `core.space.consume_diff(consumer_id="knowledge-db")` 與 `InvertedIndex.acked_ast_generation` 雙重水位線感知變更；常駐背景服務 `KnowledgeDBServiceWorker` (`knowledge-db-worker`) 運行於 `BaseServiceWorker` 受管背景執行緒中，具備明確五態狀態機（`STARTING`, `UPDATING`, `READY`, `DEGRADED_OFFLINE`, `STOPPED`）與 `core.log` 背景日誌流隔離：
  - **Stage 1 快篩同步**：秒級更新 AST/BM25 倒排索引並立即釋放 `_index_lock`。
  - **Stage 2 向量補齊與受管背景自動下載**：在釋放 `_index_lock` 後，若 `EmbeddingService.has_local_model()` 為 `False` 則於受管背景執行緒自動拉取模型（離線或失敗時切換為 `DEGRADED_OFFLINE` 並設 60 秒重試冷卻），下載就緒後以微批次補齊向量並轉為 `READY`；當 `unified.index.bin.gz` 已存在且背景 Worker 忙碌或無本地模型時，前台 `search` 採非阻塞快篩路徑（`< 1ms` 瞬時回傳純 BM25 結果），絕不等待 `_index_lock` 或網路下載。手动 `yscb kdb model download` 標註 `server_compatible: false`，強制於獨立冷啟動進程執行。
- **雙軌 RRF 複合檢索與平滑降級 (Hybrid Search)**：結合中英混排分詞 (`MultilingualTokenizer`)、多欄位加權 BM25 與 FastEmbed ONNX 離線向量推論（動態維度解析，預設 `BAAI/bge-small-zh-v1.5` 為 `512-dim`），透過倒數排名融合 (RRF $k=60$) 精準召回，並具備 100% 剛性平滑降級純 BM25 保證。

---

## 2. 意圖導向三級複雜度矩陣 (3-Tier View Matrix)

本模組檢索與拓撲指令（`search`、`callers`、`callees`、`impact`）全面支援三級意圖複雜度與高密度 JSON 輸出（搭配 8,000 字元動態預算階梯衰減與 `UniversalRedundancyFilter` 切片去重）：

| 複雜度層級 (Tier) | 觸發旗標 | 適用情境與終端輸出 | Agent 推薦 `--json` 格式 |
| :--- | :---: | :--- | :--- |
| **Tier 1: 自適應大綱 (Auto / Simple)**<br/>*(預設模式)* | *(無旗標: `auto`)*<br/>`--simple` | 預設採相對路徑 `path:Lstart-end`（省去 `file:///` 絕對路徑重複膨脹，可加 `--file-uri` 顯式開啟）；單檔單命中自動壓縮為單行，多命中父子節點消滅重複檔名。 | **超緊湊 JSON** (`--json`)：<br/>預設省略 `file_uri` 與空字串欄位，Token 消耗最小化。 |
| **Tier 2: 內文瀏覽 (Preview)**<br/>*(Agent 探索首選)* | `-s` / `--snippet`<br/>`--preview` | 一步到位取得帶行號之 AST 代碼切片、簽名與 Docstrings。 | **高密度業務 JSON** (`--json -s`)：<br/>剪除雜湊 ID 與除錯欄位，資訊密度高達 86%+。 |
| **Tier 3: 全量除錯 (Detail)** | `-d` / `--detail`<br/>`--verbose` | 包含 40 碼 SHA-1、BM25 分詞矩陣 (`matched_terms`) 與全量屬性。 | **全量除錯 JSON** (`--json -d`)：<br/>保留完整 Schema 與 2-space 縮排。 |

---

## 3. CLI 快速上手 (Quick Start)

`knowledge-db` 專注於語意與全文檢索指令集（`status`, `index`, `search`, `clean`, `model`）；單檔結構大綱（`outline`）與靜態調用拓撲（`callers`, `callees`, `impact`）正統入口位於 [`yscb ast`](../ast/README.md)（`knowledge-db` 亦保留向下相容轉發）：

```bash
# 1. 查看所有已註冊空間、快取、索引狀態與 acked_ast_generation 水位 (支援頂層短別名 kdb)
python yscb.py kdb status
python yscb.py knowledge-db status
python yscb.py knowledge-db status --scan

# 2. 一鍵全管線索引建置 (消費 ASTSnapshot -> 倒排索引 -> 向量特徵)，支援導出 Bundle
python yscb.py knowledge-db index --all
python yscb.py knowledge-db index --export ./output/project.bundle.json

# 3. 向量推論模型生命週期管理 (狀態查詢與顯式預載)
python yscb.py knowledge-db model status
python yscb.py knowledge-db model download

# 4. 執行 BM25 + 向量雙軌複合檢索 (預設為 Auto 自適應大綱與相對路徑，支援 --file-uri 顯式附帶超連結)
python yscb.py kdb search PIDController
python yscb.py kdb search PIDController --file-uri
python yscb.py knowledge-db search "狀態機更新" --kind=class --limit=5

# 5. 代碼/文檔分流檢索 (--ftype 與 -s / --snippet 預覽代碼切片與 Docstring 摘要)
python yscb.py knowledge-db search "PIDController" --ftype=py --json -s
python yscb.py knowledge-db search "開發規範" --ftype=md --json -s

# 6. 單檔結構大綱與跨檔案呼叫拓撲查詢 (透過 Layer 2 module:ast)
python yscb.py ast outline yscb.py --public --methods
python yscb.py ast callers "InvertedIndex.load_binary" --json -s
python yscb.py ast callees "KnowledgeEngine.build_unified_index" --json -s
python yscb.py ast impact "InvertedIndex.patch_incremental" --depth=2 --json

# 7. 清理特定或全空間之倒排索引與向量快取
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
results = engine.search("PID 控制器速度輸出", limit=5, snippet=True)
for res in results:
    sym = res.symbol
    print(f"[{res.score:.2f}] {sym.kind.upper()}: {sym.name} ({sym.file_path}:{sym.line_number})")
    print(f"  簽名: {sym.signature}")
    print(f"  命中: {', '.join(res.matched_terms)}")

# 3. 調用圖譜與影響面查詢 (輕量 JIT 解耦，不觸發向量推論)
callers = engine.callers("InvertedIndex.load_binary", snippet=True)
callees = engine.callees("IndexingPipeline.build_unified_index", snippet=True)
impact = engine.impact("UnifiedSymbol", depth=2)

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
- 🔍 **語意檢索引擎指南**：[retrieval.md](./retrieval.md)
- 🕸️ **符號調用圖譜與引用拓撲**：[call_graph_and_reference_index.md](./call_graph_and_reference_index.md)
- ⚡ **細粒度增量熱重載與常駐 Worker**：[incremental_hot_reload.md](./incremental_hot_reload.md)
- 🛡️ **設計決策與工程妥協手冊**：[DESIGN_NOTES.md](./DESIGN_NOTES.md)
- ⚙️ **Server 常駐與熱重載服務專題**：[雙軌熱重載與常駐服務架構專題](../server/hot_reload_and_services.md)

---

## 6. 組態配置與向量環境參考 (`KnowledgeDBConfig` & Environment)

### 6.1 雙層運作組態設定 (`config.project.json` / `config.local.json`)

本模組運作組態遵循 YSCB 2x2 組態矩陣，位於 `config://knowledge-db/config.project.json`（團隊共享）與 `config.local://knowledge-db/config.local.json`（本機覆蓋，優先權高於 project），可透過 `python yscb.py config set knowledge-db <key> <val>` 進行設定：

| 設定鍵值 (Key) | 預設值 (Default) | 型態 | 說明 |
| :--- | :--- | :---: | :--- |
| **`enable_vector_search`** | `true` | `bool` | 是否啟用 FastEmbed 向量語意檢索與特徵提取。設為 `false` 則跳過向量化並強制使用純 BM25 詞彙檢索模式。 |
| **`embedding_model`** | `"BAAI/bge-small-zh-v1.5"` | `str` | 指定 FastEmbed ONNX 嵌入模型名稱（預設模型為 `512-dim`，支援中英多語言）。 |
| **`jit_vector_timeout_ms`** | `3000` | `int` | 向量容差等待與 JIT 熔斷超時上限（毫秒，向下相容舊鍵 `jit_vector_timeout_seconds`）。當背景 Worker 已運行時間 `elapsed_ms < jit_vector_timeout_ms` 時最多等待剩餘時間 `timeout_ms - elapsed_ms`；若 `elapsed_ms >= jit_vector_timeout_ms` 則等待 0ms 瞬時降級純 BM25 並印出 `[後台向量資料庫更新中，已暫時降級為純 BM25 搜尋]`。無 Server 環境時則作為前台 10 符號探針熔斷上限。 |
| **`vector_batch_size`** | `32` | `int` | 背景 `knowledge-db-worker` Stage 2 微批次向量差集自癒之單批符號數量。 |
| **`max_threads`** | `"auto"` | `str` / `int` | 向量推論與 ONNX Runtime 執行緒上限。預設 `"auto"` 自動限制為 `min(2, max(1, cpu_count // 2))` 以防止 CPU 排程飢餓。 |

### 6.2 向量嵌入與作業系統環境注意事項

- **動態維度解析 (Dynamic Dimension Resolution)**：`EmbeddingService` 徹底淘汰硬編碼維度常數，統一以實際加載之 FastEmbed 模型實例原生屬性 (`model.embedding_size`) 作為唯一真理來源（預設 `BAAI/bge-small-zh-v1.5` 為 `512-dim`），保證二進位快取比對與檢索維度 100% 相容。
- **離線權重探針先行 (`Probe First`)**：初始化時先以純本機路徑探測 `.onnx` 權重是否存在；若尚未執行 `model download`，絕不發起任何未認證網路請求，立即平滑退回純 BM25 檢索並於 `stderr` 輸出 `[GUARD]` 指引。
- **Windows / Anaconda 環境需求**：ONNX Runtime 依賴 Microsoft Visual C++ 2015-2022 執行期（VC++ runtime $\ge 14.4x$）。若遇 `WinError 1114`（動態連結庫初始化例行程序失敗），可透過 `conda install -c conda-forge vc14_runtime` 或安裝官方最新 VC++ Redistributable 修復。
- **符號連結權限警告抑制**：系統已預設配置 `HF_HUB_DISABLE_SYMLINKS_WARNING=1`，防止在 Windows 非管理員模式下觸發 Hugging Face Hub 的 `WinError 1314` 符號連結警告並保護 `--json` 通道純淨。

