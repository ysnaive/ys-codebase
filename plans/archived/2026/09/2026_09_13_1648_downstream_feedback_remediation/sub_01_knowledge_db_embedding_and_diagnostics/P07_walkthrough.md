# 成果展示與結案報告 (Walkthrough)

> 功能名稱：sub_01_knowledge_db_embedding_and_diagnostics  
> 建立日期：2026-09-13  
> 所屬主計畫：2026_09_13_1648_downstream_feedback_remediation  
> 狀態：Completed  
> 模板版本：v1.4  

---

## 1. 變更概述 (Executive Summary)

- **核心功能落地**：
  - 徹底移除 `DEFAULT_EMBEDDING_DIM = 384` 硬編碼常數（零特例），統一以實際加載之 FastEmbed 模型實例原生屬性 `self._model.embedding_size`（512 維）為唯一真理來源 (SSOT)，徹底解決 `BAAI/bge-small-zh-v1.5` 每次皆被誤判為不相容而降級 BM25 的關鍵缺陷。
  - 封裝結構化 `last_error`，於 FastEmbed / ONNX Runtime 載入失敗（如 Anaconda 下 VC++ runtime `WinError 1114`）時，在 CLI 與日誌中輸出精確錯誤類型與診斷訊息，不再靜默吞掉。
  - 預設注入 `HF_HUB_DISABLE_SYMLINKS_WARNING=1`，抑制 Windows 無符號連結權限之大段警告。
  - 排查並確認 Core 派發階段在 1.1.0 已全域攔截 `--help`（實機驗證通過），健全化 `normalize_model_name` 前綴自動補齊。
  - 單元測試全面重構，淘汰過期常數依賴，新增 FT-10~13 測試案例，套件 148/148 100% 通過。

---

## 2. 變更檔案清單 (Changed Files Inventory)

| 檔案路徑 | 變更類型 | 變更說明 |
| :--- | :---: | :--- |
| `source/knowledge-db/knowledge_db/embedding.py` | Modify | 徹底移除 `DEFAULT_EMBEDDING_DIM`，落實以加載模型實例為 SSOT 之動態維度、`last_error` 結構化異常與警告抑制 |
| `source/knowledge-db/knowledge_db/pipeline.py` | Modify | 移除 384 寫死，對齊 `self.embedding_service.dimension`，降級通知注入 `last_error` 與 `--force` 指引 |
| `source/knowledge-db/tests/test_retrieval.py` | Modify | 移除 `DEFAULT_EMBEDDING_DIM` 導入與斷言，新增 FT-10~13 覆蓋動態維度、last_error 與模型補齊 |
| `docs/knowledge-db/README.md` | Modify | 補充第 6 節向量嵌入動態解析、Windows Anaconda VC++ 執行期環境需求說明 |

---

## 3. 測試與品質驗證結果 (Verification & Quality Audit)

- **自動化測試通過率**：`knowledge-db` 全套測試 148/148 100% 通過 (Pass: 148, Fail: 0, Skip: 0)。
- **實機 UX / 人工驗證**：
  - UX-01（向量檢索不再降級）：已確認通過，實機查詢不再觸發維度不相容告警。
  - UX-02（CLI 說明攔截）：已確認通過，`index --help` 由 Core 統一攔截並輸出說明卡。

---

## 4. 知識庫文檔交付驗收對齊表 (Documentation Delivery Audit)

| 維度 | 文件路徑 | 交付狀態 | 驗收重點 |
| :--- | :--- | :---: | :--- |
| **模組手冊** | `docs/knowledge-db/README.md` | [PASS] 已交付 | 補充第 6 節向量嵌入動態解析與環境配置指南 |
| **專題手冊** | `docs/knowledge-db/retrieval.md` | [PASS] 已交付 | 檢索引擎架構與混合檢索機制說明齊備 |
| **設計決策** | `plans/2026_09_13_1648_downstream_feedback_remediation/sub_01_knowledge_db_embedding_and_diagnostics/P02_architecture_plan.md` | [PASS] 已交付 | 登記 [P02:DR-01] 零常數動態維度與 [P02:DR-02] last_error 結構化決策 |
| **發布日誌** | `CHANGELOG.md` | [PASS] 已交付 | 登記本次 sub_01 向量維度動態解析修復摘要 |

---

## 5. 推薦 Commit 訊息 (Conventional Commit Format)

```text
fix(knowledge-db): eliminate DEFAULT_EMBEDDING_DIM and adopt dynamic model dimension

- Remove DEFAULT_EMBEDDING_DIM constant completely from embedding.py and test_retrieval.py
- Use loaded model instance attribute (self._model.embedding_size) as SSOT for dimension
- Suppress HuggingFace Windows symlink warnings via HF_HUB_DISABLE_SYMLINKS_WARNING=1
- Capture and expose structured last_error on FastEmbed load failures
- Add FT-10~13 automated test cases covering dynamic dimension, last_error, and model normalization
- Update docs/knowledge-db/README.md with VC++ runtime requirements and dynamic embedding details
```

---

## 6. 計畫結構合規檢核 (Plan Compliance Verification)

- [x] **結構與註解檢核**：實機執行 `python yscb.py agents-workflow plan verify 2026_09_13_1648_downstream_feedback_remediation` 驗證 100% Passed。
