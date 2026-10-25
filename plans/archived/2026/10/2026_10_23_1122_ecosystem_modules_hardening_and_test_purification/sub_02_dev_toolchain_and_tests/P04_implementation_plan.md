# 實作計畫與定稿審查書 (Implementation Plan & Review)

> 功能名稱：sub_02_dev_toolchain_and_tests  
> 建立日期：2026-10-24  
> 所屬主計畫：2026_10_23_1122_ecosystem_modules_hardening_and_test_purification  
> 狀態：Confirmed  
> 模型：Gemini 3.8 Flash (Medium)  

> 模板版本：v1.4  

---

## 1. 交叉驗證檢查清單 (Cross-Validation Checklist)

- [x] **需求對齊**：FR-01 ~ FR-09 在 API 規格書中有對應介面與契約
- [x] **邊界防護**：EC-01 ~ EC-07 有具體錯誤處理策略（長選項單一 Token、跨三元組單調防回退、git commit 失敗中斷、UNKNOWN 剛性阻斷、自訂檢核例外轉 WARN、SemVer 數值排序）
- [x] **依賴純淨**：符合 NFR-01 運行時剛性隔離（嚴禁注入 `module.source://`）與 NFR-02 測試套件 7 檔純化收斂且工作區零殘留

---

## 2. 知識庫文檔衝擊與交付規劃 (Documentation Impact Plan)

| 維度 | 文件路徑 | 變更類型 | 交付內容與重點 |
| :--- | :--- | :---: | :--- |
| **模組手冊** | `docs/dev/README.md`、`ys_codebase/source/dev/README.md` | Modify | 更新 CLI 指令說明、`test` 選項、`release-check` 3-Gate 與產物路徑 |
| **專題手冊** | `assets/skills/yscb-module-dev/references/cli_and_commands.md` | Modify | 校正 `CmdBags` 取值語法、預設版號 `0.1.0.0`、產物路徑與 3-Gate 定義 |
| **設計決策** | `docs/dev/DESIGN_NOTES.md` | Modify | 增補 `[DN-DEV-04]` CLI 具名函式契約與全庫單調防回退註記 |
| **微觀註解** | 源碼檔案 Docstrings | Modify | 同步更新 `tester.py`、`releaser.py`、`checker.py`、`runner.py` 介面註解 |
| **發布日誌** | `CHANGELOG.md` | Modify | 記錄本版本發布摘要與 `sub_02` 結案紀錄 |

---

## 3. 架構靈魂拷問 (Stress Test & Resilience Review)

> [?] **尖銳問題 1**：當模組測試檔含有 `_FailedTest`（語法錯誤）時，若使用者下了 `--type=env`，該錯誤是否會被過濾掉而造成假綠燈？  
> [*] **防護解法**：在 `runner.py:filter_suite` 的 `_matches()` 首行特判：凡 `test_case.__class__.__name__ == "_FailedTest"`，在任何 `--type` 下強制回傳 `True` 予以保留，確保語法錯誤 100% 暴露。

> [?] **尖銳問題 2**：`dev check dev` 本身會掃描 `dev/tests/` AST，若我們在 `test_tester.py` 中測試 `UNKNOWN` 行為，是否會導致 `dev check dev` 靜態檢核報警失敗？  
> [*] **防護解法**：嚴格落實 `[P00:DR-03]`，一律透過 `create_mock_source_module(..., files={"tests/test_bad.py": "..."})` 將未呼叫 `self.mark_passed()` 的代碼寫入沙盒暫存模組進行測試，嚴禁在 `test_tester.py` AST 頂層宣告未合規之測試類別。

---

## 4. 實作任務清單 (Task Breakdown & Topological Sequence)

1. **TASK-01 (基礎契約與延遲載入)**：更新 `contributes/core.json` 補齊 `test/op-test/op-mksb` 選項契約與 `events` 清冊；更新 `dev/__init__.py` 實作 PEP 562 按需載入。
2. **TASK-02 (CLI 選項轉譯與測試引擎加固)**：更新 `scripts/cli.py` 正規化選項；更新 `tester.py` 組裝長選項 `--pattern=<pat>` 並落實 `UNKNOWN > 0` 剛性阻斷；更新 `runner.py` 保留 `_FailedTest` 並將 `NETWORK` 納入預設發現。
3. **TASK-03 (發布流水線加固)**：更新 `releaser.py` 實作 Gate 3 全庫最高版本防回退、字母序穩定 DAG 阻斷、`release_git` commit 錯誤攔截；更新 `scripts/cli.py:release_check` 支援預設全模組。
4. **TASK-04 (檢核器修復與腳手架/沙盒現代化)**：更新 `checker.py` 自訂規則運行時隔離、源碼 Schema 優先讀取與 CLI 對稱性檢核；更新 `scaffold.py`、`sandbox.py`、`case.py`、`builder.py` 汰除 `process(args)`、修正 SemVer 排序、還原 CWD 與 `clean` 參數修復。
5. **TASK-05 (測試集收斂 10 檔 $\rightarrow$ 7 檔與補盲)**：裁撤 3 個碎片檔，重寫 5 處虛假測試，消滅暫存洩漏，並於 7 個主測試檔補齊 `D-01`~`D-08` 五大回歸路徑。
6. **TASK-DOC (文檔與手冊同步)**：更新 `assets/skills/yscb-module-dev/references/cli_and_commands.md`、`docs/dev/README.md`、`docs/dev/DESIGN_NOTES.md` 與 `contributes/_manifest.md`。

---

## 5. 決策定稿 (Confirmed Decision Records)

- **[P04:DR-01]** **`P06_test_plan.md` 狀態正式定稿為 `Confirmed`**：所有功能與邊界測試（`FT-01`~`FT-11`、`ET-01`~`ET-07`、`RT-01`、`UX-01`~`UX-02`）均具備實質斷言與明確對應之測試方法，符合 `testing-sop` 六大鐵律。

