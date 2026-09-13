# 需求討論說明書 (Semantic Requirements Discovery)

> 功能名稱：sub_01_knowledge_db_embedding_and_diagnostics  
> 建立日期：2026-09-13  
> 所屬主計畫：2026_09_13_1648_downstream_feedback_remediation  
> 狀態：Draft  
> 計畫類型：Bug Fix  
> 模板版本：v1.2  

---

## 1. 使用者原始需求與意圖 (User Intent)

- **原始陳述**：
  1. `knowledge-db 1.1.0.0`：向量維度寫死，`DEFAULT_EMBEDDING_DIM = 384`，`EmbeddingService.dimension` 直接回傳 384。但預設模型 `BAAI/bge-small-zh-v1.5` 實際輸出為 512 維。導致 `index --force` 產出真實 512 維向量後，`pipeline.py` 的 `is_compatible_with(model, 384)` 判定不相容，永遠退回純 BM25 模式並反覆提示重建。
  2. FastEmbed 不可用時（如 Anaconda Python 下 VC++ runtime 缺失導致 `WinError 1114`），CLI 僅印出「FastEmbed 不可用，略過」，吞掉底層原生例外訊息，排查困難。
  3. Windows 平台 HuggingFace cache symlink 權限不足 (`WinError 1314`) 印出大段警告，需預設抑制。
  4. `knowledge-db index --help` 傳入時應正確印出說明而非直接執行建索引。
  5. 自動寫入模型名稱未帶前綴時之相容性與 fallback 驗證。
- **核心目標**：
  1. 徹底解除向量維度硬編碼：優先自 FastEmbed 模型清單或模型實際推論維度動態解析維度，確保 `BAAI/bge-small-zh-v1.5` 正確解析為 512 維，快取相容判定通過，恢復向量檢索。
  2. 強化 FastEmbed 載入與推論失敗診斷：記錄並在 CLI / 日誌中暴露原始例外（如 ImportError / WinError），文件指引 VC++ 14.4x 依賴。
  3. 抑制 Windows HuggingFace symlink 警告（設定 `HF_HUB_DISABLE_SYMLINKS_WARNING=1`）。
  4. 確保 CLI 命令列參數（如 `--help`）在 `index` 與其他子指令正確分流。
- **邊界排除 (Explicitly Excluded)**：
  - 本子計畫僅聚焦於 `knowledge-db` 模組內部之向量推論、快取相容、診斷與 CLI 呼叫。
  - 發布提供者、Host self-update、server 模組及 agents-workflow 區塊覆寫問題交由 sub_02~sub_05 處理。

---

## 2. 核心討論與決策紀錄 (Discussion & Decisions)

- **[P00:DR-01] 向量維度動態解析機制**：
  - 放棄單一全域寫死常數 `DEFAULT_EMBEDDING_DIM = 384` 作為所有模型的維度真理。
  - 實作兩段式動態獲取策略：
    1. 靜態字典 / FastEmbed `list_supported_models()`：查詢模型預定義維度（`BAAI/bge-small-zh-v1.5` 為 512，MiniLM 為 384）。
    2. 實例化探針兜底：若不在清單中，模型加載後以單次 dummy 向量或推論輸出 shape 決定真實維度。
    3. Mock 模式支援動態 dim 參數（預設匹配所選模型之維度）。
- **[P00:DR-02] FastEmbed 原生例外與環境警告處置**：
  - `EmbeddingService` 內部保留 `last_error` 欄位記錄載入失敗原因。
  - CLI `knowledge-db index` 與 `search` 在降級時輸出精簡版關鍵錯誤提示（如 `(原因: DLL 載入失敗 WinError 1114，請確認 VC++ 執行期)`），在 `--verbose` / `--debug` 模式輸出完整 traceback。
  - 進入 `embedding.py` 時自動設定 `os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")`，防止 Windows 無符號連結權限時傾倒冗長警告。
- **[P00:DR-03] CLI 說明攔截健全化**：
  - 檢核 `scripts/cli.py` 中 `index` 指令合約，確保 `--help` 由 `HelpRenderer` 或 `dispatcher` 正確優先攔截，避免直接觸發全量檔案掃描。

---

## 3. 開放議題與確認紀錄

- [x] 是否需要支援既有 384 維度舊模型（如 MiniLM-L6-v2）？已確認：動態維度解析應同時支援 384 與 512，相容清單內所有模型。
- [x] 舊的 384 維向量索引快取若與 512 維模型不符時之行為？已確認：應正確提示維度不相容並指引使用者執行 `index --force` 重建，重建後維度為 512 且隨後檢索完全相容。
