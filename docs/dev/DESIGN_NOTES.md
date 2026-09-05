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
| **DN-DEV-05** | 本地建置產物直裝通道 (@build) 與宣告式工程規範連動注入 | `source/core/core/engine.py`<br/>`source/dev/manifest.json` | 💡 INFO |
| **DN-DEV-06** | Build 版 pip 相依性適配與沙盒微環境零拷貝投影 | `source/dev/dev/testing/sandbox.py`<br/>`source/dev/dev/checker.py` | 💡 INFO |
| **DN-DEV-07** | 沙盒測試輸出純化、信息聚合與宿主防穿透剛性守門 | `source/dev/dev/tester.py`<br/>`source/dev/dev/testing/runner.py`<br/>`source/dev/dev/testing/case.py` | 💡 INFO |

---

### [DN-DEV-01] 執行期 Auto-Contract 動態契約合成

- **核心決策**：不要求開發者在每個模組手動撰寫重複的 `test_manifest.py` 或 `test_cli.py`，而是由 `dev.testing.contract.create_contract_suite_for_module(mod)` 在測試收集時，使用 `type(f"{mod_camel}AutoContractTestCase", (YSCBTestCase,), ...)` 動態合成契約測試類別。
- **背後考量**：大幅減輕新模組開發負擔，同時對所有模組實施 100% 強制性的品質守門。

---

### [DN-DEV-02] 測試失敗現場自動保留機制

- **核心決策**：在 `YSCBTestCase.tearDown()` 中，唯有當測試方法顯式呼叫 `self.mark_passed()` 時才清理沙盒。若遇到未捕獲例外或斷言失敗，沙盒目錄原封不動保留在 `cache://dev/sandbox/sandbox_<timestamp>` 並將絕對路徑印至終端。
- **背後考量**：避免測試出錯時現場被銷毀導致無法重現或除錯。

---

### [DN-DEV-03] 三階測試指令解耦與完全對標虛擬沙盒隔離

- **核心決策**：將測試命令解耦為 `dev op-mksb` (環境工廠)、`dev op-test` (原地單元執行器) 與 `dev test` (組合門面)。`yscb.py` 嚴格僅調用 `modules/`，沙盒建置時完整複製父層 `modules/` 與 `installed_modules` 配置，徹底終結二度沙盒遞迴與父層污染。
- **背後考量**：徹底分離「外層沙盒調度」與「內層測試執行」職責，既保證端到端測試環境純淨度，又提供開發者手動除錯的原子能力。

---

### [DN-DEV-04] 本地發布流水線解耦 Git 乾淨限制之純淨打包哲學

- **核心決策**：在 `dev.releaser` 中移除強制檢查 `git status --porcelain` 的守門限制。本地發布純粹產出單檔 Zip 至 `release/<mod>/<ver>.zip` 並維護 `index.json`，由開發者自主掌控何時 Commit / Push 遠端。若處於非 Git 倉庫，流水線自動安全跳過 Git 操作而不拋出例外。
- **背後考量**：將「本機發布打包」與「遠端版本庫推送」的職責正交解耦，大幅提升本地模組迭代、測試與離線協同的流暢度。

---

### [DN-DEV-05] 本地建置產物直裝通道 (@build) 與宣告式工程規範連動注入

- **核心決策**：
  1. `core.engine.PackageManager` 特例處理 `@build` revision：當版本約束包含 `build` 時，強制直連 `module.build://` 下載 `*.build.zip`，未建置時拋出清楚的引導提示，徹底終結本地開發需先手動 release 的繁瑣流程。
  2. `dev` 模組透過 `contributes["agents-workflow"]`（`mode: "below"`）向 `WORKFLOW_SOP_STANDARDS` 注入專案特化工程規範（`DevEngineeringStandards.md`），收斂三層空間 SSOT、沙盒除錯加速與禁止 Agent 主動 release/install 鐵律。
- **背後考量**：落實「零侵入宣告式擴充」架構哲學，並提供流暢安全的自引用 (Dogfooding) 開發體驗。

---

### [DN-DEV-06] Build 版 pip 相依性適配與沙盒微環境零拷貝投影

- **核心決策**：
  1. **靜默物化**：在 `create_sandbox` 建立沙盒前，透過 `adapt_build_pip_dependencies` 掃描待測模組之 build/source manifest 中 `pip_dependencies` 宣告，調用 `core.PipManager` 於宿主微環境完成靜默物化。
  2. **3-Tier 投影管線**：沙盒環境透過 Windows Junction (免管理者權限、sub-1ms 完成) 或 POSIX Symlink 穿透宿主微環境；若於 virtiofs / 容器掛載磁碟等受限環境，平滑降級為 `.pth` 檔案指標，保證 100% 跨平台相容。
  3. **沙盒清理防護**：在 `cleanup_sandbox` 調用 `shutil.rmtree` 前，強制調用 `_unlink_projected_venv` 解開重析點/符號連結，徹底阻斷遍歷刪除宿主微環境之風險。
- **背後考量**：兼顧沙盒高保真測試能力與極致效能（零拷貝、零重複網路下載），同時剛性保證宿主微環境之完整性與純淨度。

---

### [DN-DEV-07] 沙盒測試輸出純化、信息聚合與宿主防穿透剛性守門

- **核心決策**：
  1. **IPC JSON 結構化解耦**：單模組與平行測試全面採用 `--report-json` 跨進程交換測試結果，外層宿主調度器作為唯一渲染終端，徹底解耦內層沙盒日誌與宿主終端輸出。
  2. **雙模式輸出純化與信息聚合**：
     - `--quiet` / `-q` 模式：子進程 stdout/stderr 全量屏蔽；測試全數通過時嚴格維持單行統計（`Pass: X(100.0%), Fail: 0, Skip: 0`）；崩潰或非 0 返回碼時精準擷取 stderr tail（後 20 行）供快速診斷。
     - 一般模式：子進程之非致命警告（如沙盒未配置專案 URI 之編譯期警告）以 `[*] Notices: N sandbox warning(s) captured (suppressed, run with --verbose to inspect)` 收斂折疊，杜絕數十行警告洗版。
  3. **沙盒黑盒子與高保真原則**：沙盒內部生命週期 Hook（如 JIT 預發布與自癒物化）維持自然運行，嚴禁粗暴短路業務邏輯；輸出純化由宿主調度器之輸出捕獲與格式化看板完成。
  4. **宿主防穿透剛性守門**：
     - `dev op-test` 於宿主環境直接調用時剛性阻斷（Gate 0），提示改用 `dev test` 進入沙盒。
     - `YSCBTestCase.setUp` 在無法向上解析出合法沙盒目錄時強制拋出 `SecurityError`，徹底拔除回退至 `os.getcwd()` 的漏洞，守護專案根目錄零污染。
- **背後考量**：徹底根除沙盒穿透造成的專案目錄污染，並極大化節約開發與 Agent 協同的終端日誌 Token 吞吐量。



