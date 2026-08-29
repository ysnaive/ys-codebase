`__@{BEGIN_HTML_ANNOTATION}__`

Fast Track 執行指引：
1. 目標：適用於修改檔案數 <= 2、不改動 Public API / 介面簽名且無跨模組依賴的小型任務、缺陷修復或輕量擴充，以單一 fast_track_plan.md 敏捷完成 FT-1 ~ FT-3。
2. 溯源與初始化：嵌入 P00 引用，開立計畫目錄時與 changelog.md 剛性伴隨初始化。
3. FT-1 (變更規劃)：定義核心需求、受影響範圍、TASK 清單與測試規劃 ➔ Checkpoint 等待確認 (Confirmed)。
4. FT-2 (實作與驗證)：按 TASK 依序撰寫代碼並執行實機編譯與測試，記錄真實日誌。若遇 Critical 偏差立即升級 Full Track。
5. FT-3 (品質審查與結案)：代碼清理、1:1 知識庫同步，實機調用 `python __${yscb.host://yscb.py}__ agents-workflow plan verify <plan_name>` 驗證計畫完整合規，追加 project://CHANGELOG.md ➔ Checkpoint 等待結案確認 (Completed)。

`__@{FAST_TRACK_AGENTS_GUILD}__`

`__@{END_HTML_ANNOTATION}__`

# Fast Track 敏捷開發計畫 (Fast Track Plan)

`__@{PHASEXX_HEADER}__`

`__@{FAST_TRACK_HEADER}__`

> 計畫類型：Level 0 Fast Track  
> 模板版本：v1.1  

---

## 1. 敏捷需求與實作計畫 (FT-1 Specification & Plan)

### 1.1 核心需求與邊界
- **需求描述**：
- **影響範圍**：

### 1.2 實作任務與測試規劃
- [ ] **TASK-01**：
- **測試案例**：`FT-01` 

---

## 2. 實作與驗證成果 (FT-2 Execution & Test Log)

- **實作結果**：
- **實機測試日誌**：

---

## 3. 結案與交付確認 (FT-3 Closure & Walkthrough)

- **結案狀態**：`Completed`

`__@{FAST_TRACK_TEMPLATE}__`
