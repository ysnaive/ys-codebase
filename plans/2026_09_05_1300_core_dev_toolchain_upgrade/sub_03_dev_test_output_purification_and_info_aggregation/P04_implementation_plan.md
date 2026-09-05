# 實作計畫與定稿審查書 (Implementation Plan & Review)

> 功能名稱：dev_test_output_purification_and_info_aggregation  
> 建立日期：2026-09-05  
> 所屬主計畫：2026_09_05_1300_core_dev_toolchain_upgrade  
> 狀態：Confirmed  
> 模板版本：v1.4  

---

## 1. 交叉驗證檢查清單 (Cross-Validation Checklist)

- [x] **需求對齊**：FR-01 ~ FR-05 在 API 規格書與架構設計書中均有明確對應類別與方法簽名。
- [x] **邊界防護**：EC-01 (沙盒崩潰 fallback)、EC-02 (宿主直接調用阻斷)、EC-03 (警告折疊) 均有具體防禦機制。
- [x] **依賴純淨**：嚴格恪守 NFR-01 (單行節流 $\le 50$ Bytes) 與 NFR-03 (宿主零污染)。

---

## 2. 知識庫文檔衝擊與交付規劃 (Documentation Impact Plan)

| 維度 | 文件路徑 | 變更類型 | 交付內容與重點 |
| :--- | :--- | :---: | :--- |
| **模組手冊** | `docs/dev/testing_guide.md` | Modify | 補充第 7 節雙模式信息聚合、輸出節流與沙盒終端輸出完整屏蔽機制。 |
| **設計決策** | `docs/dev/DESIGN_NOTES.md` | Modify | 登記 `[DN-DEV-07]` 沙盒終端輸出完整屏蔽與防穿透剛性守門決策。 |
| **發布日誌** | `CHANGELOG.md` | Modify | 專案根目錄追加 sub_03 高階發布條目。 |

---

## 3. 架構靈魂拷問 (Stress Test & Resilience Review)

> ❓ **尖銳問題 1**：若沙盒進程因重大 Python 語法或 C-extension 錯誤在產出 report JSON 前直接崩潰，宿主如何避免完全死寂？  
> 💡 **防護解法**：宿主調度器在讀取 report JSON 失敗時，檢驗子進程 returncode；若非 0，從 captured 的 `res.stderr` 中提取末尾 20 行（Tail）作為錯誤診斷清單輸出，確保開發者獲得明確除錯線索。

> ❓ **尖銳問題 2**：若移除 `TestRunner.run_suite` 內部的 `YSCB_TEST_SANDBOX="1"`，既有沙盒內部跑測是否會受阻？  
> 💡 **防護解法**：完全不會。因為由 `Tester._run_test` 或 `_run_single_module_worker` 啟動沙盒進程時，外層 `subprocess.run(..., env=p_env)` 早已天然注入 `p_env["YSCB_TEST_SANDBOX"] = "1"`，環境變數真實就位，移除假造反而堵住宿主偽造漏洞。

---

## 4. 實作任務清單 (Task Breakdown & Topological Sequence)

- [ ] **TASK-01**：加固 `case.py` 與 `runner.py`：移除 `TestRunner.run_suite` 偽造標識，加固 `YSCBTestCase.setUp` 沙盒路徑校驗（失敗拋 SecurityError，嚴禁回退 cwd）。
- [ ] **TASK-02**：加固 `Tester._run_op_test` 宿主直接調用守門，確保指定 `--report-json` 與 `--quiet-report` 時不洩漏 stdout。
- [ ] **TASK-03**：重構 `Tester._run_test` 統一改採 JSON IPC，實作雙模式終端輸出屏蔽與信息聚合（徹底封堵 stderr 洩漏）。
- [ ] **TASK-04**：升級 `ASCIIReportFormatter` 支援子進程警告計數折疊與乾淨底部安裝提示。
- [ ] **TASK-05**：撰寫 `source/dev/tests/test_output_purification.py` 單元與整合測試套件（覆蓋 FT-01~04, ET-01~02）。
- [ ] **TASK-06**：執行全套 dev 模組自動化測試與計畫合規檢核。
- [ ] **TASK-DOC**：更新 `docs/dev/testing_guide.md` 與 `docs/dev/DESIGN_NOTES.md` `[DN-DEV-07]`。

---

## 5. 決策定稿 (Confirmed Decision Records)

- **[P04:DR-01] 統一以 JSON IPC 作為跨進程資料通訊唯一契約**：消除單模組與平行測試雙軌分歧，解耦沙盒子進程 stdout 與報告渲染。
- **[P04:DR-02] 剛性根除沙盒穿透隱患**：移除測試執行器身分偽造，用例基類路徑解析嚴格校驗，拒絕任何回退至宿主工作目錄之妥協。
