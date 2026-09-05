# 需求討論說明書 (Semantic Requirements Discovery)

> 功能名稱：knowledge_db_cli_ux_flow_refactor_and_optimization  
> 建立日期：2026-09-05  
> 所屬主計畫：2026_09_05_1025_knowledge_db_refactor  
> 狀態：Confirmed  
> 計畫類型：Refactor  
> 模板版本：v1.2  

---

## 1. 使用者原始需求與意圖 (User Intent)

- **原始陳述**：
  > 首先，你提到的問題都要處理，但 (2.) 中的熱更新提示還是要有，以下為流程重構：
  > - local 級 config 添加是否啟用向量語意搜尋的選項
  > - JIT 熱更新添加臨界值評估，現有架構已存在自動降級，僅 BM25 搜尋模式，評估當向量化時長需要超過 5 秒時，僅做 BM25 熱更新 + 退回到 BM25 模式，並丟出提示，向量索引未建立/變動過大，呼叫 <cli> 重建/更新索引，或是於 <config> 關閉向量語意搜尋
  > - 重建/更新索引在熱更新情況下不須特別顯示進度，提示有做這件事就好，但是在單獨調用時需顯示進度
- **核心目標**：
  1. **Config 級向量搜尋開關**：於 YSCB local-level config 支援 `knowledge-db.enable_vector_search`（預設依環境自動判定或啟用），提供零侵入式靈活切換純 BM25 模式能力。
  2. **JIT 熱更新動態探針與可配置臨界值熔斷**：重構熱修補流程，支援 `knowledge-db.jit_vector_timeout_seconds`（預設 5.0 秒，可於 Local Config 靈活自訂）。當待向量化符號 $> 10$ 個時，先執行 10 個符號之即時推論探針動態換算總耗時；若預估超過臨界值，主動熔斷後續向量推論，僅熱更新 BM25 與調用圖譜，本次檢索安全降級為 BM25 模式並輸出引導提示。
  3. **分流進度與耗時反饋機制**：JIT 背景熱更新保持極簡單行提醒；手動調用 `knowledge-db index` 時提供分階段進度指示（AST Parsing $\rightarrow$ BM25 $\rightarrow$ CallGraph $\rightarrow$ Vector $\rightarrow$ Save）與各階段耗時摘要。
  4. **全方位 CLI 痛點徹底修復**：
     - `knowledge-db --help` 補齊遺漏之 `index` 指令與參數說明。
     - `status` 指令修正倒排索引判定邏輯（精準感知 `unified.index.bin.gz`）。
     - 屏蔽 Hugging Face Hub 未認證警告（`Warning: You are sending unauthenticated requests...`），杜絕終端雜訊。
     - 保證 `--json` 模式下 stdout 100% 機器可讀性與純淨度。
     - 終端色彩階層美化（支援 ANSI 著色，相容 `NO_COLOR` 與非 TTY 管道自動去色）。
  5. **Project / Local 級模型自訂配置**：支援 `knowledge-db.embedding_model`，支援專案與本機層級自訂向量模型（預設為 `BAAI/bge-small-zh-v1.5`），並提供模型維度自動適配與模型切換時的快取失效防呆。
  6. **CPU 執行緒防排程飢餓保護可配置化**：支援 `knowledge-db.max_threads`（預設 `"auto"`，自動採用主機核心數之一半 `max(1, cpu_count // 2)`；亦支援手動指定整數上限），徹底拔除原本硬編碼 `min(2, ...)` 的吞吐量枷鎖，並保護系統不發生 100% 核心飽和。
- **邊界排除 (Explicitly Excluded)**：
  - 不修改底層 Tree-sitter AST 解析規則與 S-Expression 宣告。
  - 不變更既有 NetworkX 調用圖譜資料結構與核心演算法。
  - 不在 JIT 搜尋請求阻塞執行超過組態設定臨界值的重型向量推論。

---

## 2. 核心討論與決策紀錄 (Discussion & Decisions)

- **[P00:DR-01] Config 命名與層級繼承規範**：
  - 開放四組核心組態鍵：
    1. `knowledge-db.enable_vector_search` (boolean, 預設 `True`)
    2. `knowledge-db.embedding_model` (string, 預設 `"BAAI/bge-small-zh-v1.5"`)
    3. `knowledge-db.jit_vector_timeout_seconds` (float, 預設 `5.0`)
    4. `knowledge-db.max_threads` (string \| int, 預設 `"auto"`)
  - 支援 `python yscb.py config set knowledge-db <key> <value> [--local]`。
  - 讀取時嚴格遵循 `yscb.config.local.json` $\rightarrow$ `yscb.config.json` $\rightarrow$ 預設常數優先級。
- **[P00:DR-02] JIT 動態探針 (Dynamic Probe) 與臨界值熔斷機制**：
  - 若待向量化符號 $N \le 10$，直接推論完成熱修補。
  - 若 $N > 10$，先執行首批 10 個符號作為動態探針，計算單符號實測延遲 $t_{\text{unit}} = t_{\text{probe}} / 10$，並預估總耗時 $t_{\text{total}} = t_{\text{probe}} + (N - 10) \times t_{\text{unit}}$。
  - 當 $t_{\text{total}} > \text{timeout}$（預設 5.0s，由 local config 決定）或向量快取遺失時觸發熔斷：
    - 中斷剩餘向量推論（探針耗時僅數百毫秒，前置推論不浪費），熱修補管線完成 BM25 倒排索引與調用圖譜更新。
    - 檢索引擎標記 `vector_degraded=True` 並退回純 BM25 檢索。
    - 輸出引導提示：`[*] Notice: Vector update estimated at {t_total:.1f}s (probed {t_unit*1000:.0f}ms/sym) exceeding limit ({timeout}s). Fallen back to BM25. Run 'python yscb.py knowledge-db index' to rebuild vectors.`
- **[P00:DR-03] 雙軌進度呈現架構 (Dual-Track Progress Protocol)**：
  - 在 `Pipeline` 導入回調或模式標記 `interactive: bool`：
    - `interactive=False` (JIT 觸發)：保留輕量單行 `[knowledge-db:auto-rebuild] Index updated in Xms.`。
    - `interactive=True` (手動執行 `index`)：輸出 5 階段進度指示與耗時報表。
- **[P00:DR-04] Hugging Face Hub 警告收斂方式**：
  - 於 `embedding.py` 初始化前設定環境變數 `HF_HUB_DISABLE_IMPLICIT_TOKEN=1` 與 `HF_HUB_ENABLE_HF_TRANSFER=0`，並針對 `huggingface_hub` 與 `transformers` 抑制 warning，消除終端未認證請求雜訊。
- **[P00:DR-05] 嵌入模型自訂配置與維度/快取失效防呆**：
  - 組態鍵：`knowledge-db.embedding_model` (string)。
  - 繼承順序：`Local Config` $\rightarrow$ `Project Config` $\rightarrow$ `"BAAI/bge-small-zh-v1.5"`。
  - 合法性驗證：透過 `TextEmbedding.list_supported_models()` 比對，非法時提供清晰候選列表提示。
  - 矩陣維度守門：`VectorIndex` 保存 `model_name` 與 `dim`；若當前配置模型與快取不符，自動標記快取失效並退回純 BM25，提示執行 `index` 重建。
- **[P00:DR-06] CPU 調用保護計算與注入規範**：
  - 若 `max_threads` 為 `"auto"`，動態解析為 $\max(1, \text{cpu\_count} // 2)$。
  - 若為手動整數，防禦性截斷於 $[1, \text{cpu\_count}]$ 區間。
  - 動態同步注入 `OMP_NUM_THREADS` 與 `ONNXRUNTIME_INTRA_OP_NUM_THREADS`，並於 `TextEmbedding(..., threads=...)` 傳入。

---

## 3. 開放議題與確認紀錄

- [x] JIT 熱更新是否保留文字提示？（是，保留輕量單行提示）
- [x] 是否支援關閉向量搜尋？（是，透過 local 級 config 支援）
- [x] 索引進度顯示何時觸發？（手動執行 index 時詳細顯示，JIT 時僅簡要提示）
- [x] 是否納入說明文件與 status 判定修復？（是，全量納入 sub_06）
- [x] 是否支援 Project/Local 級模型自訂配置？（是，定錨 [P00:DR-05]）
