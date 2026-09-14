# 成果展示與結案報告 (Walkthrough)

> 功能名稱：sub_03_knowledge_db_cli_consolidation_and_model_management  
> 建立日期：2026-09-14  
> 所屬主計畫：2026_09_14_0455_downstream_feedback_remediation  
> 狀態：Completed  
> 模板版本：v1.4  

---

## 1. 變更概述 (Executive Summary)

針對下游專案反饋與過度碎片化之 CLI 指令進行全面收斂與架構重構，達成零相容包袱之 8 大標準指令集與強韌離線降級：
- **8 大標準正交指令集收斂 (SSOT)**：
  - 徹底移除過度碎片化之頂層 `scan` 與 `bundle` 指令。
  - 將增量指紋比對併入 `status`（支援 `status --scan` / `--diff`）。
  - 將語意 Bundle 打包併入 `index`（支援一鍵全管線索引建置與 `index --export <path>` 導出 Bundle）。
  - 確立 8 大標準正交指令：`status`, `index`, `search`, `callers`, `callees`, `impact`, `clean`, `model`。
- **獨立 `model` 向量模型管理群組**：
  - 新增 `knowledge-db model` 子指令樹，支援 `model status`（檢視快取目錄、模型名稱、本地權重存在性與維度）及 `model download`（顯式預載模型）。
- **本地探針先行 (Probe First) 與平滑靜默降級**：
  - `EmbeddingService` 於推論前先以純本機路徑檢查 `.onnx` 權重檔案；未就緒時絕不發起任何 Hugging Face Hub 未認證連線，秒級平滑退回純 BM25 詞彙檢索（延遲 $< 500\text{ms}$），徹底切斷外部網路依賴。
- **AI Agent 剛性防呆引導通道**：
  - 當檢索觸發降級且組態中 `enable_vector_search: true` 時，強制於 `sys.stderr` 輸出剛性引導：
    `[GUARD] 如果你是 AI Agent，必須立即暫停當前作業，並向開發者提問：要執行 model download 或是於 config 中關閉向量檢索？`
    確保檢索輸出 (stdout) 純淨且高優先度阻斷信號傳遞予 Agent。

---

## 2. 變更檔案清單 (Changed Files Inventory)

| 檔案路徑 | 變更類型 | 變更說明 |
| :--- | :---: | :--- |
| `source/knowledge-db/contributes/core.json` | Modify | 徹底移除 `scan` 與 `bundle`；`status` 擴充 `--scan`/`--diff`；`index` 擴充 `--export`；新增 `model` 指令群組。 |
| `source/knowledge-db/scripts/cli.py` | Modify | 移除 `scan`/`bundle` 進入點；重構 `status` 與 `index`；實作 `model`、`model_status`、`model_download` 路由。 |
| `source/knowledge-db/knowledge_db/embedding.py` | Modify | 新增 `is_model_downloaded` 探針、`download_model` 方法；重構 `_init_model` 平滑靜默降級與 `[GUARD]` 引導輸出。 |
| `source/knowledge-db/knowledge_db/engine.py` | Modify | `status` 擴充差異掃描支援；新增 `model_status` 與 `model_download` 門面 SDK 轉發；`build_index` 支援 `export_path`。 |
| `source/knowledge-db/knowledge_db/formatter.py` | Modify | `TerminalStyler` 新增 `bold` 樣式支援。 |
| `source/knowledge-db/tests/test_cli.py` | Modify | 擴充測試套件覆蓋 FT-01 ~ FT-06、ET-01、RT-01，斷言舊指令移除與 8 大標準指令健全運作。 |
| `docs/knowledge-db/README.md` | Modify | 更新 CLI 快速上手章節，對齊 8 大標準指令集與 `model` 指令。 |
| `source/knowledge-db/README.md` | Modify | 更新模組自身 CLI Reference，移除舊 `scan`/`bundle` 並對齊 8 大標準指令。 |
| `docs/knowledge-db/retrieval.md` | Modify | 第 9 章補充本地探針先行、[GUARD] 剛性引導與 `model` CLI 指南。 |
| `docs/knowledge-db/DESIGN_NOTES.md` | Modify | 追加 `[DN-25]` 設計決策記錄：CLI 指令邊界整合、8 大正交指令集與向量模型離線探針先行。 |
| `CHANGELOG.md` | Modify | 專案根目錄追加 `sub_03` 宏觀變更歷史記錄。 |

---

## 3. 測試與品質驗證結果 (Verification & Quality Audit)

- **自動化測試通過率**：157 / 157 PASSED (100% Ready, 0 Failed, 0 Unknown, 0 Skipped)
- **模組靜態合規性**：`python yscb.py dev check knowledge-db` PASSED (0 警告 0 錯誤)
- **實機 UX / 人工驗證**：[跳過/免測]（經開發者指示免測，單元測試覆蓋 FT-01~06 與 ET-01 100% 通過）

---

## 4. 知識庫文檔交付驗收對齊表 (Documentation Delivery Audit)

| 維度 | 文件路徑 | 交付狀態 | 驗收重點 |
| :--- | :--- | :---: | :--- |
| **模組手冊** | `docs/knowledge-db/README.md` | [PASS] 已交付 | 全面更新為 8 大標準指令集與 `model` 管理指引 |
| **專題手冊** | `docs/knowledge-db/retrieval.md` | [PASS] 已交付 | 補充本地探針先行、平滑降級與 [GUARD] 引導機制 |
| **設計決策** | `docs/knowledge-db/DESIGN_NOTES.md` | [PASS] 已交付 | 新增 `[DN-25]` 架構動機、決策與驗證效益 |
| **發布日誌** | `CHANGELOG.md` | [PASS] 已交付 | 於當前 Remediation 主計畫追加 sub_03 高階變更摘要 |

---

## 5. 推薦 Commit 訊息 (Conventional Commit Format)

```text
feat(knowledge-db): consolidate cli commands into 8 standard sets and add local probe fallback

- Remove fragmented top-level commands 'scan' and 'bundle' with zero backward compatibility baggage
- Consolidate fingerprint scanning into 'status --scan' and bundle export into 'index --export <path>'
- Add dedicated 'model' command tree ('model status', 'model download')
- Implement local probe first in EmbeddingService to prevent unauthenticated Hugging Face requests
- Output mandatory [GUARD] directive to stderr when falling back with vector search enabled
- Expand test suite to 157 passing tests and align three-layer documentation
```

---

## 6. 計畫結構合規檢核 (Plan Compliance Verification)

- [x] **結構與註解檢核**：實機執行 `python yscb.py agents-workflow plan verify 2026_09_14_0455_downstream_feedback_remediation/sub_03_knowledge_db_cli_consolidation_and_model_management` 驗證 100% Passed。
