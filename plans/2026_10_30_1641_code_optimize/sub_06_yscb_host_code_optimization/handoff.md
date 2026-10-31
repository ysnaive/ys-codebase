# 當前進度與暫停交接現場 (Handoff Context)

> 暫停時間：2026-10-31 16:48  
> 所屬計畫：2026_10_30_1641_code_optimize / sub_06_yscb_host_code_optimization  
> 當前所在階段：Research Plan (P00 + R01 Completed / 狀態: In Progress，待升級實作)  
> 模型：Unknown  
> 模板版本：v1.2  

---

## 1. 現場已完成事項
- [x] 完成 `yscb.py`（793 LOC，38 個頂層符號）全倉引用盤點與 `Mode A` 五維度靜態診斷（`D1~D5`）。
- [x] 於主計畫 `2026_10_30_1641_code_optimize` 下建立子計畫 `sub_06_yscb_host_code_optimization`，落檔 [`P00_discuss.md`](./P00_discuss.md) 與 [`R01_code_optimization_audit.md`](./R01_code_optimization_audit.md)，並同步登記於父目錄 [`umbrella_overview.md`](../umbrella_overview.md)。

---

## 2. 現場未完成 / 進行中待辦
- [ ] 待下次 `/continue` 接手時，將 `sub_06_yscb_host_code_optimization` 原地升級為實作計畫（`Full Track` 搭配 `/auto` 或 `Fast Track`），依據 `R01_code_optimization_audit.md` 執行 `yscb.py` 重構與 `ys_codebase/source/core/tests/` 4 支測試檔同步遷移。
- [ ] 執行 `python yscb.py dev test core` 驗證重構後全套單元測試與覆蓋率 100% 通過。

---

## 3. 踩坑與注意事項 (Gotchas & Blockers)
- [WARN] **剛性架構防線（嚴禁觸碰）**：`yscb.py` 必須維持 100% Python 標準庫零第三方依賴；`main()` 必須維持注入 `YSCB_HOST_DISPATCH_TOKEN`；`_activate_runtime_env()`（`L769-L774`）僅能將 `.modules/` 掛載入 `sys.path`，絕對禁止加入任何讀取 `ys_codebase/source/` 的 fallback。
- [WARN] **保留冷啟動自癒符號**：`_bootstrap_package_from_provider`（`L518-L583`）、`_extract_and_cache_mirror`（`L510-L515`）、`_read_module_manifest_version`（`L699-L706`）、`_is_modules_dirty`（`L709-L719`）與 `dispatch_module`（`L734-L737`）屬於 `yscb.py` 冷啟動與 `_auto_bootstrap_and_restore_if_needed` 的真實生產鏈路，不可誤刪。

---

## 4. 上下文交接 (Compressed Task Context)
- **任務核心脈絡與定案清單**：
  1. **直接移除之 0 引用死代碼（`yscb.py`）**：
     - `import difflib` (`L7`)、`import importlib.util` (`L8`)
     - `INTERNAL_IGNORE_BEGIN` (`L22`)、`INTERNAL_IGNORE_END` (`L23`)、`CORE_COMMANDS` (`L25-L29`)、`_MODULE_CACHE` (`L31`)
     - `_resolve_self_update_target_url` (`L207-L209`) 移除無用之 `provider` 參數，簽名收斂為 `_resolve_self_update_target_url(custom_url: Optional[str] = None) -> str`（同步更新 `core/tests/test_distribution_lifecycle.py:48`）。
  2. **直接拔除之 8 個歷史相容轉發殼層與對應測試遷移座標**：
     - `_suggest_command` (`yscb.py:722-725`) $\to$ 更新 `core/tests/test_cli_router.py:74-80`（改測 `core.commands.dispatcher._suggest_command`）與 `core/tests/test_core_commands.py:258, 261-262`。
     - `_print_global_help` (`yscb.py:728-731`) $\to$ 更新 `core/tests/test_cli_router.py:50`（改測 `dispatch(["--help"])`）與 `core/tests/test_core_commands.py:259`。
     - `cmd_event` (`yscb.py:677-678`) $\to$ 更新 `core/tests/test_events_pipeline.py:103, 108`（改測 `dispatch(["event", "list"])`）。
     - `_ensure_jit_lifecycle_pre` / `_ensure_jit_lifecycle_post` (`yscb.py:681-696`) $\to$ 更新 `core/tests/test_events_pipeline.py:83-98, 167-178`（改測 `dispatch` 觸發事件與 `yscb.main(["init", "--help"])` 自舉命令短路不觸發事件）。
     - `_generate_internal_gitignore` (`yscb.py:501-507`)、`_restore_module_package` (`yscb.py:586-592`)、`cmd_restore` (`yscb.py:651-674`) $\to$ 更新 `core/tests/test_distribution_lifecycle.py:341, 459`（改測 `Installer().cmd_restore()` 與 `Installer()._restore_module_package(...)`）。
  3. **`S1 ~ S5` 內部結構純化處方**：
     - 提煉 `_fetch_url_bytes(url: str, timeout: int = 15) -> bytes`：統一封裝 `"User-Agent": "yscb-host/2.0"` 與 `localhost / 127.0.0.1` 之 `ProxyHandler({})` 繞過邏輯，供 `_fetch_and_extract_zip` (`L168`)、`cmd_self_update` (`L270`) 與 `_discover_latest_core` (`L377`) 共用。
     - `_auto_bootstrap_and_restore_if_needed` (`L599-L606`) 復用 `_read_module_manifest_version(core_dest)`。
     - 拆解 `_discover_latest_core` (`L334-L388`) 為本地目錄掃描與遠端 `index.json` 探測兩個輔助函式；拆解 `cmd_self_update` (`L252-L312`) 提取來源讀取與原子替換輔助函式。
- **關鍵檔案與行號座標**：
  - `yscb.py`（`L1-L793`）
  - `ys_codebase/source/core/tests/test_cli_router.py`（`L46-L94`）
  - `ys_codebase/source/core/tests/test_core_commands.py`（`L253-L264`）
  - `ys_codebase/source/core/tests/test_events_pipeline.py`（`L83-L115`, `L167-L179`）
  - `ys_codebase/source/core/tests/test_distribution_lifecycle.py`（`L44-L50`, `L290-L352`, `L446-L474`）

---

## 5. 下一次接手時的第 1 步 (Immediate Next Action)
- 讀取 `plans/2026_10_30_1641_code_optimize/sub_06_yscb_host_code_optimization/handoff.md` 與 `R01_code_optimization_audit.md`，向開發者確認將 `sub_06` 原地升級為 `Full Track`（搭配 `/auto`）並啟動 `yscb.py` 與 `core/tests/` 的 `Mode A` 重構實作。

