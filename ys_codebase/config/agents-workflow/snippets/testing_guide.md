- **標準測試執行指令**：
  - **單一測試案例／子系統快速跑測（日常開發推薦）**：`python yscb.py dev test <module> -k <pattern>`（微調測試時可附加 `--no-build` 略過重複打包）。
  - **單一模組完整回歸守門（Phase 06 守門 ① 必跑）**：`python yscb.py dev test <module> -q`。
  - **跑測防呆紅線**：嚴禁在執行 `dev test` 前手動執行 `dev build`（`dev test` 內部自動前置構建）；嚴禁在日常開發中無差別執行 `dev test --all`；嚴禁在完成 `@build` 安裝或正式發布後無意義重複執行 `dev test`。
- **測試目錄拓撲與命名規範**：
  - 各模組測試集中於 `ys_codebase/source/<module>/tests/test_<subsystem>.py`，強制按子系統職責 1:1 歸戶，嚴禁以開發計畫或臨時話題新建碎片測試檔。
- **沙盒隔離與基底類別契約（`YSCBTestCase`）**：
  - 所有測試類別繼承自 `YSCBTestCase`，並標註 `@require(Requirement.LOGIC | Requirement.ENV | Requirement.ISOLATED_SANDBOX)`；每個測試方法結尾必須顯式呼叫 `self.mark_passed()` 完成狀態閉環（詳細沙盒與斷言庫規範請查閱 [`yscb-module-dev/references/testing_and_sandbox.md`](../yscb-module-dev/references/testing_and_sandbox.md)）。

