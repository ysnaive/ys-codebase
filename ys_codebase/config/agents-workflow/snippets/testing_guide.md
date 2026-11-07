- **標準測試執行指令与兩階靶向跑測鐵律（Mandatory Targeted-First Execution）**：
  - **開發與除錯期間強制單點靶向跑測**：日常實作、迭代與除錯期間，**任何時候僅允許執行單點靶向測試** `python yscb.py dev test --target=<module>:<TestClass>.<test_method>`（或子系統類別 `--target=<module>:<TestClass>`，僅改測試碼時附加 `--no-build` 略過重複打包），**嚴禁在開發與除錯中途跑全模組或全倉測試**。
  - **全量回歸唯一時機（僅限 Phase 06 確認收尾時單次執行）**：唯有在所有單點靶向測試 100% 通過、進入 Phase 06 最終驗收收尾時，方允許對受影響模組執行**唯一一次**完整回歸 `python yscb.py dev test <module> -q`；若全量回歸發現個別案例失敗，強制退回 `--target=<module>:<TestClass>.<test_method>` 單點重現與修復，嚴禁以全量測試作為除錯迴圈。
  - **跑測防呆紅線**：嚴禁在執行 `dev test` 前手動執行 `dev build`（`dev test` 內部自動前置構建）；嚴禁無差別執行 `dev test --all`；嚴禁在完成 `@build` 安裝或正式發布後無意義重複執行 `dev test`。
- **測試目錄拓撲與命名規範**：
  - 各模組測試集中於 `ys_codebase/source/<module>/tests/test_<subsystem>.py`，強制按子系統職責 1:1 歸戶，嚴禁以開發計畫或臨時話題新建碎片測試檔。
- **沙盒隔離與基底類別契約（`YSCBTestCase`）**：
  - 所有測試類別繼承自 `YSCBTestCase`，並標註 `@require(Requirement.LOGIC | Requirement.ENV | Requirement.ISOLATED_SANDBOX)`；每個測試方法結尾必須顯式呼叫 `self.mark_passed()` 完成狀態閉環（詳細沙盒與斷言庫規範請查閱 [`yscb-module-dev/references/testing_and_sandbox.md`](../yscb-module-dev/references/testing_and_sandbox.md)）。

