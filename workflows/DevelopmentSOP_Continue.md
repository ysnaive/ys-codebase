---
description: 接續中斷或已存在的開發計畫工作流
---

# 接續開發計畫工作流 (DevelopmentSOP Continue)

當使用者指示「接續開發」、「繼續上次進度」或指定特定計畫名稱時，Agent 必須依照此工作流恢復上下文。

---

## 執行步驟

### 步驟 1：定位目標計畫目錄
1. 優先執行狀態掃描腳本：
   ```bash
   python .agents/scripts/scan_plan_status.py
   ```
2. 若使用者未明確指定計畫名稱，以最近一次處於 `Planning`、`Implementing` 或 `Reviewing` 狀態的計畫為目標。

### 步驟 2：載入計畫上下文與狀態
1. 讀取工作目錄中的 `changelog.md` 與當前 Phase 文件（或 `FT_plan.md`）。
2. 檢查 `P05_task.md` 的 TODO 勾選進度（若處於 Phase 5）。
3. 檢查 `P06_test_plan.md` 的測試狀態（若處於 Phase 6）。

### 步驟 3：呈遞進度簡報並確認
向開發者呈遞當前定位與進度摘要：
- 當前目標計畫名稱與 Track 模式
- 目前所處 Phase 及已完成/待處理事項
- 下一步預計採取的具體動作

→ **Checkpoint** → 等待開發者確認後繼續推進。
