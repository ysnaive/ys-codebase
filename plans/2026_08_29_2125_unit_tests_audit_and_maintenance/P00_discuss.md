# 需求討論說明書 (Semantic Requirements Discovery)

> 功能名稱：`unit_tests_audit_and_maintenance`  
> 建立日期：2026-08-29  
> 狀態：Confirmed  
> 計畫類型：Refactor  
> 模板版本：v1.2  

---

## 1. 使用者原始需求與意圖 (User Intent)

- **原始陳述**：
  針對四大模組 (`core`, `dev`, `agents-workflow`, `knowledge-db`) 的 unit tests 進行地毯式排查維護，檢查是否有可合併、多餘之測試內容，進行主釋出版本前最後整理；並合併為單一 Full Track (Level 1) 計畫推進。
- **核心目標**：
  1. 地毯式掃描四大模組全部 42 個測試檔案與 272 個測試函式。
  2. 消除同質性重複測試（如 `test_semver_v4.py` 與 `test_semver.py`、`test_basic.py` 孤立測試等）。
  3. 整併重複斷言與夾具，清理過期與多餘 Mock。
  4. 確保重構後全生態系 4 大模組之單元測試 100% Passed，零功能測試防線遺失。
- **邊界排除 (Explicitly Excluded)**：
  - 本次任務 100% 聚焦於 `source/<module>/tests/` 測試代碼庫，0 涉及任何 Production Code (Public API / SDK) 契約修改。

---

## 2. 核心討論與決策紀錄 (Discussion & Decisions)

- **[P00:DR-01] 全模組單元測試地毯式排查目標**：
  在主版本發布前，對現有 42 檔測試進行徹底掃描，以「精純化、消除重複、提升測試執行效率與維護性」為唯一主軸。
- **[P00:DR-02] 轉型為單一 Full Track (Level 1) 統籌推進**：
  四模組測試整併總規模預估約 $200 \sim 300$ 行（$> 100$ 行），採單一 Full Track 進行全域架構設計、任務拆分與一次性沙盒回歸驗證，避免多子計畫切換開銷。
- **[P00:DR-03] 四大模組具體整併策略**：
  1. **`core`**：合併 `test_semver_v4.py` 至 `test_semver.py`，統整標準 4 段式 SemVer 測試並移除重複檔案。
  2. **`dev`**：整併 `test_sandbox.py` 與 `test_tester.py` 的重複沙盒建立斷言，精簡 `test_scaffold.py`。
  3. **`agents-workflow`**：移除冗餘孤立的 `test_basic.py`，收斂 `test_targets.py` 與 `test_publisher.py` 的發布目標驗證。
  4. **`knowledge-db`**：整併 `test_parsers_deep.py` 邊界至 `test_parsers.py`，整合 `test_thesaurus.py` 與 `test_tokenizer.py`。

---

## 3. 開放議題與確認紀錄

- [x] 四大模組測試掃描與行數/案例數盤點已完成（共 42 檔、6,898 行、272 個測試）。
- [x] 確認轉型為 Level 1 Full Track 模式推進。
- [x] 確認重構後執行 `python yscb.py dev test --all` 作為最終全生態系驗收關卡。
