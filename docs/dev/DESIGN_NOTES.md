# Dev 開發者工具鏈設計決策與工程註記 (Dev Design Notes)

> 本文件記錄 Dev 開發者模組與測試框架中的非直觀實作、工程妥協與關鍵防呆決策（維度 5）。

---

## 登錄決策清單 (Decision Registry)

| 決策編號 | 標題 / 主題 | 影響檔案 | 風險等級 |
| :--- | :--- | :--- | :---: |
| **DN-DEV-01** | 執行期 Auto-Contract 動態契約合成 | `source/dev/dev/testing/contract.py` | 💡 INFO |
| **DN-DEV-02** | 測試失敗現場自動保留機制 | `source/dev/dev/testing/case.py` | 💡 INFO |
| **DN-DEV-03** | 三階測試指令解耦與完全對標虛擬沙盒隔離 | `source/dev/dev/tester.py`<br/>`source/dev/dev/testing/sandbox.py` | 💡 INFO |
| **DN-DEV-04** | 本地發布流水線解耦 Git 乾淨限制之純淨打包哲學 | `source/dev/dev/releaser.py` | 💡 INFO |

---

### [DN-DEV-01] 執行期 Auto-Contract 動態契約合成

- **核心決策**：不要求開發者在每個模組手動撰寫重複的 `test_manifest.py` 或 `test_cli.py`，而是由 `dev.testing.contract.create_contract_suite_for_module(mod)` 在測試收集時，使用 `type(f"{mod_camel}AutoContractTestCase", (YSCBTestCase,), ...)` 動態合成契約測試類別。
- **背後考量**：大幅減輕新模組開發負擔，同時對所有模組實施 100% 強制性的品質守門。

---

### [DN-DEV-02] 測試失敗現場自動保留機制

- **核心決策**：在 `YSCBTestCase.tearDown()` 中，唯有當測試方法顯式呼叫 `self.mark_passed()` 時才清理沙盒。若遇到未捕獲例外或斷言失敗，沙盒目錄原封不動保留在 `temp://sandbox_<timestamp>` 並將絕對路徑印至終端。
- **背後考量**：避免測試出錯時現場被銷毀導致無法重現或除錯。

---

### [DN-DEV-03] 三階測試指令解耦與完全對標虛擬沙盒隔離

- **核心決策**：將測試命令解耦為 `dev op-mksb` (環境工廠)、`dev op-test` (原地單元執行器) 與 `dev test` (組合門面)。`yscb.py` 嚴格僅調用 `modules/`，沙盒建置時完整複製父層 `modules/` 與 `installed_modules` 配置，徹底終結二度沙盒遞迴與父層污染。
- **背後考量**：徹底分離「外層沙盒調度」與「內層測試執行」職責，既保證端到端測試環境純淨度，又提供開發者手動除錯的原子能力。

---

### [DN-DEV-04] 本地發布流水線解耦 Git 乾淨限制之純淨打包哲學

- **核心決策**：在 `dev.releaser` 中移除強制檢查 `git status --porcelain` 的守門限制。本地發布純粹產出單檔 Zip 至 `release/<mod>/<ver>.zip` 並維護 `index.json`，由開發者自主掌控何時 Commit / Push 遠端。若處於非 Git 倉庫，流水線自動安全跳過 Git 操作而不拋出例外。
- **背後考量**：將「本機發布打包」與「遠端版本庫推送」的職責正交解耦，大幅提升本地模組迭代、測試與離線協同的流暢度。

