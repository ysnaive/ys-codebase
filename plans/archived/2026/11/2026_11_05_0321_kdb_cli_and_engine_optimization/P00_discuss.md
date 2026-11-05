# 需求討論說明書 (Semantic Requirements Discovery)

> 功能名稱：2026_11_05_0321_kdb_cli_and_engine_optimization  
> 建立日期：2026-11-05  
> 所屬主計畫：無  
> 狀態：Discussing  
> 模型：Unknown  
> 計畫類型：Performance  
> 模板版本：v1.2  

---

## 1. 使用者原始需求與意圖 (User Intent)

- **原始陳述**：發現本專案中為了訊息齊全，CLI 有越來越長的趨勢，其中最重的依然是 `knowledge-db`，且檔案路徑佔用了很大的部分；要求開啟一份 `kdb` 優化調研，包含上述 CLI 與檔案路徑膨脹問題，並全面研究 `knowledge-db` 是否還有其他可優化之處。
- **核心目標**：
  1. 量化剖析 `knowledge-db` CLI 輸出中檔案路徑與 `file:///...` URI 的真實字元／Token 佔比，提出兼顧「極致精簡、同名檔案高辨識度、IDE 點擊跳轉與 Agent 直接讀檔」的路徑與呈現層瘦身方案（`OPT-01` ～ `OPT-04`）。
  2. 深入審查 `knowledge-db` 檢索與索引核心管線（`pipeline.py`、`retrieval.py`、`engine.py`、`hybrid.py`、`embedding.py`），挖掘消除無效 I/O、加速索引載入與降低記憶體佔用的高價值優化點（`OPT-05` ～ `OPT-08`）。
- **既有組件復用與查重 (Reuse Discovery)**：
  - 復用 `ResultFormatter.normalize_workspace_path()` 既有專案相對路徑正規化邏輯作為預設檔案顯示格式。
  - 復用 `ast/scripts/cli.py` 在 `simple` JSON 模式省略冗餘 `file_uri` 之設計慣例。
  - 復用 `FingerprintScanner.snapshot_mgr.load_state()` 已載入之 `snap_state.files` 避免 `status()` 重複走訪磁碟。
- **邊界排除 (Explicitly Excluded)**：
  - 不改變 BM25 與向量 RRF 混合檢索之排序演算法與評分數學模型，確保檢索召回率與排名 100% 等價。
- **架構影響範圍**：`ys_codebase/source/knowledge-db/`（含 `knowledge_db/{formatter,pipeline,retrieval,engine}.py`、`scripts/cli.py`、`contributes/core.json` 及 `tests/test_cli.py`），並可選擇性同步對齊 `ys_codebase/source/ast/ast_engine/formatter.py`。

---

## 2. 核心討論與決策紀錄 (Discussion & Decisions)

- **[P00:DR-01] 全面盤點 `knowledge-db` 呈現層與核心引擎之 8 大優化標的（`OPT-01` ～ `OPT-08`）**：
  - 已完成 `R01_kdb_cli_and_engine_optimization.md` 實證調研，確立 **維度 A（CLI 與路徑瘦身：`OPT-01` 預設改用相對路徑 `rel_path:Lxx-yy`、`OPT-02` 消除子項目重複路徑、`OPT-03` 精簡 JSON `file_uri` 與空欄位、`OPT-04` 新增 `kdb` 模組別名）** 與 **維度 B（核心管線加速：`OPT-05` 無變更熱路徑免反序列化 `ASTSnapshot`+`CallGraphIndex`、`OPT-06` 自適應斷層過濾前移消除 70%+ 無效切片讀檔、`OPT-07` `InvertedIndex` 剔除 `Posting` 零值欄位與字典轉換迴圈、`OPT-08` `status()` 免磁碟遍歷）**。

- **[P00:DR-02] 駁回 CLI 輸出端「盲碼 `0..n` + `kdb id=n` 反查」，將整數唯一碼映射下沉至 `OPT-07` `InvertedIndex` 內部儲存**：
  - 經量化評估，若在 CLI 輸出端以唯一碼 `0..n` 隱藏檔案路徑並要求執行 `kdb id=n` 反查，將破壞 `knowledge-db-search` 三階段漏斗直接呼叫宿主原生讀檔工具（`view_file`）之零摩擦鏈路（省 ~15 Output Tokens 卻需多花 1 個 Tool-Call Turn 重送數萬 Context Tokens），並喪失從路徑一眼區分 `source/`、`tests/`、`docs/` 與 `plans/archived/` 的語意篩選能力。
  - 採納 `OPT-01 + OPT-02`（父節點印 1 次專案相對路徑、子節點僅印行號）即可在不損失任何語意與可讀性的前提下砍除 **84.9%** 的路徑字元（4 檔實測 `1,485 -> 224 chars`）；同時將「`0, 1, 2 ... n` 唯一碼映射表」落實於 `OPT-07` 的 `InvertedIndex` 內部儲存，消除 75,000+ 個 `Posting` 節點的長路徑字串重複。

- **[P00:DR-03] 採納雙路盲眼子代理反向設計審計之 8 項防回歸修正處方**：
  - 經盲眼子代理對照第一手源碼與測試集審查，成功攔截：`OPT-01` 預設 `use_basename=True` 退化、`-md` 超連結契約與 `core.json` `"format"` 互斥群組衝突；`OPT-02` `cli.py:L321` 死代碼分支與 `--simple` `"清單模式"` 測試斷言衝突；`OPT-03` `detail` JSON 固定 Schema 保證；`OPT-04` `agents-workflow` `_trace_parser.py` 漏認 `kdb` 短別名引發假陽性盲讀警告；`OPT-05` Lazy Graph Loading（免載入 `unified.graph.bin.gz`）與 `mtime_ns` 綁定之世代讀取；`OPT-06` `adaptive_limit=False` 預設保護 SDK `limit` 與 `--json` 契約；`OPT-07` `Posting` `__slots__` 相容、`SparseFieldFreqs`、`patch_incremental` 不平移 Free-List 回收與 `VectorIndex` 字串 ID 邊界；以及 `OPT-08` `SnapshotState.entries`（過濾 `not fp.is_deleted`）取代不存在之 `.files` 屬性。

---

## 3. 開放議題與確認紀錄

- **待確認事項**：請開發者審閱 `R01_kdb_cli_and_engine_optimization.md` 之 8 項優化方案，確認是否全數納入並選擇流轉出口（① 立即實作、② 路線圖/TODO 儲備、或 ③ 放棄結案），以及是否同步將 `OPT-01` 相對路徑格式套用至 `module:ast`。
