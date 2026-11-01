# 自動連續推進綜合規格與實作紀錄 (Consolidated Auto Plan & Task Log)

> 功能名稱：發布產物二進位解耦、本地同版本自給自足與孤兒分支分發管線 (sub_01)  
> 建立日期：2026-11-01  
> 所屬主計畫：2026_11_01_1138_release_binary_storage_optimization  
> 狀態：Completed  
> 模型：Gemini 4 Argon (Low)  

> 依據 P00：[P00_discuss.md](./P00_discuss.md)  
> 模板版本：v1.0  

---

## 1. 需求規格與邊界契約 (P01)

### 1.1 功能需求清單 (Functional Requirements)

| 需求編號 | 需求名稱 | 詳細規格與驗收條件 (Acceptance Criteria) | 優先級 | 對應 P00 語意 |
| :--- | :--- | :--- | :---: | :--- |
| **FR-01** | 標準發布事件廣播 (`on_module_released`) 與註冊宣告 | 1. 當 `dev` 模組完成正式打包發布時，透過 `core.events.broadcast("on_module_released", ExecutionContext("dev", "on_module_released", [module_name, target_version], metadata={"module": module_name, "version": target_version, "zip_path": zip_path}), emit_module="dev")` 發出標準事件。<br/>2. 同步於 `ys_codebase/source/dev/contributes/core.json`、`ys_codebase/source/dev/contributes/_manifest.md` 及 `Checker._check_sandbox_hooks` (`checker.py:992`) 宣告註冊 `on_module_released` 事件。 | P0 | [P00:DR-01] |
| **FR-02** | `index.json` 升格為版本帳本 SSOT（滑動視窗與 Gate 2/3 聯集守門） | 1. `Builder._update_release_index` 對「既有 `index.json["versions"]` $\cup$ 本地實體 `.zip` $\cup$ `{new_version}`」執行 3-Revision 滑動視窗演算法：視窗內保留之活躍版本寫入 `index.json["versions"]`，並於 `index.json["releases"][<ver>]` 永久保留歷史版本紀錄（活躍版標記 `"status": "active"`、淘汰版標記 `"status": "pruned"`，同時提取當前版本之 `dependencies`）。<br/>2. `Releaser.release_check` (Gate 2/3) 與 `Releaser.release_git` (`is_already_released`) 以 `index.json["versions"]` $\cup$ `index.json["releases"].keys()` $\cup$ 本地實體 `.zip` 為全歷史版本權威基準。 | P0 | [P00:DR-01] |
| **FR-03** | 本地同版本 (`source_version == target_version`) 自給自足動態打包 | 1. 於 `yscb.py` 與 `core` 內建零 `dev` 依賴之純標準庫忽略過濾器（排除 `tests/`、`__pycache__`、`*.pyc`、`.DS_Store` 與 `.yscbignore`）。<br/>2. 打通 `yscb.py` (`_discover_latest_core`, `_bootstrap_package_from_provider`)、`core/engine.py` (`_download_from_release_tier`) 與 `core/installer.py` (`_restore_module_package`) 三條路徑：當本地 Provider 缺失 `<mod>/<ver>.zip` 且 `source/<mod>/manifest.json` 存在並滿足 `"version" == ver` 時，當場動態打包生成 `.mirror/<mod>/<ver>.zip`（並回填 `release/<mod>/<ver>.zip`）後解壓至 `.modules/<mod>/`。 | P0 | [P00:DR-02] |
| **FR-04** | 老舊版本新環境 Clone 之 `pruned` 同三元組 (`X.Y.Z.*`) 自動平滑遞補 | 當外部專案於新環境 Clone（無本地 `.mirror/` 亦無 `source/`），且 `yscb.config.json` 鎖定之舊版 `X.Y.Z.W` 已在 `index.json` 被標記為 `pruned`（或不在可下載 `versions` 清單中）時，`yscb.py` 自舉與 `core` (`cmd_restore` / `act_reload`) 自動於 `index.json["versions"]` 尋找同三元組 (`X.Y.Z.*`) 最高可用 revision 下載還原，印出遞補提示並同步更新 `yscb.config.json`。 | P0 | [P00:DR-02] |
| **FR-05** | 遠端 `releases` 孤兒分支 Provider 對接與雙層 URL 無感遷移 | 1. 將 `yscb.py:20` (`DEFAULT_PROVIDER_URL`)、`core/installer.py:690` 及對應測試更新為 `https://raw.githubusercontent.com/ysnaive/ys-codebase/releases`。<br/>2. 於 `yscb.py`、`core/engine.py`、`core/installer.py` 與 `core/update_checker.py` 讀取/儲存配置時，自動將頂層 `default_provider` 與 `installed_modules[*]["provider"]` 中指向舊官方 `.../main/ys_codebase/release` 之 URL 無感遷移為 `.../releases/ys_codebase/release`。<br/>3. 建立 `.github/workflows/release-publish.yml` 單層孤兒分支自動同步工作流。 | P0 | [P00:DR-03] |

### 1.2 邊界與異常情況 (Edge Cases & Failure Modes)

| 邊界編號 | 情境說明 | 預期防禦與處理行為 |
| :--- | :--- | :--- |
| **EC-01** | 本地 Provider 缺失 `<mod>/<ver>.zip`，且 `source/<mod>/manifest.json` 的 `"version"` 與目標 `ver` **不相等** | 嚴格拒絕從 `source/<mod>` 打包（防止將開發中未發布或不同版本之源碼偽裝為目標版本），回退至下層解析或拋出明確缺失錯誤。 |
| **EC-02** | `cmd_init` 於無 `.zip` 之母倉環境探測 `core` | `_discover_latest_core` 命中同版本 `source/core` 時，先將其動態打包為 `.zip` 檔案並回傳 `.zip` 路徑，避免 `_fetch_and_extract_zip` 直接 `copytree` 未過濾之 `source/core`（含 `tests/`）進入 `.modules/core`。 |
| **EC-03** | 新 Clone 環境 `ys_codebase/release/<mod>/` 僅有 `index.json` 無任何歷史 `.zip`，開發者嘗試以較低版本或重複版本執行 `dev release` | `Releaser.release_check` Gate 2 與 Gate 3 從 `index.json` 的 `versions` 與 `releases` 帳本讀取歷史版本與最高版本，100% 攔截重複版本與版本倒退。 |
| **EC-04** | 老專案鎖定之版本 `X.Y.Z.W` 不在遠端 `versions` 中，但同三元組 `X.Y.Z.*` 亦無任何可用版本 | 不進行跨三元組盲目替換，明確報錯提示使用者執行 `update` 或指定有效版本。 |

### 1.3 非功能需求 (Non-Functional Requirements)

| 需求編號 | 類別 | 指標與量化約束 |
| :--- | :--- | :--- |
| **NFR-01** | 零外部依賴 | `yscb.py` 與 `core` 維持 100% Python 標準庫實作，且不得依賴 `dev` 模組即可完成本地同版本 `source/<mod>` 過濾打包。 |
| **NFR-02** | 第三方儲存庫中立性 | 不在 `core/installer.py:INTERNAL_IGNORE_PATTERNS` 硬編碼忽略 `release/**/*.zip`，確保外部模組開發者可自由選擇其儲存庫版控策略。 |

### 1.4 知識庫與踩坑紀錄查閱 (Known Gotchas & CAUTIONs)

- **`[!CAUTION]` `core.events.broadcast` 參數簽名契約**：`events.broadcast(event_name, context=None, emit_module="core", ...)` 不接受 `**kwargs`，傳遞事件負載必須封裝於 `ExecutionContext(..., metadata={...})` 中。
- **`[!NOTE]` 滑動視窗向後相容契約**：`test_builder.py:101` 斷言 `index.json["versions"]` 僅包含經 3-Revision 滑動視窗保留之活躍版本，故被淘汰之歷史版本必須移出頂層 `versions` 並留存於 `releases[<ver>]`（標註 `"status": "pruned"`）。

---

## 2. 架構設計與異動檔案清單 (P02)

### 2.1 模組架構與核心資料流 (Architecture & Data Flow)

```text
[1. 打包與發布流 (dev)]
Builder.package_release(name, ver)
  ├── 打包產生 release/<name>/<ver>.zip
  ├── _update_release_index(name, desc, ver)
  │     ├── 讀取既有 index.json (versions ∪ releases) 與本地 .zip
  │     ├── 執行 3-Revision 滑動視窗：保留者寫入 versions (status="active")，淘汰者刪本地 .zip 並標記 status="pruned"
  │     └── 提取當前版本 dependencies 寫入 releases[ver]
  └── Releaser.release_module -> events.broadcast("on_module_released", ExecutionContext("dev", ...), emit_module="dev")

[2. 本地自給自足與同三元組遞補流 (yscb.py & core)]
請求還原/下載 <mod>@<ver> (當 mirror:// 與 release:// 皆無 <ver>.zip)
  ├── 分支 A (母倉本地 Provider)：檢查 source/<mod>/manifest.json
  │     └── 若 manifest["version"] == ver -> 純標準庫過濾打包至 mirror/<mod>/<ver>.zip & release/<mod>/<ver>.zip -> 解壓至 .modules/<mod>
  └── 分支 B (遠端/本地 Provider 遇 pruned 舊版)：檢查 index.json
        └── 若 ver 不在 active versions 中，且存在同三元組 (X.Y.Z.*) active 最高版 best_rev -> 平滑遞補下載 best_rev 並更新 yscb.config.json
```

### 2.2 受影響與新建檔案清單 (Impacted & New Files Inventory)

| 檔案路徑 | 類型 | 職責與變更說明 |
| :--- | :---: | :--- |
| `yscb.py` | Modify | 更新 `DEFAULT_PROVIDER_URL` 為 `releases` 分支；新增舊官方 `main` URL 無感遷移、純標準庫同版本 `source/<mod>` 動態打包器，以及 `pruned` 同三元組自動平滑遞補 |
| `ys_codebase/source/core/core/engine.py` | Modify | 新增本地同版本 `source/<mod>` 動態打包 fallback、舊官方 URL 無感遷移，以及 `_find_manifest_in_local_provider` 讀取 `index.json["releases"]` 依賴元數據 |
| `ys_codebase/source/core/core/installer.py` | Modify | 更新 `cmd_restore` 預設 URL、舊官方 URL 雙層無感遷移、`_restore_module_package` 本地同版本 `source/<mod>` 動態打包與 `pruned` 同三元組自動遞補 |
| `ys_codebase/source/core/core/update_checker.py` | Modify | 讀取配置探測更新時支援舊官方 `main` Provider URL 無感遷移至 `releases` URL |
| `ys_codebase/source/dev/dev/builder.py` | Modify | `_update_release_index` 支援無歷史 `.zip` 下基於 `index.json` 計算 3-Revision 滑動視窗並維護 `releases[<ver>]` (`status: "active"\|"pruned"`, `dependencies`) |
| `ys_codebase/source/dev/dev/releaser.py` | Modify | `release_check` (Gate 2/3) 與 `release_git` 改以 `index.json` (`versions` $\cup$ `releases`) $\cup$ 本地 `.zip` 為準；`release_module` 廣播 `on_module_released` 事件 |
| `ys_codebase/source/dev/dev/checker.py` | Modify | `_check_sandbox_hooks` (`checker.py:992`) 納入 `on_module_released` / `module_released` 合法 hook 校驗 |
| `ys_codebase/source/dev/contributes/core.json` | Modify | 於 `events` 區段宣告 `on_module_released` 事件 |
| `ys_codebase/source/dev/contributes/_manifest.md` | Modify | 同步記錄 `on_module_released` 事件契約 |
| `.github/workflows/release-publish.yml` | New | 當 `main` 推送變更時，自動打包並以單一無父節點孤兒 Commit 同步至 `origin/releases` 分支 |
| `ys_codebase/source/core/tests/test_distribution_lifecycle.py` | Modify | 更新預設 Provider URL 斷言，並新增本地同版本 `source/` 動態打包、`pruned` 同三元組遞補與舊 URL 遷移單元測試 |
| `ys_codebase/source/dev/tests/test_builder.py` | Modify | 新增無歷史 `.zip` 環境下 `index.json` 滑動視窗與 `releases` 帳本保留測試 |
| `ys_codebase/source/dev/tests/test_release_pipeline.py` | Modify | 新增無歷史 `.zip` 環境下 `release_check` Gate 2/3 守門與 `on_module_released` 事件廣播測試 |
| `docs/core/DESIGN_NOTES.md` | Modify | 補充本地同版本 `source/` 自給自足打包與 `pruned` 同三元組平滑遞補設計紀錄 |
| `docs/dev/DESIGN_NOTES.md` | Modify | 補充 `on_module_released` 事件廣播與 `index.json` 雙軌帳本 SSOT 設計紀錄 |

### 2.3 架構決策記錄 (Architecture Decision Records)

- **[P02:DR-01] 內建標準庫打包器於 `yscb.py` 與 `core`**：為確保 `yscb.py` 自舉與 `core` 在未安裝 `dev` 模組時仍可獨立將同版本 `source/<mod>` 打包為 `.zip`，於 `yscb.py` 與 `core` 內建輕量標準庫打包輔助函式，對齊 `RELEASE_IGNORES` 與 `.yscbignore` 過濾規則。
- **[P02:DR-02] 雙層舊官方 URL 無感遷移常數化**：定義 `LEGACY_MAIN_PROVIDER_URL = "https://raw.githubusercontent.com/ysnaive/ys-codebase/main/ys_codebase/release"`，凡讀取 `default_provider` 或 `installed_modules[*]["provider"]` 命中該值（含尾斜線變體）時，自動正規化為新版 `releases` 分支 URL。

---

## 3. 介面契約與 API 簽名 (P03)

### 3.1 介面契約與核心簽名 (Interface Inventory & Method Signatures)

```python
# yscb.py
LEGACY_PROVIDER_URLS: Tuple[str, ...]
def _normalize_provider_url(url: Optional[str]) -> str: ...
def _package_source_to_zip_if_exact_version(
    source_dir: str, target_version: str, dest_zip_path: str, release_zip_path: Optional[str] = None
) -> bool: ...
def _resolve_same_triplet_fallback_version(
    provider: str, module_name: str, requested_version: str, base_dir: Optional[str] = None
) -> Optional[str]: ...

# ys_codebase/source/core/core/engine.py
def normalize_legacy_provider_url(provider_url: Optional[str]) -> str: ...
def package_local_source_if_exact_match(
    source_dir: str, target_version: str, dest_zip_path: str, release_zip_path: Optional[str] = None
) -> bool: ...
class AtomicEngine:
    def _resolve_same_triplet_fallback_version(
        self, module_name: str, requested_version: str, provider_url: str, base_dir: Optional[str] = None
    ) -> Optional[str]: ...

# ys_codebase/source/dev/dev/builder.py
class Builder:
    def _update_release_index(
        self, name: str, description: str = "", new_version: Optional[str] = None, manifest_data: Optional[Dict[str, Any]] = None
    ) -> None: ...

# ys_codebase/source/dev/dev/releaser.py
class Releaser:
    def _collect_all_known_released_versions(self, module_name: str) -> Set[str]: ...
    def release_check(self, module_name: str, force: bool = False) -> Tuple[bool, List[str]]: ...
    def release_module(self, module_name: str, force: bool = False, _skip_check: bool = False) -> Tuple[bool, str]: ...
```

- **錯誤與例外契約 (Error & Exception Contracts)**：
  - 當本地 `source/<mod>/manifest.json` 版本與請求之 `target_version` 不一致時，`package_local_source_if_exact_match` 回傳 `False`，不拋出未預期例外，交由呼叫端繼續遠端拉取或報錯。
  - `events.broadcast("on_module_released", ...)` 內部對個別模組 hook 例外具備隔離保護，不中斷打包主流程。
- **階段決策紀錄**：`[P03:DR-01]` 維持 `Builder.package_release` 與 `Releaser.release_module` 既有回傳簽名 `Tuple[bool, str]` 不變，確保所有既有呼叫端 100% 相容。

---

## 4. 定稿審查與文檔衝擊規劃 (P04)

### 4.1 交叉驗證與靈魂拷問 (Cross-Validation & Resilience Review)

- [x] **需求對齊**：FR-01 ~ FR-05 皆已於介面簽名與實作中完整對齊
- [x] **邊界防護**：EC-01 ~ EC-04 皆有具體錯誤攔截與降級策略
- [x] **依賴純淨**：100% 符合 NFR-01 與 NFR-02 指標約束
- **靈魂拷問與防護解法**：
  - *拷問 1：若 `yscb.py` 在自舉時觸發了 `pruned` 同三元組版本遞補（例如將 `1.1.2.0` 遞補為 `1.1.2.3`），如果不寫回 `yscb.config.json` 會怎樣？*
    - **防護解法**：`_is_modules_dirty` 每次啟動都會比對 `yscb.config.json` 的版號與 `.modules/<mod>/manifest.json` 的版號。因此一旦發生同三元組 `pruned` 遞補，必須同步將 `yscb.config.json` 中該模組的 `"version"` 更新為遞補後的實際版本 `1.1.2.3`，徹底杜絕每次執行指令都重跑自舉的死循環。

### 4.2 知識庫文檔衝擊與交付規劃 (Documentation Impact Plan)

| 維度 | 文件路徑 | 變更類型 | 交付內容與重點 |
| :--- | :--- | :---: | :--- |
| **模組手冊** | `docs/core/README.md` | N/A | CLI 介面未變更，無須改動 |
| **專題手冊** | `docs/dev/README.md` | Modify | 補充 `on_module_released` 生命週期事件說明 |
| **設計決策** | `docs/core/DESIGN_NOTES.md`, `docs/dev/DESIGN_NOTES.md` | Modify | 登記本地同版本 `source/` 動態打包、`pruned` 同三元組平滑遞補與 `index.json` 版本帳本 SSOT 設計筆記 |
| **微觀註解** | 源碼檔案 Docstrings | Modify | 同步更新 `yscb.py`、`engine.py`、`installer.py`、`builder.py`、`releaser.py` Docstring |
| **發布日誌** | `CHANGELOG.md` | Modify | 記錄 `sub_01` 發布二進位解耦與自給自足引擎變更摘要 |

- **決策定稿**：**[P04:DR-01]** 確認 `sub_01` 僅建立機制、測試與 CI 工作流，實際 `.gitignore` 忽略 `*.zip` 與 `git filter-repo` 留待 `sub_03` 執行。

---

## 5. 實作任務清單與偏差紀錄 (P05)

### 5.1 實作任務清單 (Task Breakdown)

- [x] **TASK-01**：實作 `dev` 模組 `Builder._update_release_index` 雙軌帳本、`Releaser` (`release_check`, `release_git`, `release_module` 事件廣播)、`Checker._check_sandbox_hooks` 與 `contributes` 事件宣告
- [x] **TASK-02**：實作 `yscb.py` 與 `core` (`engine.py`, `installer.py`, `update_checker.py`) 之本地同版本 `source/` 自給自足動態打包、`pruned` 同三元組平滑遞補與舊官方 `main` URL 無感遷移，並建立 `.github/workflows/release-publish.yml`
- [x] **TASK-03**：編寫與更新 `core` (`test_distribution_lifecycle.py`) 及 `dev` (`test_builder.py`, `test_release_pipeline.py`) 單元與邊界測試並通過全量沙盒測試
- [x] **TASK-DOC**：同步更新 `docs/core/DESIGN_NOTES.md`、`docs/dev/DESIGN_NOTES.md`、`docs/dev/README.md` 與源碼 Docstrings

### 5.2 實作偏差紀錄表 (Implementation Deviations)

| 任務編號 | 偏差等級 | 偏離描述與決策理由 | 處置方式 / 記錄 |
| :--- | :---: | :--- | :--- |
| - | - | 無偏差 | - |

