# 需求規格說明書 (Requirements Specification)

> 功能名稱：sub_01_host_and_core_foundation_remediation  
> 建立日期：2026-10-14  
> 所屬主計畫：2026_10_14_1224_deep_audit_and_ecosystem_refinement  
> 狀態：Confirmed  
> 依據 P00：[P00_discuss.md](./P00_discuss.md)  
> 模板版本：v1.5  

---

## 1. 功能需求清單 (Functional Requirements)

| 需求編號 | 需求名稱 | 詳細規格描述 | 優先級 | 對應 P00 語意 |
| :--- | :--- | :--- | :---: | :--- |
| **FR-01** | `ContributesAggregator` 雙層分桶與同名指令隔離 | 在 `ContributesAggregator` 聚合 `core.commands` 時，將捐獻模組指令保存於 `commands["__modules__"][donor_mod]`，同時維持頂層平鋪結構相容既有 Mock 測試；`core/providers.py` 生成 CLI Guild 時依模組獨立呈現，杜絕同名指令覆蓋。 | P0 | [P00:DR-01] |
| **FR-02** | `contributes list --module` 參數解析修復 | 於 `core/contributes/core.json` 為 `contributes list` 之 `module` (`-m`) 選項宣告 `"args"` 欄位，支援字串傳參，消除被轉為布林 `True` 之問題。 | P0 | [P00:DR-01] |
| **FR-03** | `AtomicEngine` 重複代碼清理與鏡像快取協議修復 | 移除 `engine.py` L249-252 與 L648-755 之重複方法；將 `act_prepare` 的 `mirror://` 修正為 `module.mirror://`，恢復本地版本包快取命中。 | P0 | [P00:DR-01] |
| **FR-04** | `PipManager` / `IdeProjector` 根目錄委派與 `.gitignore` 同步 | 兩者無參初始化之 `_resolve_yscb_root()` 委派 `core.uri._get_yscb_root()`；`PipManager._ensure_gitignore()` 委派 `installer.generate_internal_gitignore()`，維持內部標記區塊一致。 | P1 | [P00:DR-01] |
| **FR-05** | `dispatcher._maybe_auto_spawn_server` 雙層路徑讀取 | 基於傳入之 `yscb_abs` 實體路徑依序讀取 `config/server/config.project.json` 與 `config/server/config.local.json` 合併 `auto_spawn`，兼顧本機覆蓋與臨時目錄測試。 | P0 | [P00:DR-02] |
| **FR-06** | `Installer` 遠端清單與更新掃描補齊 | `cmd_list` 支援 manifest 讀取與 `--remote`/`--provider`；`cmd_update` 支援本地 `.zip`/`index.json` 探測；`restore` 補齊 `provider` 選項宣告與修正預設 URL。 | P1 | [P00:DR-01] |
| **FR-07** | `yscb.py` 參數解析強化與無效來源防呆 | `cmd_init` 與 `cmd_self_update` 支援 `--provider <val>`、`-p <val>`、`--url <val>` 空格分隔與等號雙語法；`_fetch_and_extract_zip` 補齊無效來源 `FileNotFoundError`（保留相容代理函式）。 | P1 | [P00:DR-01] |
| **FR-08** | `core.uri` 安全邊界、反向協議、快取與重載 | 路徑穿越檢查加入 `target_base + os.sep`；`to_uri()` 支援 `config` 協議；`reconcile_undefined_uri()` 寫入後呼叫 `config.reload()`；`_get_merged_uri_schemes` 實作基於 `(yscb_dir, mtime)` 的記憶體快取。 | P0 | [P00:DR-03] |
| **FR-09** | `_format.json` 與 `CommandsRegistry` 契約對齊 | 將 `_format.json:5` 的 `ArgDef.required` 改為 `"bool? = true"`；`CommandsRegistry` 同時相容 `choice` 與 `choices`。 | P1 | [P00:DR-01] |
| **FR-10** | `core/__init__.py` 延遲匯出補齊與 `semver` 修復 | 補齊 `config`, `validator`, `providers`, `ide_projector` 至 `_MODULE_MAP` 與 `__all__`；修正 `VersionTuple.__str__` 在含 `prerelease` 時保留非零 `revision`。 | P1 | [P00:DR-01] |

---

## 2. 邊界與異常情況 (Edge Cases & Failure Modes)

| 邊界編號 | 情境說明 | 預期防禦與處理行為 |
| :--- | :--- | :--- |
| **EC-01** | `contributes.get("core", "commands")` 面臨舊版單元測試平鋪 Mock | 若聚合資料不含 `"__modules__"`，`providers.py` 平滑回退為遍歷頂層平鋪結構，保證 `test_cli_router.py` 100% 通過。 |
| **EC-02** | `contributes list` 未帶參數或帶不存在模組名 | 若指定不存在模組輸出友善錯誤碼 1；若指定合法模組精準列出貢獻點。 |
| **EC-03** | `_maybe_auto_spawn_server` 臨時目錄無 `config.local.json` | 僅以 `config.project.json` 為準，不拋出 `FileNotFoundError`。 |
| **EC-04** | `yscb.py init` 傳入 `-p ./local_rel` 空格參數 | 不得將 `-p` 誤判為 `yscb_root`，正確解析 Provider URL 為 `./local_rel`。 |
| **EC-05** | `core.uri` 遭遇同前綴兄弟目錄穿越 (如 `cache://../.cache_test`) | 因比對 `target_base + os.sep`，立即攔截並拋出安全邊界違規例外。 |
| **EC-06** | `contributes.merged.json` 檔案被刪除或損毀 | `_get_merged_uri_schemes` 捕捉異常並自動觸發自癒重建快照。 |

---

## 3. 非功能需求 (Non-Functional Requirements)

| 需求編號 | 類別 | 指標與量化約束 |
| :--- | :--- | :--- |
| **NFR-01** | 效能 / I/O | `uri.resolve()` 熱路徑免除重複檔案 I/O，命中記憶體快取延遲 $< 0.1\text{ms}$。 |
| **NFR-02** | 相容性 / 測試 | `core` 全套 192 項單元測試與全生態系 550 項測試 100% 通過，0 警告 0 失敗。 |
| **NFR-03** | 架構不變量 | 嚴格維持 `yscb.py` 薄代理函式與 `semver.py` 比較邏輯不變，符合 `[DN-21]` 與 `[DN-10]`。 |

---

## 4. 知識庫與踩坑紀錄查閱 (Known Gotchas & CAUTIONs)

- **`[!CAUTION]`**：`test_core_commands.py:509-619` 執行時 `uri.yscb_scope` 指向實體目錄而非測試臨時目錄，`_maybe_auto_spawn_server` 絕對禁止改調全域 `core.config.get()`。
- **`[!CAUTION]`**：`test_cli_router.py` 模擬了舊版平鋪指令字典，`ContributesAggregator` 必須同時兼顧頂層平鋪與 `__modules__` 雙軌資料。

