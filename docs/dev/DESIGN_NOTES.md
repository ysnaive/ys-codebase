---
target: "Dev"
doc_type: "design_notes"
status: "active"
source_paths:
  - "yscb://source/dev/dev/testing/case.py"
  - "yscb://source/dev/dev/testing/sandbox.py"
  - "yscb://source/dev/dev/testing/discovery.py"
  - "yscb://source/dev/dev/tester.py"
  - "yscb://source/dev/dev/checker.py"
related_docs:
  - "./README.md"
  - "./architecture.md"
  - "./user_guide.md"
  - "./testing_guide.md"
last_updated: "2026-10-15"
---

# Dev 開發者工具鏈設計決策與工程註記 (Dev Design Notes)

> 本文件記錄 `dev` 開發者模組與沙盒測試框架中的**反直覺實作、平台相容性妥協與關鍵防呆邊界（維度 ⑤）**。常規架構與 CLI 規格請參閱 [architecture.md](./architecture.md)、[user_guide.md](./user_guide.md) 與 [testing_guide.md](./testing_guide.md)。

---

## 登錄決策清單 (Decision Registry)

| 決策編號 | 標題 / 主題 | 影響檔案 | 風險等級 |
| :--- | :--- | :--- | :---: |
| **DN-DEV-01** *(原 DN-DEV-02)* | 測試失敗現場自動保留與顯式 `self.mark_passed()` 防呆契約 | `source/dev/dev/testing/case.py`<br/>`source/dev/dev/checker.py` | `[!WARNING]` |
| **DN-DEV-02** *(原 DN-DEV-06)* | 沙盒微環境 3-Tier 零拷貝投影與 `shutil.rmtree` 前強制斷開防護 | `source/dev/dev/testing/sandbox.py` | `[!CAUTION]` |
| **DN-DEV-03** *(原 DN-DEV-07.4)* | 宿主環境防穿透三道剛性守門鎖與禁止 `os.getcwd()` 回退鐵律 | `source/dev/dev/testing/case.py`<br/>`source/dev/dev/testing/discovery.py`<br/>`source/dev/dev/tester.py` | `[!CAUTION]` |
| **DN-DEV-04** *(原 DN-DEV-10.3)* | Checker AST 靜態分析之首行 Docstring 節點豁免與 CLI 入口雙軌容錯 | `source/dev/dev/checker.py` | `[!WARNING]` |

---

### [DN-DEV-01] (原 DN-DEV-02) 測試失敗現場自動保留與顯式 `self.mark_passed()` 防呆契約

> [!WARNING]
> **防呆契約：測試方法結尾必須顯式呼叫 `self.mark_passed()`**  
> 在 `YSCBTestCase` 中，未拋出例外但漏寫 `self.mark_passed()` 的測試方法（除顯式標記 `@require(Requirement.NONE)` 外），其執行狀態將被歸類為 `"UNKNOWN"`，並會在 `dev check` 靜態檢核（`_check_test_classes`）時觸發 `[WARN]` 告警。修改或新增測試案例時，請務必於斷言結束處呼叫 `self.mark_passed()`。

- **反直覺設計與三態分類 (`PASSED` / `FAILED` / `UNKNOWN`)**：
  - Python 標準 `unittest.TestCase.tearDown()` 無法直接且跨版本一致地判定當前測試方法是否因斷言失敗而中斷。為此，`YSCBTestCase` 結合 `_callTestMethod` 例外攔截與顯式 `self.mark_passed()` 標記：
    1. **`FAILED`（拋出未捕獲例外或斷言失敗）**：若為專屬獨立沙盒 (`_is_isolated_sandbox=True`)，**刻意不執行 `cleanup_sandbox`**，將故障現場原封不動保留於 `cache://dev/sandbox/sandbox_<timestamp>` 並印出完整路徑供事後除錯。
    2. **`PASSED`（顯式呼叫 `self.mark_passed()` 且無例外）**：於 `tearDown()` 安全清理獨立沙盒（除非指定 `--keep-sandbox`）。
    3. **`UNKNOWN`（無例外但漏呼叫 `self.mark_passed()`）**：安全清理獨立沙盒且**不印出 `[Test Failed]` 假警報**，避免終端洗版，並交由 `dev check` AST 靜態檢查攔截提醒。

---

### [DN-DEV-02] (原 DN-DEV-06) 沙盒微環境 3-Tier 零拷貝投影與 `shutil.rmtree` 前強制斷開防護

> [!CAUTION]
> **致命損毀紅線：銷毀沙盒前絕對禁止直接對沙盒根目錄呼叫 `shutil.rmtree`！**  
> 沙盒內的 `host_env/engine/.venv` 是透過目錄重析點（Windows Junction）或符號連結（POSIX Symlink）指向宿主真實 `.venv`。若未先執行 `SandboxProvisioner._unlink_projected_venv(sandbox_dir)` 即直接呼叫 `shutil.rmtree`，在某些平台或 Python 版本下將穿透重析點，**遞迴刪空宿主微環境的所有第三方套件**！任何清理沙盒之路徑必須統一經由 `SandboxProvisioner.cleanup_sandbox()`。

- **工程妥協與 3-Tier 零拷貝投影 (`_project_venv`)**：
  - 若為每個測試沙盒實體複製 `.venv` 或重新執行 `pip install`，單次沙盒建立將耗時數十秒並耗費大量磁碟 I/O。`SandboxProvisioner` 採用事前於宿主靜默物化（`adapt_build_pip_dependencies`）+ 3-Tier 零拷貝投影：
    1. **Tier 1 (Windows Junction)**：優先調用 `_winapi.CreateJunction` 建立目錄重析點，免 Administrator 權限且耗時 $\le 1\text{ms}$。
    2. **Tier 2 (POSIX Symlink)**：優先調用 `os.symlink` 建立目錄符號連結。
    3. **Tier 3 (`.pth` 降級兜底)**：在 virtiofs、容器跨系統掛載或 exFAT 等不支援重析點/Symlink 的環境自動捕獲 `OSError`，於沙盒建立輕量 `site-packages/host_venv.pth` 寫入宿主 `site-packages` 絕對路徑。
- **強制斷開協議 (`_unlink_projected_venv`)**：
  - `cleanup_sandbox` 在執行 `shutil.rmtree` 前，強制先行檢測 `host_env/engine/.venv`：若為 Junction / Symlink 則僅以 `os.rmdir` / `os.unlink` 解除連結節點本身，確保宿主 `.venv` 100% 零損毀。

---

### [DN-DEV-03] (原 DN-DEV-07.4) 宿主環境防穿透三道剛性守門鎖與禁止 `os.getcwd()` 回退鐵律

> [!CAUTION]
> **安全紅線：嚴禁在 `YSCBTestCase.setUp` 中加入回退至 `os.getcwd()` 的容錯邏輯，亦嚴禁在宿主目錄直接解除 `YSCB_TEST_SANDBOX` 檢查！**  
> 測試案例常包含檔案刪除、組態覆寫與模組卸載等破壞性操作。一旦沙盒路徑解析失敗並回退至 `os.getcwd()`，測試將直接在真實專案根目錄執行，造成專案源碼與宿主環境遭受不可逆的覆寫與污染。

- **三道剛性守門鎖 (Triple-Lock Guard)**：
  1. **第 1 鎖（靜態 AST 門禁 `Checker._check_test_classes`）**：掃描 `tests/test_*.py`，凡 `Test*` 類別直接繼承 `unittest.TestCase` 而非 `YSCBTestCase` 者，直接判定 `CheckSeverity.FAIL` 阻斷。
  2. **第 2 鎖（動態加載門禁 `TestDiscovery` & `Tester` Gate 0）**：
     - `dev op-test` 若偵測到在真實宿主工作區直接被呼叫（非沙盒環境），立即剛性阻斷並引導改用 `dev test`。
     - `TestDiscovery` 動態載入測試類別時檢驗 MRO 繼承鏈，非 `YSCBTestCase` 子類直接拋出 `TypeError` 拒絕掛載。
  3. **第 3 鎖（執行期入口門禁 `YSCBTestCase.setUp`）**：
     - 強制檢驗 `os.environ.get("YSCB_TEST_SANDBOX") == "1"`。
     - 強制由 `YSCB_SANDBOX_DIR` 或向上遍歷目錄結構驗證是否存在合法的 `host_env/` 沙盒特徵；若無法解析出真實沙盒目錄，**立即拋出 `SecurityError` 終止執行，絕不回退至 `os.getcwd()`**。

---

### [DN-DEV-04] (原 DN-DEV-10.3) Checker AST 靜態分析之首行 Docstring 節點豁免與 CLI 入口雙軌容錯

> [!WARNING]
> **維護注意事項：勿移除 `_check_source_files` 的 Docstring 節點豁免或 `_check_cli_compliance` 的雙軌分支**  
> 1. 移除 Docstring AST 豁免會導致模組、類別或函式文檔註解中撰寫的 URI 範例（如說明禁止使用 `module.source://`）被誤判為 Zero-Probing 違規。  
> 2. 移除 `process(args)` 雙軌容錯將導致未宣告 `contributes/core.json` 的輕量測試 Mock 模組（如 `create_mock_source_module` 產物）全數合規檢核失敗。

- **設計細節與雙軌相容**：
  1. **AST Docstring 節點精準豁免 (`_check_source_files`)**：
     - 在掃描字串常數（`ast.Constant`）是否違反 Zero-Probing（存取 `module.source://`）或直接讀寫底層設定檔（`config.project.json`、`contributes.merged.json`）前，先行收集 `Module`、`ClassDef`、`FunctionDef` / `AsyncFunctionDef` 主體首個 `ast.Expr` 字串常數節點（`doc_nodes`）並予以跳過，兼顧嚴格靜態防護與完整 Docstring 範例撰寫自由。
  2. **CLI 入口雙軌命令契約 (`_check_cli_compliance`)**：
     - **軌道 A（具名命令契約）**：當模組於 `contributes/core.json` 宣告了非空的 `commands.cmd` 樹狀結構時，`Checker` 強制要求 `scripts/cli.py` 必須定義對應的所有葉節點具名函式（破折號 `-` 轉底線 `_`），防止宣告了 CLI 指令卻僅以空殼 `process` 掩蓋未實作邏輯。
     - **軌道 B（傳統/Mock 入口相容）**：當模組未定義 `contributes/core.json` 或無 `commands.cmd`（例如沙盒動態合成之最小化 Mock 模組）時，平滑回退為驗證 `def process(args)` 入口函式存在性。


