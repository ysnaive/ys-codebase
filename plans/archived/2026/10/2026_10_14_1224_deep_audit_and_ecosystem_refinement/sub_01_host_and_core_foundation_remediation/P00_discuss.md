# 需求討論說明書 (Semantic Requirements Discovery)

> 功能名稱：sub_01_host_and_core_foundation_remediation  
> 建立日期：2026-10-14  
> 所屬主計畫：2026_10_14_1224_deep_audit_and_ecosystem_refinement  
> 狀態：Confirmed  
> 計畫類型：Bug Fix  
> 模板版本：v1.2  

---

## 1. 使用者原始需求與意圖 (User Intent)

- **原始陳述**：
  啟動全專案雙向審計主計畫之第一個子計畫 `sub_01`，修復 Host `yscb.py` 與 `core` 模組於雙向審計中確認之底層架構缺陷、隱性 Bug、快取失效與邊界問題。
- **核心目標**：
  1. 修復 `ContributesAggregator` 跨模組同名指令覆蓋污染，解決 `.agents/skills/yscb-cli-guild/SKILL.md` 中 `core list`、`core status`、`knowledge-db status`、`core reload`、`agents-workflow release` 等指令遺失與說明錯置問題（同時維持頂層平鋪結構相容 `test_cli_router.py`）。
  2. 修復 `core.json` 中 `contributes list` 之 `module` (`-m`) 選項漏宣告 `"args"`，導致 `--module=core` 解析為布林 `True` 且查詢恆為空之缺陷。
  3. 清理 `AtomicEngine` 中 108 行重複定義之方法（`act_delete`, `_clean_module_cache`, `act_reload`），並修復 `act_prepare` 誤用已廢棄之 `mirror://` 導致本地鏡像快取穿透之問題。
  4. 修復 `PipManager` 與 `IdeProjector` 的 `_resolve_yscb_root()` 委派 `core.uri._get_yscb_root()`，並讓 `PipManager._ensure_gitignore()` 委派 `installer.generate_internal_gitignore()` 避免抹除 `*.bak` 規則。
  5. 修復 `dispatcher._maybe_auto_spawn_server` 忽略 `config.local.json` 本機覆蓋之缺陷（基於 `yscb_abs` 實體路徑依序合併，確保相容 `test_core_commands.py:509-619`）。
  6. 補齊 `Installer` 契約：`cmd_list` 支援 manifest 讀取與 `--remote`/`--provider`，`cmd_update` 支援本地 `.zip` / `index.json` 探測，`restore` 補齊 `provider` 選項宣告與預設 URL 修正。
  7. 修正 `yscb.py` 進入點之 CLI 參數解析（支援 `init` 與 `self-update` 之 `--provider <val>`、`-p <val>`、`--url <val>` 空格分隔與等號雙語法），為 `_fetch_and_extract_zip` 補上無效來源 `FileNotFoundError`。
  8. 修復 `core.uri` 路徑穿越檢查漏加 `os.sep`、`to_uri()` 支援 `config` 型別協議、`reconcile_undefined_uri()` 後呼叫 `config.reload()`，並為 `_get_merged_uri_schemes` 建立基於 `(yscb_dir, mtime)` 的記憶體快取。
  9. 對齊 `_format.json` 與 `CommandsRegistry` 的 `required` 預設值（改為 `"bool? = true"`），並支援 `choice`/`choices` 雙別名。
  10. 補齊 `core/__init__.py` PEP 562 延遲匯出清單，並修正 `VersionTuple.__str__` 在含 `prerelease` 時保留非零 `revision`。
- **邊界排除 (Explicitly Excluded)**：
  - **[嚴禁改動]** 嚴禁刪除 `yscb.py:467-579` 薄代理函式與 `core/contributes.py:print_global_help`（受 `[DN-21]` 與單元測試鎖定保護）。
  - **[嚴禁改動]** 嚴禁修改 `semver.py` 的版本比較與 `~=` 運算邏輯（受 `test_semver.py` 斷言鎖定保護）。
  - **[邊界隔離]** `dev`、`server`、`knowledge-db`、`agents-workflow` 各模組專屬業務邏輯分流至後續 `sub_02` ~ `sub_06` 處理。

---

## 2. 核心討論與決策紀錄 (Discussion & Decisions)

- **[P00:DR-01] 指令聚合雙層分桶機制（解決同名衝突同時保障向後相容）**：
  在 `ContributesAggregator._aggregate_target("core")` 中，維持既有平鋪合併以滿足 `test_cli_router.py` 與 `test_contributes.py` 的測試 Mock；同時在 `commands` 結構中增闢 `"__modules__": {donor: donor_commands}` 隔離桶。`core/providers.py` 生成 CLI Guild 時優先讀取 `__modules__`，使各模組同名指令（`status`, `list`, `reload`, `release`）獨立成列，徹底消滅覆蓋污染。
- **[P00:DR-02] `_maybe_auto_spawn_server` 雙層路徑讀取契約**：
  不依賴全域 `core.config.get`，直接針對傳入之 `yscb_abs` 實體路徑依序讀取 `config/server/config.project.json` 與 `config/server/config.local.json`，若 `local` 存在 `"auto_spawn"` 則覆蓋 `project`，既尊重本機個人覆蓋，又 100% 通過 `test_core_commands.py:509-619` 臨時目錄測試。
- **[P00:DR-03] URI 記憶體快取以 `(yscb_dir, mtime)` 為鍵**：
  在 `core/uri.py` 中以模組層級快取字典保存 `contributes.merged.json` 內容與檔案 `mtime`，當檔案未變更時避免每次 `uri.resolve()` 重新讀檔反序列化，顯著提升高頻 VFS 讀取效能。

---

## 3. 開放議題與確認紀錄

- [x] 反向查證是否已確立修復邊界無衝突？（已完成，確鑿無誤）
- [x] 是否已明確排除 `yscb.py` 相容代理與 `semver.py` 比較邏輯之誤刪？（已確立為邊界排除項）
- [x] 全套單元測試守門標準：`python yscb.py dev test core` 與全生態系回歸測試須達 100% 通過。

