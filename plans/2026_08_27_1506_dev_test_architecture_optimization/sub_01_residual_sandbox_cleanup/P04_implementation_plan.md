# 實作計畫與定稿審查書 (Implementation Plan & Review)

> 功能名稱：殘留 sandbox 清理機制 (Residual Sandbox Cleanup)  
> 建立日期：2026-08-27  
> 所屬主計畫：`plans://2026_08_27_1506_dev_test_architecture_optimization/`  
> 狀態：`Confirmed`  
> 模板版本：v1.4  

---

## 1. 交叉驗證檢查清單 (Cross-Validation Checklist)

- [x] **需求對齊**：FR-01 ~ FR-04 在 API 規格書中有對應介面（`prune_sandboxes`、`cleanup_all_sandboxes` 與 `Tester._run_test`）
- [x] **邊界防護**：EC-01 ~ EC-04 有具體錯誤處理策略（目錄存在性檢查、異常捕獲與警告、前綴過濾）
- [x] **依賴純淨**：符合 NFR 指標約束（零外部依賴，純標準庫與 `core.uri`）

---

## 2. 知識庫文檔衝擊與交付規劃 (Documentation Impact Plan)

| 維度 | 文件路徑 | 變更類型 | 交付內容與重點 |
| :---: | :--- | :---: | :--- |
| **維度 2** | `docs/dev/user_guide.md` | Update | 補充說明測試沙盒之生命週期管理政策（滾動上限 3 個與 `test --all` 通過時自動清空）。 |

---

## 3. 架構靈魂拷問 (Stress Test & Resilience Review)

> ❓ **尖銳問題 1**：若開發者在多個終端同時執行測試，同時產生沙盒，是否會因目錄競爭刪除導致崩潰？  
> 💡 **防護解法**：`prune_sandboxes` 與 `cleanup_sandbox` 在刪除單一目錄時皆具備 `try...except` 異常防護，若某目錄正在被使用或已被刪除，將安全略過並記錄警告，不中斷正在執行的測試行程。

> ❓ **尖銳問題 2**：若目錄名稱非標準格式或時間戳微秒位數不一致，如何確保時間排序正確？  
> 💡 **防護解法**：標準沙盒生成採 `sandbox_%Y%m%d_%H%M%S_%f` 格式，自然字串正序排列保證最舊者在前；同時在比對時進行 `startswith("sandbox_")` 嚴格過濾。

---

## 4. 實作任務清單 (Task Breakdown & Topological Sequence)

- [ ] **TASK-01**：在 `source/dev/dev/testing/sandbox.py` 中實作 `prune_sandboxes` 與 `cleanup_all_sandboxes`，並於 `create_sandbox` 注入修剪呼叫。
- [ ] **TASK-02**：在 `source/dev/dev/tester.py` 中更新 `_run_test`，於 `--all` 成功時呼叫 `cleanup_all_sandboxes`。
- [ ] **TASK-03**：在 `source/dev/tests/test_sandbox.py` 與 `source/dev/tests/test_tester.py` 中編寫完整單元測試。
- [ ] **TASK-04**：執行全量回歸驗證 `python yscb.py dev test dev` 並回填 P06 日誌。

---

## 5. 決策定稿 (Confirmed Decision Records)

- **[P04:DR-01]** 確立雙軌清理機制：`prune_sandboxes(max_keep=3)` 負責常態滾動防護，`cleanup_all_sandboxes()` 負責 `test --all` 成功後之全量乾淨交付。
