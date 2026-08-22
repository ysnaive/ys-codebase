---
target: "[Namespace/ModuleName]"
doc_type: "changelog"
status: "active"
source_paths:
  - "[src/path/to/relevant_component]"
related_docs:
  - "./README.md"
last_updated: "YYYY-MM-DD"
---

# [模組名稱] — 架構演進歷史 (Architectural Changelog)

> 本文件記錄 `[ModuleName]` 的**重大架構重構與職責重劃歷史**。  
> **注意**：日常微小功能與 Bugfix 請參閱 Dev Plan；本文件**僅記錄架構級重大決策與演進**。

---

## [YYYY-MM-DD] 重構：[架構重構事件標題，例：引入非同步事件分發與解耦儲存層]

### 1. 重構前舊架構的痛點
[描述重構前的架構形態，以及在維護性、效能或擴充性上暴露出的嚴重痛點]
- **痛點 1**：[例：模組同時承擔協議解析與資料庫連線，違反單一職責原則]
- **痛點 2**：[例：同步阻塞調用導致網路抖動時整體處理執行緒被耗盡]

### 2. 本次架構演進的核心改變
[說明重構後的關鍵架構設計與邊界劃分]
- **改變 1**：[例：拆分出獨立的 EventDispatcher，解耦網路層與儲存層]
- **改變 2**：[例：全量切換為非同步無鎖佇列架構]

### 3. 對應開發計畫與驗證
- **參考 Dev Plan**：`[YYYY_MM_DD_HHMM_計畫名稱]`（可透過 `python yscb_cli.py agents-workflow search -q "[關鍵字]"` 檢索完整細節）
- **關鍵架構驗收成果**：[說明重構後效能指標、解耦度或測試覆蓋達成情況]

---

## [YYYY-MM-DD] 重構：[更早的歷史重構事件]

### 1. 重構前舊架構的痛點
[...]

### 2. 本次架構演進的核心改變
[...]

### 3. 對應開發計畫與驗證
[...]
