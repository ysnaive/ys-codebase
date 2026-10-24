# 需求討論說明書 (Semantic Requirements Discovery)

> 功能名稱：sub_01_core_microkernel_and_tests  
> 建立日期：2026-10-24  
> 所屬主計畫：2026_10_23_1122_ecosystem_modules_hardening_and_test_purification  
> 狀態：Confirmed  
> 模型：Unknown  

> 計畫類型：Refactor  
> 模板版本：v1.2  

---

## 1. 使用者原始需求與意圖 (User Intent)

- **原始陳述**：推進 Global Step 3（Stage 2 地基純化：`2026_10_23_1122/sub_01_core_microkernel_and_tests`），合併落實 [roadmap.md](./roadmap.md) 內之 `core_microkernel_purification_and_cli_hardening`（`C-01`~`C-06`）與 `core_test_suite_purification_roadmap`（`T-01`~`T-06`）。
- **核心目標**：
  1. **微內核跨模組耦合純化 (`C-01`)**：自 `core/providers.py` 移除專屬於 `agents-workflow` 階段概念的 `get_phase_cli_guide` 及 `get_phase00_cli_guide` ～ `get_research_cli_guide` 共 11 個函式；自 `core/uri.py:format_undefined_uri_hint()` 移除 `prov == "agents-workflow" or scheme.startswith("workflow.")` 硬編碼特例；自 `tests/test_events_pipeline.py` 移除對 `agents_workflow.publisher.ensure_jit_release` 的跨模組 `patch`。
  2. **`contributes check` 專案級覆寫檢驗 (`C-02`)**：修正 `core/commands/contributes_cmd.py:check_contributes()` 單檔模式對 `config://<target>/contribute.json` 目標模組（取父目錄 `<target>` 而非檔名 `contribute`）與外層 `<target>` 鍵剝殼邏輯，並於全量／單模組檢查時同步納管 `config://<target>/contribute.json`（`donor_mod="project"`）。
  3. **多層子指令熱派發 (`_try_hot_dispatch`) 參數序列化修復 (`C-03`)**：將 `core/commands/dispatcher.py:_try_hot_dispatch()` 第二參數由空白拼接字串改為 `cmd_path: List[str]`，組裝 HTTP Payload 為 `"args": list(cmd_path) + list(args)`。
  4. **實作 `yscb.py list --remote` (`C-04`)**：於 `core/installer.py:cmd_list(remote=True, provider=...)` 探測本地或遠端 Provider 可用模組與最新版本（支援掃描 `*/index.json`、`release/*/index.json` 或根 `index.json`），並標示本地是否已安裝（`Installed (vX.Y.Z)` vs. `Available`）。
  5. **補齊 `config list --local`、`config inspect` 與 `config unset` (`C-05`)**：於 `core/scripts/cli.py` 打通 `config list --local` 過濾，並在 `contributes/core.json` 與 `core/scripts/cli.py` 暴露 `config inspect <module> <key> [--json]` 與 `config unset <module> <key> [--local]` 頂層葉節點函式。
  6. **統一群組節點未知子命令攔截與 `HelpRenderer` 輸出 (`C-06`)**：在 `core/commands/dispatcher.py` 步驟 8 未知子命令攔截移除 `if not has_fn:` 繞過分支（對 `cmd_spec.cmd and not cmd_spec.args` 一律觸發 `_suggest_command` 報錯回傳 `1`）；在步驟 7 保留 `if not has_fn:` 以保護跨模組無參數預設動作，並將 `core/scripts/cli.py` 內 `config()`、`uri()`、`event()`、`contributes()` 四個群組函式之無參數 fallback 改為呼叫 `HelpRenderer.render_cmd_help("core", ...)`。
  7. **核心測試集六維度純化與 28 $\to$ 20 檔收斂 (`T-01`~`T-06`)**：移除 `core/contributes.py:print_global_help` 死代碼與 `test_contributes_help.py`，將 8 個歷史碎片測試檔無損整併收斂為 20 個子系統測試檔；實質化改寫 5 處虛假測驗 (`T-01`)、消除跨模組測試耦合與重複 `yscb.py` 載入樣板 (`T-04`)、補齊 `@require(Requirement.ENV | Requirement.ISOLATED_SANDBOX)` 與 `tearDown` / `try...finally` 零殘留清理 (`T-05`)，並補齊 4 大高風險漏測路徑 (`T-06`)。
- **邊界排除 (Explicitly Excluded)**：
  - 不涉及 `dev`、`server`、`knowledge-db` 模組內部業務邏輯修改（分別歸屬後續 `sub_02`、`sub_03`、`sub_04`）。
  - 不引入任何第三方 PyPI 依賴，維持 `core` 100% Python 標準庫零依賴原則。
- **架構影響範圍**：
  - `ys_codebase/source/core/core/{providers.py,uri.py,contributes.py,installer.py}`
  - `ys_codebase/source/core/core/commands/{contributes_cmd.py,dispatcher.py}`
  - `ys_codebase/source/core/contributes/core.json`
  - `ys_codebase/source/core/scripts/cli.py`
  - `ys_codebase/source/core/tests/`（28 檔收斂為 20 檔）
  - `docs/core/` 與 `ys_codebase/source/core/README.md`

---

## 2. 核心討論與決策紀錄 (Discussion & Decisions)

- **[P00:DR-01] 採納微內核 100% 去耦合與宣告式群組優先路由（方案 3）**：徹底移除 `core/providers.py` 的 `get_phase*_cli_guide`、`core/uri.py` 的 `agents-workflow` 特例與 `test_events_pipeline.py` 的跨模組 `patch`；於 `dispatcher.py` 步驟 8 未知子命令強制攔截並提供拼寫建議，同時在 `core/scripts/cli.py` 群組函式內轉調 `HelpRenderer.render_cmd_help`，兼顧全系統 CLI 體驗統一與既有單元測試向下相容。
- **[P00:DR-02] `contributes check` 專案級 `config://<target>/contribute.json` 雙模式納管**：單檔模式針對檔名為 `contribute.json` 者取父目錄名作為 `target_mod` 並支援 `data.get(target_mod, data)` 自動剝殼；全量與單模組模式於掃描完 `module://<donor>/contributes/*.json` 後自動檢查 `config://<target>/contribute.json`（以 `donor_mod="project"` 驗證）。
- **[P00:DR-03] 葉節點命令 1:1 頂層函式對齊**：新增之 `config inspect` 與 `config unset` 於 `contributes/core.json` 宣告為葉節點子命令，並於 `core/scripts/cli.py` 實作 `def config_inspect(cmd_bags: CmdBags) -> int` 與 `def config_unset(cmd_bags: CmdBags) -> int`，同時在 `def config()` 手動分發分支中支援直接呼叫相容。
- **[P00:DR-04] 測試集 28 $\to$ 20 檔子系統 1:1 對齊收斂與六維度純化（方案 3）**：同步绑定執行 `C-01`~`C-06` 與 `T-01`~`T-06`，裁撤 8 個碎片／過時測試檔（`test_contributes_help.py`、`test_config_and_hook_observability.py`、`test_robustness.py`、`test_build_git_decoupling.py`、`test_restore_and_jit_modules.py`、`test_installer_restore.py`、`test_pip_manager_sdk.py` 及 `test_cli_router.py` 重複項），確保 20 個測試檔 100% 獨立通過且沙盒零殘留。

---

## 3. 開放議題與確認紀錄

- 所有技術細節與測試收斂映射已於合流之 [roadmap.md](./roadmap.md) 完整定義並確認無歧義，標頭狀態直接設為 `Confirmed`。
