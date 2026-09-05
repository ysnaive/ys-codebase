# 實作計畫與定稿審查書 (Implementation Plan & Review)

> 功能名稱：core_dev_test_case_purification  
> 建立日期：2026-09-05  
> 所屬主計畫：2026_09_05_1300_core_dev_toolchain_upgrade  
> 狀態：Confirmed  
> 模板版本：v1.4  

---

## 1. 交叉驗證檢查清單 (Cross-Validation Checklist)

- [x] **需求對齊**：FR-01 ~ FR-04 在 API 規格書 P03 中均有對應整合介面與標註簽名。
- [x] **邊界防護**：EC-01 ~ EC-03 有明確的跨分類過濾、動態模組收集與沙盒隔離機制。
- [x] **依賴純淨**：符合 NFR-01 ~ NFR-03 效能與通過率量化約束。

---

## 2. 知識庫文檔衝擊與交付規劃 (Documentation Impact Plan)

| 維度 | 文件路徑 | 變更類型 | 交付內容與重點 |
| :--- | :--- | :---: | :--- |
| **專題手冊** | `docs/dev/testing_guide.md` | Modify | 補充測試純化原則與 WORKFLOW 分類劃分基準手冊 |
| **設計決策** | `docs/dev/DESIGN_NOTES.md` | Modify | 記錄重型沙盒測試遷移至 WORKFLOW 之效能與維護權衡 |
| **發布日誌** | `CHANGELOG.md` | Modify | 追加 `sub_04` 測試案例純化與分類重構摘要 |

---

## 3. 架構靈魂拷問 (Stress Test & Resilience Review)

> ❓ **尖銳問題 1：合併與刪除舊測試檔案後，如何保證斷言沒有任何隱形遺漏？**  
> 💡 **防護解法**：在刪除 `test_tester_sync.py`、`test_tester_throttle.py`、`test_cli_help.py`、`test_cli_guild.py`、`test_contributes_jit.py` 之前，逐一盤點其全部 `assertEqual`、`assertTrue`、`assertRaises` 斷言點，完整對照移植至整併後的 `TestCase` 類別中，並以 `--all-types` 全量跑測確認測試邏輯 100% 覆蓋。

> ❓ **尖銳問題 2：將耗時沙盒測試移出日常預設跑測後，是否會削弱日常開發時的防護力？**  
> 💡 **防護解法**：預設模式（LOGIC + ENV）保留了所有以輕量 Mock、VFS 語意協議與內存狀態機進行的快速單元與環境測試（可於 1~3 秒內完成，大幅減少開發反饋延遲）；而需要 5~10 秒的端到端沙盒建立與子進程派發則由 WORKFLOW 分類收容，在發布前或全量驗證時以 `--all-types` 嚴格守門，兼顧日常靈敏度與最終發布防護。

---

## 4. 實作任務清單 (Task Breakdown & Topological Sequence)

- [ ] **TASK-01**：Dev 模組測試整併（將 sync 與 throttle 測試吸收至 `test_tester.py`，安全刪除舊兩檔）。
- [ ] **TASK-02**：Dev 模組沙盒重型測試 WORKFLOW 標註（`test_sandbox.py` 中 5 項實體沙盒案例）。
- [ ] **TASK-03**：Core 模組 CLI 與 Contributes 測試整合（建立 `test_cli_router.py`，整合 JIT 案例至 `test_contributes.py`，清理舊檔）。
- [ ] **TASK-04**：Core 模組 Pip SDK 測試緊湊化與 Engine WORKFLOW 標註。
- [ ] **TASK-05**：執行全量與預設測試雙軌驗證（`--quiet` 與 `--all-types` 100% 通過）。
- [ ] **TASK-DOC**：更新 `docs/dev/testing_guide.md` 與 `docs/dev/DESIGN_NOTES.md`。

---

## 5. 決策定稿 (Confirmed Decision Records)

- **[P04:DR-01] 零回歸整併與精確標註**：
  整併檔案一律保持單一責任原則，以內部 TestCase 類別名稱保留原測試語意（例如 `TestDevTesterSync`、`TestDevTesterThrottle`、`TestCLIRouterAndGuild`），不破壞測試報告的語意結構。
