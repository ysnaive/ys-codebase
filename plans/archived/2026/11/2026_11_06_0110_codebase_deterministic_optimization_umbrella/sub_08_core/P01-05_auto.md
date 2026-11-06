# 自動連續推進綜合規格與實作紀錄 (Consolidated Auto Plan & Task Log)

> 功能名稱：sub_08_core 確定性代碼優化、實作邏輯/併發問題修復與測試套件純化  
> 建立日期：2026-11-06  
> 所屬主計畫：2026_11_06_0110_codebase_deterministic_optimization_umbrella  
> 狀態：Completed  
> 模型：Gemini 3.1 Pro  
> 依據 P00：[P00_discuss.md](./P00_discuss.md)  
> 模板版本：v1.0  

---

## 1. 需求規格與邊界契約 (P01)

### 1.1 功能需求清單 (Functional Requirements)

| 需求編號 | 需求名稱 | 詳細規格與驗收條件 (Acceptance Criteria) | 優先級 | 對應 P00 語意 |
| :--- | :--- | :--- | :---: | :--- |
| **FR-01** | `events`、`uri`、`os_backend`、`config`、`symbols`、`contributes_cmd` 與 `dispatcher` 併發與對稱生命週期修復 (`OPT-01~06`) | 過濾 `__providers__`、URI 重入回傳 `List[Dict]`、VFS 變動連動清除 `contributes` 快取、`config` 空路徑深拷貝、`exec_module` 異常清理 `sys.modules` 與 `dispatch_local` `try...finally` 對稱觸發 `post_cli_dispatch`。 | P0 | [P00:DR-01] |
| **FR-02** | `contributes`、`validator`、`engine`、`installer`、`locale` 與 `pip_manager` 事務鎖及深拷貝加固 (`OPT-07~12`) | `dict[K, V]` 鍵型別與巢狀 `_merge` 校驗、`resolve_local_provider_path` 統一解析、`reconcile_installed_dependencies` 自癒 `provider` 回退、`cmd_rollback` 事務鎖、`locale` 深拷貝與 `PipManager` 可重入 `_pip_lock`。 | P0 | [P00:DR-01] |
| **FR-03** | `platform`、`semver`、`commands`、`telemetry`、`update_checker` 與 `scripts/` 確定性收斂 (`OPT-13~18`) | `is_process_alive(True)` 攔截、`FileLock` 指數退避、`_read_host_venv_pth` 註解過濾、`_parse_semver_str` LRU 快取與 `scripts/cli.py`、`1.2.7.x.py` 頂層 `0 ast.Assign`。 | P0 | [P00:DR-02] |
| **FR-04** | `source/core/tests/` 23 檔測試套件純化與 `0 ResourceWarning` (`AUD-01~30`) | 重命名 62 個工單前綴方法、移除全部 `time.sleep`、修復 12 處未關閉 `open()` 與 `Popen` 洩漏並收斂共用載入器至 `tests/__init__.py`。 | P0 | [P00:DR-02] |

### 1.2 邊界與異常情況 (Edge Cases & Failure Modes)

| 邊界編號 | 情境說明 | 預期防禦與處理行為 |
| :--- | :--- | :--- |
| **EC-01** | `core/config.py` 底部定義了 `set = ConfigManager.set` 全域別名 | `list_modules()` 內部使用 `{m for m in ()}` 建構空集合，避開模組級別名遮蔽內建 `set()`。 |
| **EC-02** | `parse_semver()` 傳入非字串（如 `list` 或 `dict`） | 先執行 `isinstance(version_str, str)` 檢查拋出 `ValueError`，再委派予 `@functools.lru_cache` 裝飾之 `_parse_semver_str()`。 |
| **EC-03** | 單元測試透過 `patch.object(PipManager, 'ensure_venv')` 攔截微環境建立 | `install_packages()` 使用可重入 `with self._pip_lock():` 並在鎖內呼叫 `self.ensure_venv(py_tag)`，兼顧併發安全與測試 Mock 相容。 |

### 1.3 非功能需求 (Non-Functional Requirements)

| 需求編號 | 類別 | 指標與量化約束 |
| :--- | :--- | :--- |
| **NFR-01** | 靜態規範與向後相容 | `Checker().check_module('core')` 達成 `0 FAIL, 0 WARN`，3 支腳本頂層 `0 ast.Assign`，公開 SDK/CLI 100% 向後相容。 |
| **NFR-02** | 測試純淨度與零資源洩漏 | 257 項單元測試於 `python3 -W error::ResourceWarning` 下 100% 通過（耗時 `28.22s`，`0 ResourceWarning`）。 |

### 1.4 知識庫與踩坑紀錄查閱 (Known Gotchas & CAUTIONs)

- **`[!CAUTION]` 公開契約相容與鎖可重入性**：所有內部鎖升級與快取深拷貝均須維持公開方法簽名與單元測試 Mock 攔截點 100% 相容。

---

## 2. 架構設計與異動檔案清單 (P02)

### 2.1 模組架構與核心資料流 (Architecture & Data Flow)

維持 `core` 現有公開模組拓撲，透過內部純函式提煉、可重入鎖保護、原子寫入回滾與測試沙盒隔離消除競態與結構膨脹。

### 2.2 受影響與新建檔案清單 (Impacted & New Files Inventory)

| 檔案路徑 | 類型 | 職責與變更說明 |
| :--- | :---: | :--- |
| `ys_codebase/source/core/core/config.py`, `contributes.py`, `locale.py`, `symbols.py`, `uri.py`, `validator.py` | Modify | 落實 `OPT-02 ~ OPT-04, OPT-07, OPT-08, OPT-11`（執行緒鎖、深拷貝、重入防禦與 `dict[K, V]` 鍵校驗） |
| `ys_codebase/source/core/core/engine.py`, `installer.py`, `pip_manager.py`, `events.py`, `semver.py`, `telemetry.py`, `update_checker.py` | Modify | 落實 `OPT-01, OPT-04, OPT-09, OPT-10, OPT-12, OPT-15, OPT-17`（自癒 `provider` 回退、`cmd_rollback` 事務鎖、可重入 `_pip_lock` 與 `_parse_semver_str` 快取） |
| `ys_codebase/source/core/core/commands/*.py` (5 檔) | Modify | 落實 `OPT-05, OPT-06, OPT-16`（`post_cli_dispatch` 對稱保證、損壞 JSON 防禦與路由去重） |
| `ys_codebase/source/core/core/platform/lock.py`, `process.py`, `venv.py` & `core/vfs/os_backend.py` | Modify | 落實 `OPT-02, OPT-13, OPT-14`（指數退避鎖、`psutil.Process.wait`、`host_venv.pth` 過濾與 VFS 快取連動失效） |
| `ys_codebase/source/core/scripts/cli.py` & `scripts/migrations/1.2.7.x.py` | Modify | 落實 `OPT-18`（頂層 `0 ast.Assign` 與遷移容錯強化） |
| `ys_codebase/source/core/tests/__init__.py` & `tests/test_*.py` (23 檔) | Modify | 落實 `AUD-01 ~ AUD-30`（62 個工單前綴重命名、0 `time.sleep`、0 `ResourceWarning` 與 257 項測試） |

### 2.3 架構決策記錄 (Architecture Decision Records)

- **[P02:DR-01] 受控 CoW 雲端同步與零工單殘留**：全部 45 個修改檔案皆以受控 CoW（舊檔移入 `repo/.trash/` 後上傳原格式新檔）同步至 Google Drive，且源碼與測試內達成 0 工單編號殘留。

---

## 3. 介面契約與 API 簽名 (P03)

### 3.1 介面契約與核心簽名 (Interface Inventory & Method Signatures)

維持 `core` 對外公開 SDK 與 `scripts/cli.py` 所有子指令、選項及回傳碼契約 100% 向後相容（`Mode B`），內部私有輔助函式採單一正統入口（`Mode A`）。

---

## 4. 定稿審查與文檔衝擊規劃 (P04)

### 4.1 交叉驗證與靈魂拷問 (Cross-Validation & Resilience Review)

- [x] 已通過 Step 2 魔鬼代言人（Devil's Advocate B1/B2）反向查驗、Step 4 盲測驗收（Subagent D `PASS`）與 Step 5 零錨定二次審計（Subagent E `P0=0, P1=0, P2=0` 融斷通過）。

### 4.2 知識庫文檔衝擊與交付規劃 (Documentation Impact Plan)

| 維度 | 文件路徑 | 變更類型 | 交付內容與重點 |
| :--- | :--- | :---: | :--- |
| **宏觀 (Macro)** | `CHANGELOG.md` | Modify | 於專案根目錄 `CHANGELOG.md` 登記 `sub_08_core` 優化與修復摘要 |
| **中觀 (Meso)** | `docs/core/README.md` | 免更 | 屬內部確定性重構與併發/邊界防禦強化，無公開架構或 CLI 語法變更 |
| **微觀 (Micro)** | `ys_codebase/source/core/` | Modify | 清理工單編號註解並同步維護公開與內部輔助函式 Docstring |

---

## 5. 實作任務清單與偏差紀錄 (P05)

### 5.1 實作任務清單 (Task Breakdown)

- [x] **TASK-01**：完成 Loop 1 Step 1~2 盲測子代理 A1/A2 初審與 B1/B2 反向驗證（定案 `OPT-01 ~ OPT-18` 與 `AUD-01 ~ AUD-30`）
- [x] **TASK-02**：完成 Loop 1 Step 3 子代理 C1/C2 沙盒實作、測試純化與雲端受控 CoW 同步（共 45 檔）
- [x] **TASK-03**：完成 Loop 1 Step 4 盲測子代理 D 驗收（`PASS`）與 Step 5 盲測子代理 E 零錨定融斷判定（`P0=0, P1=0, P2=0`）
- [x] **TASK-04**：完成 Phase 07 SOP Review Gate 冷眼靜態審查、三層文檔對齊與 `P07_walkthrough.md` 結案

### 5.2 實作偏差紀錄表 (Implementation Deviations)

| 任務編號 | 偏差等級 | 偏離描述與決策理由 | 處置方式 / 記錄 |
| :---: | :---: | :--- | :--- |
| - | - | 無偏差 | - |
