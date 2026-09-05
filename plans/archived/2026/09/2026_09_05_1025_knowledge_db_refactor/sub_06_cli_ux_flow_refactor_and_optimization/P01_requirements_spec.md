# 需求規格說明書 (Requirements Specification)

> 功能名稱：knowledge_db_cli_ux_flow_refactor_and_optimization  
> 建立日期：2026-09-05  
> 所屬主計畫：2026_09_05_1025_knowledge_db_refactor  
> 狀態：Confirmed  
> 依據 P00：[P00_discuss.md](./P00_discuss.md)  
> 模板版本：v1.5  

---

## 1. 功能需求清單 (Functional Requirements)

| 需求編號 | 需求名稱 | 詳細規格描述 | 優先級 | 對應 P00 語意 |
| :--- | :--- | :--- | :---: | :--- |
| **FR-01** | 向量檢索與逾時配置 | 支援於 `yscb.config.local.json` 與 `yscb.config.json` 讀取 `knowledge-db.enable_vector_search` (boolean, 預設 `true`) 與 `knowledge-db.jit_vector_timeout_seconds` (float, 預設 `5.0`)。若開關為 `false`，完全跳過 FastEmbed 初始化與向量計算，預設回退至純 BM25 模式。 | P0 | [P00:DR-01] |
| **FR-02** | 向量模型自訂配置 | 支援透過組態指定 `knowledge-db.embedding_model` (string，預設 `"BAAI/bge-small-zh-v1.5"`)。支援 `TextEmbedding.list_supported_models()` 白名單比對與動態載入。 | P0 | [P00:DR-05] |
| **FR-03** | JIT 動態探針與臨界值熔斷 | 於 JIT 增量熱修補時：若待向量化符號 $N \le 10$，直接推論完成；若 $N > 10$，先執行首批 10 個符號作為動態探針，計算單符號實測延遲並預估總耗時。若預估總耗時超過組態設定之臨界值（預設 5.0s）或向量快取遺失，立即熔斷中斷後續向量推論，完成 BM25 與調用圖譜修補，本次檢索降級為純 BM25 並輸出引導提示。 | P0 | [P00:DR-02] |
| **FR-04** | 雙軌進度呈現機制 | 重構索引管線反饋：JIT 背景熱更新維持極簡單行通知（`[knowledge-db:auto-rebuild] Index updated in Xms.`）；手動調用 `python yscb.py knowledge-db index` 時提供分階段進度指示（AST $\rightarrow$ BM25 $\rightarrow$ CallGraph $\rightarrow$ Vector $\rightarrow$ Save）與精確耗時摘要。 | P0 | [P00:DR-03] |
| **FR-05** | CLI 說明與狀態判定修復 | `knowledge-db --help` 補齊 `index` 子指令與參數說明；`status` 命令重構倒排索引狀態檢驗，精準識別全域聯集快取 `unified.index.bin.gz`，消除「倒排索引: 未建立」之假警報。 | P1 | 痛點修復 (1) |
| **FR-06** | 終端雜訊收斂與 JSON 純淨度 | 於 `EmbeddingService` 屏蔽 Hugging Face Hub 未認證警告（`Warning: You are sending unauthenticated requests...`）；確保在 `--json` 輸出時，所有 JIT 提示與降級警告均導向 `stderr`，`stdout` 嚴格維持 100% 潔淨 JSON。 | P1 | [P00:DR-04] |
| **FR-07** | 終端階層色彩排版美化 | 針對 `search`、`callers`、`callees`、`impact` 與 `status` 導入 ANSI 色彩階層高亮（檔案藍色、CLASS/METHOD 綠黃色、行號青色）；支援 `NO_COLOR` 與非 TTY 管道自動去色。 | P2 | 體驗優化 (4) |
| **FR-08** | CPU 執行緒調用保護配置 | 支援於 `yscb.config.local.json` 與 `yscb.config.json` 讀取 `knowledge-db.max_threads`。預設為 `"auto"`（自動解析為 `max(1, cpu_count // 2)`），亦支援整數指定。動態注入至 `OMP_NUM_THREADS`、`ONNXRUNTIME_INTRA_OP_NUM_THREADS` 與 `TextEmbedding(threads=...)`，廢除硬編碼 `min(2, ...)` 限制。 | P0 | [P00:DR-06] |

---

## 2. 邊界與異常情況 (Edge Cases & Failure Modes)

| 邊界編號 | 情境說明 | 預期防禦與處理行為 |
| :--- | :--- | :--- |
| **EC-01** | Config 中配置不支援或拼錯的模型名稱 | 讀取時進行模型名稱合法性校驗；若未在 FastEmbed 支援列表中，友善提示錯誤並輸出推薦候選模型清單，自動平滑降級為預設模型或純 BM25 模式，嚴禁程式崩潰。 |
| **EC-02** | 切換模型導致既有向量快取維度不符 (Dimension Mismatch) | `VectorIndex` 保存快取時記錄 `model_name` 與 `dim`；載入時若偵測到當前 Config 指定之模型與快取不一致，自動標記向量快取無效並退回純 BM25，輸出警告並建議執行 `knowledge-db index` 重新建置。 |
| **EC-03** | JIT 探針預估超時或大規模代碼變更 | 待向量化符號過多且 10 符號探針推估超過 `jit_vector_timeout_seconds` 時立即中斷；前置探針結果不浪費，BM25 與圖譜在 sub-second 內完成修補，確保檢索立即可用並輸出清晰降級指引。 |
| **EC-04** | `enable_vector_search=false` 關閉情境 | 系統完全不觸發 ONNX Runtime 與 FastEmbed 初始化，完全避免 CPU 向量推論開銷與記憶體占用，直接提供純 BM25 高速檢索。 |
| **EC-05** | 非 TTY 終端或外部腳本管線調用 (`| grep` 或重導向) | 自動偵測 `sys.stdout.isatty()` 或環境變數 `NO_COLOR`，自動禁用所有 ANSI 顏色跳脫碼，保證輸出純文字相容性。 |
| **EC-06** | `--json` 模式下 JIT 觸發熱更新與警告 | 嚴格將 `[knowledge-db:auto-rebuild]` 與警告資訊輸出至 `sys.stderr`，`sys.stdout` 僅輸出 `json.dumps()` 產物，確保外部 JSON Parser 零解析錯誤。 |
| **EC-07** | `max_threads` 配置超出實體 CPU 數或非法型態 | 若設定大於實體核心數則自動截斷至 `os.cpu_count()`；若為負數、0 或無法解析之字串，友善警告並安全降級回退至 `"auto"`。 |

---

## 3. 非功能需求 (Non-Functional Requirements)

| 需求編號 | 類別 | 指標與量化約束 |
| :--- | :--- | :--- |
| **NFR-01** | JIT 感知延遲 | JIT 檔案快照雜湊比對與 5 秒熔斷邊界判定開銷 $\le 60\text{ ms}$。 |
| **NFR-02** | 熔斷檢索時效 | 當觸發 5 秒熔斷降級時，單次 `search` 包含 AST+BM25+圖譜修補與檢索之端到端總耗時 $\le 1.0\text{ s}$。 |
| **NFR-03** | 架構品質守門 | 全生態系既有單元測試（130+ 個案例）100% 通過，0 破壞性變更，符合 YSCB 模組契約。 |

---

## 4. 知識庫與踩坑紀錄查閱 (Known Gotchas & CAUTIONs)

- > [!NOTE]
  > FastEmbed 的 `TextEmbedding.list_supported_models()` 返回字典清單（每個元素含 `model`、`dim`、`description` 等欄位），可直接用於合法性比對與維度預檢。
- > [!WARNING]
  > ONNX Runtime 於不同模型輸出之維度可能不同（例如 384 vs 512 vs 768）。切換模型時若未清空或未標記失效，會導致 `np.dot` 產生 `shapes (N, 512) and (1, 384) not aligned` 致命例外，必須在載入時由 `VectorIndex` 進行元資料綁定防禦 (EC-02)。
- > [!IMPORTANT]
  > Windows 控制台對 ANSI 顏色支援可能因終端而異，需在 CLI 入口點確保 `colorama` 或標準 Windows 虛擬終端跳脫序列 (`ENABLE_VIRTUAL_TERMINAL_PROCESSING`) 啟用或優雅降級為純文字。
