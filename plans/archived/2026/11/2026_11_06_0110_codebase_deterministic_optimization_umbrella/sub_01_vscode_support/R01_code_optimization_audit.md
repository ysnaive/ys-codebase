# 技術調研與程式碼優化診斷報告 (Research & Code Optimization Audit)

> 調研主題：vscode-support 模組業務與測試代碼五維度確定性優化診斷 (vscode-support Code & Test Optimization Audit)
> 建立日期：2026-11-06
> 所屬主計畫：2026_11_06_0110_codebase_deterministic_optimization_umbrella
> 狀態：Concluded
> 模型：Unknown
> 模板版本：v1.1

---

## 1. 背景與調研目標 (Background & Objectives)

### 1.1 定錨基準與範圍摘要

- **檢視範圍**：`vscode-support` 模組之業務程式碼（`__init__.py`、`projector.py`、`schema_compiler.py`、`scripts/cli.py`、`scripts/hook.core.py`、`scripts/hook.dev.py`）與測試程式碼（`tests/test_vscode_support.py`）。
- **相容性模式**：對外 SDK 與 CLI 採 `Mode B`（100% 向下相容），對內採 `Mode A`（0 外部引用之私有轉發殼與重複樣板強制收斂）。
- **代理執行軌道**：五步盲眼子代理閉環（A 初審 -> B 反向查證 -> C 實作 -> D 驗收修正 -> E 二次盲審與熔斷裁決）。

---

## 2. 核心分析與評估 (Core Analysis & Evaluation)

### 2.1 契約邊界與內部工具函式查驗表

- **對外公開契約（Mode B 嚴守相容）**：`vscode_support.SettingsProjector`、`vscode_support.SchemaCompiler`、`strip_jsonc`、`scripts/cli.py`（`status`、`sync`、`revert`）與 `scripts/hook.*.py` 入口簽名。
- **內部純私有轉發殼（Mode A 移除）**：`SettingsProjector._resolve_yscb_root`、`SchemaCompiler._rule_str_to_json_schema`。
- **原業務設計疏失分流**：`ISS-01 ~ ISS-08` 共 8 項涉及外部副作用時序或契約取捨，已全數登錄於 `issue_report.md` 並於重構中忽略。

### 2.2 D1 ~ D5 與 T-01 ~ T-06 分級診斷矩陣

| 編號 | 檔案與行號 | 維度與嚴重度 | 結構與測試病徵說明 | 對應重構策略 |
| :---: | :--- | :---: | :--- | :--- |
| **OPT-01** | `projector.py:11`, `cli.py:7` | D2 / P2 | 未使用的 `import shutil` 與 `import os` | S2 死引入清除 |
| **OPT-02** | `projector.py:160`, `schema_compiler.py:99` | D2 / P1 | 0 外部引用之單行私有轉發殼 `_resolve_yscb_root` 與 `_rule_str_to_json_schema` | S2 內聯並移除轉發殼 |
| **OPT-03** | `projector.py:22-111` | D3 / P1 | `strip_jsonc` 雙趟掃描重複實作字串跳脫狀態機並配置中繼字串 | S1+S4 收斂為單趟原地掃描 |
| **OPT-04** | `projector.py:435-625` | D3 / P1 | 三處重複手寫 JSON/JSONC 讀取解析，且 `get_status` 與 `sync_vscode_settings` 重複讀檔 | S3 提取 `_load_settings_jsonc` 與 `deepcopy` 快照比對 |
| **OPT-05** | `projector.py:234-589` | D3 / P1 | 重複實作 `.venv` 路徑前綴比對與 5 處受管清單非空寫入/空鍵彈出樣板 | S3 提取 `_is_under_yscb_venv` 與 `_set_or_pop_list` |
| **OPT-06** | `schema_compiler.py:501-662` | D3 / P1 | 每模組重複呼叫 `_select_latest_mirror_zip` 與重複 SemVer 解析 `try...except` | S3 提取 `_is_valid_semver` 並由呼叫端單次傳入 `latest_zip` |
| **OPT-07** | `schema_compiler.py:224-780` | D1 / P1 | 兩處重複 `_types` 迴圈；`_sync_all_schemas_impl` 長達 164 行混雜多階段與對稱分支 | S1+S3 提取 `_compile_type_defs`、`_write_and_track_schema`、`_append_contributed_schema_bindings`、`_cleanup_orphan_schemas` |
| **OPT-08** | `cli.py:48-122`, `hook.core.py:13-52` | D3 / P2 | CLI 三子指令與 Hook 兩處理器重複初始化 `uri.resolve` 與 `SettingsProjector()` | S3 提取 `_init_cli_context` 與 `_get_workspace_projector` |
| **AUD-01~07** | `tests/test_vscode_support.py` | T-01~T-06 / P0~P2 | broken symlink `try...except OSError: pass` 隱蔽報錯、`on_remove` 虛假 stub、`>= 2` 寬鬆斷言、`ft_08` 大雜燴與核心公開 API 漏測 | 重寫為 15 個單一職責語意化測試並補齊真實生命週期與邊界斷言 |

### 2.3 S1 ~ S6 外科手術重構處方箋 (Refactoring Blueprint)

- 經盲眼子代理 B 反向查證與盲眼子代理 D 驗收修正，完成 `_load_settings_jsonc` 非 dict JSON/JSONC 等價性修正、`_select_latest_mirror_zip` 空字串守衛與 15 項測試案例純化。
- 經盲眼子代理 E 二次零錨定盲審確認業務代碼（D1~D5）與測試代碼（T-01~T-06）之 P0/P1/P2 實質缺失皆為 0。

---

## 3. 結論 (Conclusion)

### 3.1 風險評估與推薦流轉出口

- 於 Loop 1 Step 5 達成 **P0=0, P1=0, P2=0**，正式觸發熔斷結案並完成雲端受控 CoW 交付。
