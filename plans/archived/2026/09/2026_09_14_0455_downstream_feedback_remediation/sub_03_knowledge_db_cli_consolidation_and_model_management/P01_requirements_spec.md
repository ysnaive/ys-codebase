# 需求規格說明書 (Requirements Specification)

> 功能名稱：sub_03_knowledge_db_cli_consolidation_and_model_management  
> 建立日期：2026-09-14  
> 所屬主計畫：2026_09_14_0455_downstream_feedback_remediation  
> 狀態：Draft  
> 依據 P00：[P00_discuss.md](./P00_discuss.md)  
> 模板版本：v1.5  

---

## 1. 功能需求清單 (Functional Requirements)

| 需求編號 | 需求名稱 | 詳細規格描述 | 優先級 | 對應 P00 語意 |
| :--- | :--- | :--- | :---: | :--- |
| **FR-01** | 徹底移除多餘頂層指令 | 從 `contributes/core.json` 與 `scripts/cli.py` 刪除 `scan` 與 `bundle`，零向下相容轉發與別名。 | P0 | [P00:DR-01] |
| **FR-02** | `status` 增量指紋比對整合 | `status` 支援 `--scan` / `--diff` 選項，執行空間檔案指紋掃描並印出變更統計（Added/Modified/Deleted/Unchanged）。 | P1 | [P00:DR-01] |
| **FR-03** | `index` 全管線一鍵索引 | `index` 自動串接：增量指紋掃描 -> AST 語意符號提取 (Bundle) -> 倒排索引 -> 向量特徵生成；支援 `--export <path>` 單純導出 Bundle。 | P0 | [P00:DR-01] |
| **FR-04** | `model` 專屬管理指令群組 | 新增 `knowledge-db model` 子指令樹：<br/>- `model status`：檢視本地權重就緒狀態、快取路徑、模型名稱與嵌入維度。<br/>- `model download`：顯式下載或預熱向量模型權重（支援 `--force`）。 | P0 | [P00:DR-02] |
| **FR-05** | 本地模型探針與平滑靜默降級 | `search` 啟動時透過本地探針檢查權重檔案完整性；未就緒時**絕不發起任何 HF Hub 未認證連線**，立即平滑退回純 BM25 詞彙檢索。 | P0 | [P00:DR-03] |
| **FR-06** | AI Agent 剛性防呆引導 | 當檢索降級觸發且組態中 `enable_vector_search: true` 時，於 stderr 輸出 `[GUARD]` 提示，強制要求 AI Agent 停止當前作業並向開發者確認。 | P0 | [P00:DR-03] |

---

## 2. 邊界與異常情況 (Edge Cases & Failure Modes)

| 邊界編號 | 情境說明 | 預期防禦與處理行為 |
| :--- | :--- | :--- |
| **EC-01** | 本地模型快取目錄不存在或檔案不完整 | 探針判定為未就緒，完全跳過 `TextEmbedding` 實例化，防止觸發網路請求與警告。 |
| **EC-02** | 離線環境或無外網連線下執行檢索 | 檢索不拋出任何網路逾時或 ONNX Runtime 例外，正常回傳 BM25 檢索結果。 |
| **EC-03** | 執行 `model download` 遇網路中斷或下載失敗 | 捕獲底層例外，輸出友善錯誤訊息並指示檢查網路連線或配置代理。 |
| **EC-04** | `index --export <path>` 指定不存在的父目錄 | 自動建立所需父目錄並將 Bundle JSON 正確寫入。 |
| **EC-05** | 使用者執行已被刪除的舊指令 (`scan`/`bundle`) | 核心分發器輸出未知子指令錯誤提示，引導使用 `status --scan` 或 `index`。 |

---

## 3. 非功能需求 (Non-Functional Requirements)

| 需求編號 | 類別 | 指標與量化約束 |
| :--- | :--- | :--- |
| **NFR-01** | 檢索響應時間 | 向量未就緒降級至純 BM25 時，檢索延遲保持在 $< 500\text{ms}$，無卡頓與等待。 |
| **NFR-02** | 靜態合規與測試覆蓋 | `dev check knowledge-db` 0 警告 0 錯誤；單元測試覆蓋新指令與降級情境，100% 通過。 |
| **NFR-03** | 架構邊界純粹性 | 8 大指令職責正交，底層管線生命週期高內聚封裝。 |

---

## 4. 知識庫與踩坑紀錄查閱 (Known Gotchas & CAUTIONs)

- **`[!NOTE]`**
  - FastEmbed 在未指定本機路徑或模型權重遺失時，預設會向 Hugging Face Hub 發送遠端請求，觸發未認證警示與網路阻塞；本規格強制以本機檔案探針前置攔截，杜絕任何隱式網路調用。
  - 徹底移除 `scan` 與 `bundle` 頂層指令後，既有調用該指令之外部調用需遷移為 `status --scan` 或 `index`。

---

## 5. 階段決策紀錄 (Decisions)

- **[P01:DR-01]** 確立 8 大指令架構矩陣：`status`、`index`、`search`、`callers`、`callees`、`impact`、`clean`、`model`。
- **[P01:DR-02]** 本地探針採用路徑與權重檔案特徵檢測（檢查快取目錄中特定模型資料夾），杜絕依賴網路的第三方類別初始探測。
