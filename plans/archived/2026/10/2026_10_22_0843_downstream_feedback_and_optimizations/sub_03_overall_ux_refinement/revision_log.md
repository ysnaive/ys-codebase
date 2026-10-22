# 修訂紀錄書 (Revision Log)

> 功能名稱：sub_03_overall_ux_refinement  
> 建立日期：2026-10-22  
> 所屬主計畫：2026_10_22_0843_downstream_feedback_and_optimizations  
> 狀態：Completed  
> 模型：Gemini 4 Argon (Low)  

> 模板版本：v1.0  

---

## 1. 修訂紀錄清單 (Revision Entries)

> 開發者授權：本子計畫採修訂模式逐項打磨整體 UX，授權允許直接修改控制流與原始碼（2026-10-22）。

### [REV-01] 全指令觸發新版檢查與入口檔 `yscb.py` 版本自檢及 Agent 阻斷提示
- **修訂類別**：UI/UX/DX
- **涉及檔案**：
  - `yscb.py`
  - `ys_codebase/source/core/core/update_checker.py`
  - `ys_codebase/source/core/core/commands/dispatcher.py`
  - `ys_codebase/source/core/scripts/cli.py`
  - `ys_codebase/source/core/tests/test_update_checker.py`
- **修訂摘要**：
  1. **全指令統一觸發**：將 `UpdateChecker` 的非阻塞 12 小時節流版本檢查與提示移至 `core.commands.dispatcher.dispatch` 結尾（`_maybe_check_and_print_updates()`，涵蓋熱派發與本地冷派發），取代原本僅於 `list` / `status` 觸發的限制。
  2. **入口檔 `yscb.py` 語意版本自檢與 Agent 阻斷提示**：於 `yscb.py` 新增明確的 `__version__: str = "1.1.0.6"` 常數；`UpdateChecker` 新增 `_check_host_script_update()` 探測本機與遠端/本地來源 `yscb.py` 之 `__version__` 並進行語意版本比對；當有新版時優先輸出 `[CRITICAL UPDATE]` 與 `[AGENT BLOCKER]` 橫幅，強制要求 AI Agent 立即暫停手頭任務並向開發者請示是否執行 `python yscb.py self-update`。
  3. **`self-update` 快取同步失效**：`cmd_self_update` 更新成功後自動呼叫 `UpdateChecker().invalidate_cache("yscb.py")` 清除入口檔更新提示快取。
- **驗證結果**：新增 `test_host_script_update_detection_and_agent_blocker_tip` 與 `test_dispatcher_triggers_update_check_on_any_command`；`dev check core` 與 `dev test core` 206/206 (100%) 通過。

### [REV-02] 新設備 Clone 後入口檔自適應下載 `core` 與 `restore` 重建運行環境（嚴守確定來源，零跨版本 Fallback）
- **修訂類別**：UI/UX/DX
- **涉及檔案**：
  - `yscb.py`
  - `ys_codebase/source/core/core/installer.py`
  - `ys_codebase/source/core/tests/test_restore_and_jit_modules.py`
- **修訂摘要**：
  1. **嚴格依組態確定來源提取 (`_bootstrap_package_from_provider`)**：當 `yscb.config.json` 存在時，`provider` 與 `version` 皆為已知真理；`yscb.py` 在 `.modules/core` 尚未物化時嚴格從組態宣告之 `provider` 與 `version` 下載解壓 `core`，隨後自動觸發 `core restore` 重建環境，**嚴禁跨版本猜測或無限 fallback（如自動退回 `_discover_latest_core` 或 `"1.1.0.1"`）**。
  2. **來源遺失明確阻斷與修復指引 (`_print_missing_source_remediation`)**：若組態指定之 `version` / `provider` 無法取得，立即中斷並輸出「`'<mod>' 模組 (v<ver>) 來源 '<provider>' 已遺失或無法存取，需手動修復。建議措施為: ...`」（提供 `init --fix` / `install --force`、`restore --force --provider` 與修正 `yscb.config.json` 三項具體措施）。
- **驗證結果**：新增 `test_rev_02_auto_bootstrap_core_and_restore_on_fresh_clone` 與 `test_rev_02_missing_source_no_uncontrolled_fallback`；`dev check core` 與 `dev test core` 208/208 (100%) 通過。

### [REV-03] 精簡唯一入口檔 `yscb.py`（提取共用內部工具函式並拔除 F-01 ~ F-04 隱蔽式 Fallback）
- **修訂類別**：UI/UX/DX
- **涉及檔案**：
  - `yscb.py`
  - `ys_codebase/source/core/tests/test_restore_and_jit_modules.py`
  - `ys_codebase/source/core/tests/test_distribution_lifecycle.py`
- **修訂摘要**：
  1. **提取內部共用工具函式（零邏輯/零安全性變更，自 882 行精簡至 762 行，減少 120 行）**：
     - `_read_json_dict` / `_write_json_lf`：統一處理 JSON dict 安全讀取與 UTF-8 LF 寫入。
     - `_normalize_local_path`：統一處理 `file://` URI 與本地相對/絕對路徑正規化。
     - `_parse_flag_options` & `_render_box_help`：統一 `cmd_init` 與 `cmd_self_update` 之旗標解析與 80 字元 Help 邊框渲染。
     - `_activate_runtime_env`：統一收斂 6 處私有微環境 `.venv`、`.modules/core` `sys.path[0]` 注入與安全 Token 設定。
     - `_extract_and_cache_mirror`：統一套件解壓與 `.mirror` zip 快取寫入，並合併 `cmd_init` 之 `--fix` 與全新初始化收斂段。
  2. **徹底拔除 4 處殘留之隱蔽式 Fallback (`F-01` ~ `F-04`)**：
     - `F-01`：移除 `_discover_latest_core` 遠端探測失敗時硬編碼回傳 `("1.1.0.1", ...)` 之盲猜行為，統一回傳 `(None, None)` 讓呼叫端明確報錯。
     - `F-02`：移除 `_discover_latest_core` 本地 `manifest.json` 損毀或缺失 `version` 時偽造 `"1.0.0.0"` 之 fallback。
     - `F-03`：移除 `cmd_restore` 缺少 `default_provider` 時私自 fallback 至 `DEFAULT_PROVIDER_URL` 與 `"1.0.0.0"` 之行為，缺失時直接輸出手動修復建議並回報失敗。
     - `F-04`：移除 `cmd_self_update` 中針對 `update_check.json` 的冗餘二次手動讀寫 fallback。
- **驗證結果**：新增 `test_rev_03_discover_latest_core_no_fake_fallback`；`dev check core` 與 `dev test core` 209/209 (100%) 通過。

---

## 2. 結案與合規檢核 (Completion & Compliance Checklist)

- [x] **修訂與驗證完畢**：所有修訂項目均已實作並通過測試或驗證，無殘留死代碼或除錯資訊。
- [x] **日誌與文檔同步**：已同步更新計畫內 `changelog.md` 與相關 docs/ 知識庫文檔；若包含使用者可感知之重要變更，依比例原則追加至專案根目錄 CHANGELOG.md。
- [x] **標頭狀態更新**：完成上述檢核並將本清單其餘項勾選 `[x]` 後，將頂部標頭 `> 狀態：` 更新為 `Completed`。
- [x] **結構合規檢核（最終守門）**：最後實機執行 `python yscb.py agents-workflow plan verify <plan_name>` 驗證 100% Passed（若檢出未通過項則原地修正重驗）。

