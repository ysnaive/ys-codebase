# API 與介面規格書 (API & Interface Specification)

> 功能名稱：sub_01_core_microkernel_and_tests  
> 建立日期：2026-10-24  
> 所屬主計畫：2026_10_23_1122_ecosystem_modules_hardening_and_test_purification  
> 狀態：Confirmed  
> 模型：Gemini 3.8 Flash (Medium)  

> 模板版本：v1.2  

---

## 1. 介面契約清單 (Interface Inventory)

| 介面 / 類別名稱 | 所屬檔案路徑 | 存取層級 | 核心職責 |
| :--- | :--- | :---: | :--- |
| `format_undefined_uri_hint` | `ys_codebase/source/core/core/uri.py` | Public | 產出通用 URI 未定義時之指引字串，解除對 `agents-workflow` 硬編碼 (`FR-01`)。 |
| `check_contributes` | `ys_codebase/source/core/core/commands/contributes_cmd.py` | Public | 支援單檔 `contribute.json` 父目錄目標模組推導、外層剝殼與 `config://` 專案覆寫檢驗 (`FR-02`)。 |
| `_try_hot_dispatch` | `ys_codebase/source/core/core/commands/dispatcher.py` | Internal | 支援 `cmd_path: List[str]` 多層子指令陣列傳遞至常駐 Server (`FR-03`)。 |
| `Installer.cmd_list` | `ys_codebase/source/core/core/installer.py` | Public | 支援 `--remote` 與 `--provider` 查詢遠端或本地 Provider 可用套件狀態 (`FR-04`)。 |
| `config_inspect` | `ys_codebase/source/core/scripts/cli.py` | CLI Leaf | 探測鍵值有效值、覆蓋狀態（`local/project/both/none`）與來源 (`FR-05`)。 |
| `config_unset` | `ys_codebase/source/core/scripts/cli.py` | CLI Leaf | 刪除本機或專案層級之指定鍵值設定 (`FR-05`)。 |
| `dispatch` (Step 8) | `ys_codebase/source/core/core/commands/dispatcher.py` | Public | 群組節點無自由位置參數時，未知子命令強制攔截並提供近似拼寫建議 (`FR-06`)。 |

---

## 2. 核心 API 簽名與詳細規格 (Method Signatures & Contracts)

```python
# 1. core.uri: format_undefined_uri_hint
def format_undefined_uri_hint(
    scheme: str,
    provider: Optional[str] = None,
    binding: Optional[str] = None,
) -> str:
    """Format generic user guidance when an undefined URI scheme/binding is referenced.
    Pre-conditions: scheme is a non-empty string.
    Post-conditions: Returns a generic CLI configuration command hint without upper-module hardcoding.
    """

# 2. core.commands.contributes_cmd: check_contributes
def check_contributes(target_or_uri: Optional[str] = None) -> int:
    """Validate contributes declarations against schema, supporting project-level config:// overrides.
    Pre-conditions: target_or_uri is None (all), a module name, or a file path/URI.
    Post-conditions: Returns 0 if all validated files pass schema, or 1 if any failure occurs.
    """

# 3. core.commands.dispatcher: _try_hot_dispatch
def _try_hot_dispatch(
    module_name: str,
    cmd_path: List[str],
    args: List[str],
    yscb_abs: str,
) -> Optional[int]:
    """Attempt HTTP JSON Lines dispatch to resident background server.
    Pre-conditions: cmd_path is a list of command tokens (e.g. ['uri', 'resolve']).
    Post-conditions: Returns server exit code if cleanly executed, or None on connection failure.
    """

# 4. core.installer: Installer.cmd_list
def cmd_list(self, remote: bool = False, provider: Optional[str] = None) -> int:
    """List installed modules or inspect remote/local provider catalog.
    Pre-conditions: provider is optional; if remote=True, queries provider catalog.
    Post-conditions: Prints formatted table and returns 0 (or 1 on provider failure).
    """

# 5. core.scripts.cli: config_inspect & config_unset
def config_inspect(cmd_bags: CmdBags) -> int:
    """Inspect effective value and origin hierarchy of a configuration key.
    Pre-conditions: cmd_bags contains positional arguments [module, key].
    Post-conditions: Prints inspection report (or JSON if --json passed) and returns 0.
    """

def config_unset(cmd_bags: CmdBags) -> int:
    """Delete a configuration key from local or project scope.
    Pre-conditions: cmd_bags contains positional arguments [module, key].
    Post-conditions: Removes key via ConfigManager.delete and returns 0.
    """
```

- **錯誤與例外契約 (Error & Exception Contracts)**：
  - `check_contributes`：無效 JSON 或 Schema 違規輸出 `[FAIL]` 與具體路徑/欄位，回傳 Exit Code `1`。
  - `config_inspect` / `config_unset`：缺少必要位置參數時輸出用法說明並回傳 `1`；指定鍵值不存在時優雅提示。
  - `_try_hot_dispatch`：捕獲 `urllib.error.URLError`、`http.client.RemoteDisconnected` 與 `ConnectionRefusedError`，回傳 `None` 自動降級為本地派發。
- **階段決策紀錄**：
  - `[P03:DR-01]`：`_try_hot_dispatch` 的第二參數重構為 `cmd_path: List[str]`，徹底避免以空白拼接引發的 Token 混淆。
  - `[P03:DR-02]`：`config_inspect` 與 `config_unset` 作為標準頂層命令函式註冊於 `contributes/core.json`，對齊 `CmdBags` 契約與 `dev check core` 靜態合規要求。

---

## 3. 依賴拓撲與實作順序 (Implementation Topology)

```text
[Step 1: 微內核純化底層]
  core/providers.py (移除遺留導引函式)
  core/uri.py (微內核通用 hint 格式)
  core/contributes.py (移除 print_global_help 死代碼)
       |
       v
[Step 2: CLI 核心組件與命令擴充]
  core/installer.py (cmd_list remote 支援)
  core/commands/contributes_cmd.py (config:// 專案覆寫驗證)
  core/commands/dispatcher.py (_try_hot_dispatch 陣列傳遞 + 步驟 8 未知子指令建議)
  contributes/core.json (config inspect/unset 宣告)
  core/scripts/cli.py (config_list --local, config_inspect, config_unset, HelpRenderer 群組轉調)
       |
       v
[Step 3: 測試集純化與六維度收斂]
  移除死代碼測試 (test_contributes_help.py)
  收斂 8 個碎片測試檔至主測試檔 (test_uri, test_config, test_events_pipeline, test_distribution_lifecycle, test_installer, test_venv_core, test_cli_router)
  5 處虛假測驗改寫 + 沙盒 @require / tearDown 狀態加固 + 4 大漏測路徑補齊
```

