# 需求討論說明書 (Semantic Requirements Discovery)

> 功能名稱：sub_03_knowledge_db_cli_consolidation_and_model_management  
> 建立日期：2026-09-14  
> 所屬主計畫：2026_09_14_0455_downstream_feedback_remediation  
> 狀態：Draft  
> 計畫類型：Refactor  
> 模板版本：v1.2  

---

## 1. 使用者原始需求與意圖 (User Intent)

- **原始陳述**：
  - 採納方案 A，為向量模型建立專屬 `model` 指令群組。
  - 整併部分性質重複的 CLI 指令：`bundle` 與 `index` 性質重複、`scan` 與 `status` 性質重複。將指令整理並合併，內部應由 config 自動降級，而非分成一大堆不同指令。
  - 不保留向下相容性，直接徹底移除多餘指令（`scan` 與 `bundle`），追求純粹性。
  - 當發生 `[knowledge-db:embedding] Vector model not found locally. Gracefully fallback to BM25.` 時，代表當前組態必定開啟了向量檢索，故額外輸出剛性引導：`[GUARD] 如果你是 AI Agent，必須立即暫停當前作業，並向開發者提問：要執行 model download 或是於 config 中關閉向量檢索？`
- **核心目標**：
  1. **CLI 指令整併與架構收斂**：
     - 徹底移除 `scan` 與 `bundle` 頂層指令，不留歷史相容包袱。
     - `status` 整併指紋比對功能（支援 `--scan` / `--diff` 檢視檔案增量狀態）。
     - `index` 整併為全管線一鍵索引（內部自動執行增量掃描 -> AST 語意符號提取 -> 倒排索引 -> 向量嵌入），並支援 `--export <path>` 導出語意 Bundle。
  2. **獨立 `model` 生命週期管理**：
     - 新增 `knowledge-db model status`：檢視本地模型權重就緒狀態、快取目錄、模型名稱與向量維度。
     - 新增 `knowledge-db model download`：顯式下載或預熱向量模型權重（支援 `--force` 強制刷新）。
  3. **平滑靜默降級與 AI Agent 剛性防呆**：
     - 實作本機模型權重存在性探針，模型未下載時**絕不發起任何未認證網路連線 (HF Hub)**，平滑降級為純 BM25 檢索。
     - 若組態開啟向量檢索但本機權重遺失，於 stderr 輸出 `[GUARD]` 提示，強制要求 AI Agent 停止作業並向開發者確認。
- **邊界排除 (Explicitly Excluded)**：
  - 不保留 `scan` 與 `bundle` 向下相容轉發或別名，直接移除。
  - 不變更既有查詢指令之核心語意（`search`, `callers`, `callees`, `impact`, `clean` 維持）。

---

## 2. 核心討論與決策紀錄 (Discussion & Decisions)

- **[P00:DR-01] 零相容包袱之指令收斂**：徹底自 `contributes/core.json` 與 `scripts/cli.py` 移除頂層 `scan` 與 `bundle` 指令；將其底層能力完全封裝入 `status`（狀態與差異掃描）與 `index`（一鍵全管線索引建置）。
- **[P00:DR-02] 獨立 Model 管理指令群**：新增 `model` 作為子指令群組，下設 `status` 與 `download`，徹底切分「模型權重生命週期」與「日常檢索查詢」，杜絕運行期未認證下載帶來的網路卡頓與 ONNX Runtime 例外。
- **[P00:DR-03] 本地探針先行與 Agent 剛性防呆攔截**：於 `EmbeddingService` 實作權重檔案本機完整性檢驗（檢查 ONNX 權重檔與 tokenizer 檔案是否存在於快取目錄）；若不存在則安全標記為不可用，完全跳過 `TextEmbedding` 網路建構，並輸出 `[GUARD]` 剛性提示規範引導 Agent。

---

## 3. 開放議題與確認紀錄

- [x] CLI 整併方案拍板定案（收斂為 `status`, `index`, `search`, `callers`, `callees`, `impact`, `clean`, `model` 共 8 大指令）。
- [x] 確認不保留 `scan` 與 `bundle` 向下相容性。
- [x] 確認剛性 Agent 防呆文字與行為。
