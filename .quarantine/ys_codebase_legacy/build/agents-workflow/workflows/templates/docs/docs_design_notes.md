---
target: "[Namespace/ModuleName]"
doc_type: "design_notes"
status: "active"
source_paths:
  - "[src/path/to/relevant_file]"
related_docs:
  - "./README.md"
last_updated: "YYYY-MM-DD"
---

# [模組名稱] — 工程妥協與踩坑記錄 (Design Notes)

> 本文件記錄在 `[ModuleName]` 中，因效能、硬體限制、平台環境、底層 Bug 或其他工程約束，  
> 而採取的**非最直觀實作（Non-Obvious Design）**。  
> **目的**：防止未來的維護者在不知情的情況下，「順手修正」這些有意為之的設計而引發重大事故。

---

## DN-01：[工程妥協標題，例：預分配定長記憶體池以避免高頻 GC 壓力]

### 1. 現狀實作 (Current Implementation)
[描述當前看起來反直覺或特殊的寫法，可附上簡化程式碼片段]

```python
# 範例代碼：展示當前實作形態
buffer_pool = PreallocatedPool(size=1024)
buffer_pool.lock_all_pages()
```

### 2. 約束與限制來源 (Constraint Origin)
> 說明為什麼必須這樣做，限制來自何處：
- **效能量測 (Performance)**：[例：高頻路徑下動態配置造成延遲抖動超過 SLA]
- **平台/硬體限制 (Platform/Hardware)**：[例：特定作業系統/驅動在非同步 I/O 下的行為缺陷]
- **第三方庫 Workaround**：[例：上游庫 Issue #1234 尚未修復，需繞道處理]
- **向後相容性 (Backward Compatibility)**：[例：舊版協議客戶端仍依賴此特異行為]

### 3. 代價與重新評估條件 (Trade-off & Re-evaluation)
- **付出的工程代價**：[例：常駐記憶體增加 X MB]
- **重新評估觸發條件**：[例：當升級至 SDK v3.0 或硬體平台升級時，應重新基準測試驗證]

> [!CAUTION] 核心坑點防護
> **切勿隨意改為動態隨需配置**，否則將導致高負載情境下吞吐量暴跌並引發 OOM 崩潰。

---

## DN-02：[下一個妥協記錄標題]

### 1. 現狀實作
[...]

### 2. 約束與限制來源
[...]

### 3. 代價與重新評估條件
[...]

> [!CAUTION] 核心坑點防護
> [...]
