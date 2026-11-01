# 自動連續推進綜合規格與實作紀錄 (Consolidated Auto Plan & Task Log)

> 功能名稱：版本相容性事後修正機制、釋出元數據與更新嚴重度治理 (sub_02)  
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
| **FR-01** | `index.json["releases"]` 依賴覆寫優先級、候選版本相容性過濾、`core` 依賴檢核與 `mirror://` 離線快取 | 1. `AtomicEngine` 於 `_find_manifest_in_local_provider` (`engine.py:771-796`) 與 `_get_module_manifest_from_provider_or_local` (`engine.py:829-849`) 解析候選版本時，若 `index.json["releases"][<ver>]["dependencies"]` 存在，優先權高於 `.zip` 內建 `manifest.json["dependencies"]`；且在挑選最高版本前，先過濾出與當前已安裝環境（特別是 `core` 版本）相容之候選版本。<br/>2. `AtomicEngine.act_solve_deps` (`engine.py:880`) 移除對 `dep_name == "core"` 之無條件跳過，主動檢核當前已安裝之 `core` 版本是否滿足 `dep_ver` 約束（含 `.build` 正規化處理），不相容時拋出明確 `RuntimeError`。<br/>3. `Installer.cmd_update` (`installer.py:474-501`) 在更新前過濾 `major_constraint` 內與當前環境依賴相容之最高版本；且無論 `updated_any` 是否為 `True`，均呼叫 `UpdateChecker().invalidate_cache(m)` 清除快取。<br/>4. `AtomicEngine` 下載或解析 `<mod>/index.json` 時同步快取至 `module.mirror://<mod>/index.json`；於 `_reload_materialize_single_module` (`engine.py:1060-1088`) 解壓 `.mirror` 至 `staging_dir` 後，讀取 `module.release://<mod>/index.json` 或 `module.mirror://<mod>/index.json` 之 `releases[<ver>]` 覆寫 `staging_dir/manifest.json`，確保離線 `reload` 與 `rollback` 100% 冪等保留事後依賴修正。 | P0 | [P00:DR-01] |
| **FR-02** | `dev index-patch` 輕量事後修補 CLI 與 `Checker._check_manifest` Schema 校驗 | 1. 新增 `python yscb.py dev index-patch <module> --ver=<ver> [--dep="<mod>:<constraint>[;<mod2>:<constraint2>]"] [--status=active\|pruned] [--type=<type>] [--urgency=<urgency>] [--summary="<text>"]`（支援 `--version` 別名，且 `--dep` 支援重複傳入或以分號 `;` 分隔多組 `mod:constraint`，避免與 SemVer 區間之逗號 `,` 衝突），直接更新 `module.release://<module>/index.json` 之 `releases[<ver>]`，並在 `--status` 變更時同步更新頂層 `versions` 清單。<br/>2. 於 `ys_codebase/source/dev/scripts/cli.py` 之 `_normalize_bags` 補齊 `"urgency"`、`"summary"`、`"dep"`、`"ver"`、`"version"`、`"status"`（當同名 `--dep` 重複出現時以 `;` 串接保留所有項目）。<br/>3. 於 `Checker._check_manifest` (`checker.py:462`) 新增對 `manifest.json` 選填欄位 `"release"` 之結構校驗（若存在必須為 `dict`，且其內 `type`、`urgency`、`summary` 若存在必須為非空字串）。 | P0 | [P00:DR-02] |
| **FR-03** | 雙軌發布元數據 (`type` / `urgency` / `summary`) 寫入與 `bump-revision` 技能擴充 | 1. `dev release` 與 `dev release-git` 新增選填參數 `--type`、`--urgency`、`--summary`；當開發者或 Agent 透過 CLI 傳入時，在執行 `release_check` (Gate 1) 與 `git add` **之前**先寫入 `module.source://<mod>/manifest.json["release"]`，再執行打包與索引更新，使 Gate 1 校驗、Git Commit、`.zip/manifest.json` 與 `release/<mod>/index.json["releases"][<ver>]` 100% 同步。<br/>2. `Builder._update_release_index` 在重建或更新索引時，對既有版本保留 `existing_releases[<ver>]` 已修補之 `dependencies`、`type`、`urgency`、`summary`，不因重新掃描 `.zip` 而覆蓋事後修補值；對新打包版本則從 `manifest.json` 提取 `dependencies` 與 `release` 元數據。<br/>3. 更新 `ys_codebase/config/agents-workflow/skills/bump-revision/SKILL.md` 納入選填元數據旗標說明，並執行 `agents-workflow compile` 同步物化產物。 | P0 | [P00:DR-03] |
| **FR-04** | 向前相容元數據解析、跨版本區間掃描與 `[CRITICAL UPDATE]` 醒目告警 | 1. `UpdateChecker` 實作向前相容 (Forward-Safe) 之元數據解析器：對未知 `type` 與 `urgency` 字串不拋出例外，直接轉大寫標籤 `[<TYPE>]` 並套用預設提示等級。<br/>2. `UpdateChecker.check_updates` 過濾同主版本 (`^cur_major.cur_minor.cur_patch`) 且與當前已安裝 `core` 相容之最高可用版本 `latest_ver`（避免對無法升級之版本重複告警），並掃描 `index.json["releases"]` 中所有滿足 `cur_ver < v <= latest_ver` 之版本（含中間已 `pruned` 版本），取最高嚴重度 (`critical` > `recommended` > `optional`，或 `type == "hotfix"` 視同 `is_critical = True`) 與對應摘要寫入 `cache://core/update_check.json`。<br/>3. `UpdateChecker.get_tips` 根據快取之 `is_critical` / `urgency` / `type` / `summary`，對 `critical` 更新輸出雙線醒目橫幅 `[!] [CRITICAL UPDATE] 模組 '<mod>' 有重要修補更新可用...`，對一般更新輸出附帶 `[<TYPE>]` 與 `summary` 之增強提示。 | P0 | [P00:DR-03], [P00:DR-04] |

### 1.2 邊界與異常情況 (Edge Cases & Failure Modes)

| 邊界編號 | 情境說明 | 預期防禦與處理行為 |
| :--- | :--- | :--- |
| **EC-01** | 使用者環境鎖定 `core@1.1.0`，而遠端某模組最新版本 `1.2.3.0` 被 `dev index-patch` 事後標記為 `dependencies: {"core": ">=1.2.0"}`，次高版本 `1.2.2.0` 為 `{"core": ">=1.1.0"}` | `UpdateChecker` 與 `Installer.cmd_update` 過濾掉與 `core@1.1.0` 不相容之 `1.2.3.0`，僅推薦並升級至最高相容版本 `1.2.2.0`；若使用者已處於 `1.2.2.0`，則不顯示無效更新提示，且 `cmd_update` 執行後清除舊快取。 |
| **EC-02** | 使用者從 `1.0.0.0` 跨版本升級至 `1.0.0.4`，其中 `1.0.0.1` 曾發布 `urgency: "critical"` 但已被滑動視窗淘汰 (`status: "pruned"`)，而最新 `1.0.0.4` 為 `urgency: "optional"` | `UpdateChecker` 掃描 `index.json["releases"]` 內 `(1.0.0.0, 1.0.0.4]` 區間所有條目（含 `pruned` 版本），捕捉到 `1.0.0.1` 之 `critical` 標記，向 `1.0.0.0` 使用者觸發 `[CRITICAL UPDATE]` 告警並保留關鍵摘要。 |
| **EC-03** | 舊版客戶端讀取到未來新版本定義之未知 `type`（如 `"security"`）或未知 `urgency`（如 `"urgent"`） | 向前相容解析器絕不拋出 `ValueError` 或崩潰，未知 `type` 自動轉為 `[SECURITY]` 標籤，未知 `urgency` 安全降級為一般更新提示。 |
| **EC-04** | 使用者在離線環境執行 `yscb.py reload` 或 `rollback`，此時無法連線遠端 Provider，且 `.mirror/<mod>/<ver>.zip` 內仍是未修補之舊 `manifest.json` | `_reload_materialize_single_module` 讀取預先快取之 `module.mirror://<mod>/index.json`，將 `releases[<ver>]["dependencies"]` 覆寫至解壓後之 `.modules/<mod>/manifest.json`，確保離線還原不丟失依賴修正。 |
| **EC-05** | 開發者執行 `dev index-patch <mod> --ver=9.9.9.9` 修補一個尚不存在於 `index.json` 的版本，或帶入格式錯誤之 `--dep="invalid_format"` | 若 `--dep` 不含 `:` 分隔符則明確報錯回傳非零狀態碼；若版本已存在則原地合併更新 `releases[<ver>]`，若版本不存在且明確傳入參數則安全建立該版本條目並同步維護 `versions` 清單排序。 |

### 1.3 非功能需求 (Non-Functional Requirements)

| 需求編號 | 類別 | 指標與量化約束 |
| :--- | :--- | :--- |
| **NFR-01** | 零二進位重打包開銷 | `dev index-patch` 僅讀寫 `index.json` 文本，不觸碰、不重壓任何 `.zip` 檔案，亦不耗用 Revision 版號。 |
| **NFR-02** | 向下與向前雙向相容 | 既有不含 `"release"` 欄位之 `manifest.json` 與不含 `type`/`urgency`/`summary` 之舊版 `index.json` 100% 正常運作，預設視為 `optional` 一般更新。 |

### 1.4 知識庫與踩坑紀錄查閱 (Known Gotchas & CAUTIONs)

- **`[!CAUTION]` `dev/scripts/cli.py` 參數 Bag 正規化攔截**：`ys_codebase/source/dev/scripts/cli.py:19-22` 的 `_normalize_bags` 透過白名單 `value_options` 將 `--opt val` 轉換為 `--opt=val`。新增 CLI 選項（`urgency`, `summary`, `dep`, `ver`, `version`, `status`）必須同步加入 `value_options`，否則使用者以空白分隔傳參時會被誤判為位置參數。
- **`[!CAUTION]` 開發環境 `core@X.Y.Z.build` 版本比對**：當母倉安裝 `core@1.2.0.build` 時，`parse_version("1.2.0.build")` 的 `revision` 為 `-1`，在直接比對 `VersionTriplet(1, 2, 0, -1) >= VersionTriplet(1, 2, 0, 0)` 時會因為 `-1 < 0` 而被誤判為小於 `1.2.0`！因此在檢核環境已安裝之 `core`（或其他已安裝模組）是否滿足依賴約束時，若已安裝版本帶 `.build` 後綴，必須將其基準版本視為 `X.Y.Z.999999`（或去除 `.build` 後綴作為正式版 `X.Y.Z.0`）進行相容性判定。

---

## 2. 架構設計與異動檔案清單 (P02)

### 2.1 模組架構與核心資料流 (Architecture & Data Flow)

```text
[1. 雙軌元數據發布與事後修補流 (dev)]
  ├── 路徑 A (發布時注入): dev release / release-git [--type] [--urgency] [--summary]
  │     ├── 將 {"type", "urgency", "summary"} 寫入 source/<mod>/manifest.json["release"]
  │     └── Builder.package_release -> 打包進 <ver>.zip/manifest.json 並同步寫入 release/<mod>/index.json["releases"][<ver>]
  └── 路徑 B (事後修補): dev index-patch <mod> --ver=<ver> [--dep=...] [--status=...] [--type=...] [--urgency=...] [--summary=...]
        └── Releaser.patch_release_index -> 原地更新 release/<mod>/index.json["releases"][<ver>] 與頂層 versions

[2. 依賴覆寫、候選過濾與離線鏡像同步流 (core)]
  ├── 下載 / 查詢 index.json -> 同步快取一份至 module.mirror://<mod>/index.json
  ├── act_solve_deps / cmd_update:
  │     ├── 讀取 index.json["releases"][<ver>]["dependencies"] (優先於 .zip/manifest.json)
  │     ├── 過濾掉與當前已安裝 core 版本衝突之候選版本
  │     └── 檢核 dep_name == "core" 對當前已安裝 core 版本之相容性
  └── _reload_materialize_single_module:
        └── 解壓 mirror/<mod>/<ver>.zip 至 staging_dir -> 讀取 release:// 或 mirror:// 之 index.json["releases"][<ver>] 覆寫 staging_dir/manifest.json

[3. 跨版本嚴重度聚合與提示流 (UpdateChecker)]
  └── check_updates:
        ├── 過濾同主版本 (^Major.Minor.Patch) 且與已安裝 core 相容之最高可用版 latest_ver
        ├── 掃描 index.json["releases"] 中 (cur_ver, latest_ver] 所有版本 (含 pruned)
        ├── 聚合最高 urgency (critical > recommended > optional) 與 summary -> 寫入 cache://core/update_check.json
        └── get_tips() -> 若 is_critical 則渲染 [!] [CRITICAL UPDATE] 雙線警告橫幅，否則渲染附帶 [<TYPE>] 之一般提示
```

### 2.2 受影響與新建檔案清單 (Impacted & New Files Inventory)

| 檔案路徑 | 類型 | 職責與變更說明 |
| :--- | :---: | :--- |
| `ys_codebase/source/core/core/engine.py` | Modify | 實作 `index.json["releases"]` 依賴覆寫優先級、候選版本相容性過濾、`act_solve_deps` 對 `core` 依賴之檢核、`module.mirror://<mod>/index.json` 快取與 `_reload_materialize_single_module` 離線覆寫 |
| `ys_codebase/source/core/core/installer.py` | Modify | `cmd_update` 過濾與當前環境相容之最高候選版本，並確保無論是否升級皆執行 `UpdateChecker().invalidate_cache(m)` |
| `ys_codebase/source/core/core/update_checker.py` | Modify | 實作向前相容元數據解析、同主版本與 `core` 相容性過濾、`(cur_ver, latest_ver]` 跨版本（含 `pruned`）嚴重度聚合與 `[CRITICAL UPDATE]` 橫幅渲染 |
| `ys_codebase/source/dev/dev/builder.py` | Modify | `_update_release_index` 提取 `manifest.json["release"]` 元數據寫入 `releases[<ver>]`，並保護既有版本已修補之 `dependencies` 與元數據不被覆蓋 |
| `ys_codebase/source/dev/dev/releaser.py` | Modify | 新增 `patch_release_index` 方法，並於 `release_module` / `release_git` 支援 `release_meta` 雙軌寫入 `source/<mod>/manifest.json["release"]` |
| `ys_codebase/source/dev/dev/checker.py` | Modify | `_check_manifest` 新增對選填 `"release"` 欄位 (`type`, `urgency`, `summary`) 之型別與非空字串校驗 |
| `ys_codebase/source/dev/scripts/cli.py` | Modify | `_normalize_bags` 補齊新選項；新增 `index_patch` 命令；為 `release` 與 `release_git` 補齊 `--type`、`--urgency`、`--summary` |
| `ys_codebase/source/dev/contributes/core.json` | Modify | 註冊 `dev index-patch` 命令契約，並更新 `dev release` / `dev release-git` 選項描述 |
| `ys_codebase/source/dev/contributes/_manifest.md` | Modify | 同步更新 `dev` CLI 貢獻契約文檔 |
| `ys_codebase/config/agents-workflow/skills/bump-revision/SKILL.md` | Modify | 擴充 `/bump-revision` 技能支援詢問或帶入 `--type`、`--urgency`、`--summary` 發布元數據 |
| `ys_codebase/source/core/tests/test_update_checker.py` | Modify | 新增跨版本（含 `pruned`）`critical` 攔截、未知 `type`/`urgency` 向前相容與不相容 `core` 版本過濾測試 |
| `ys_codebase/source/core/tests/test_distribution_lifecycle.py` | Modify | 新增 `index.json["releases"]` 依賴覆寫、`act_solve_deps` 對 `core` 依賴攔截、`cmd_update` 相容版本降級與 `mirror://` 離線 `reload` 冪等覆寫測試 |
| `ys_codebase/source/dev/tests/test_release_pipeline.py` | Modify | 新增 `Releaser.patch_release_index`、`release_module` 雙軌元數據寫入與 `Checker._check_manifest` `"release"` 欄位校驗測試 |
| `docs/dev/topics/release_governance.md` | Modify | 補充 `dev index-patch` 事後修補、雙軌發布元數據與跨版本 `critical` 告警機制說明 |
| `docs/dev/README.md` | Modify | 補充 `dev index-patch` 與 `release` 元數據參數說明 |
| `docs/core/DESIGN_NOTES.md` | Modify | 補充 `index.json["releases"]` 依賴覆寫、`mirror://` 離線快取與跨版本更新嚴重度聚合設計筆記 |
| `CHANGELOG.md` | Modify | 記錄 `sub_02` 版本相容性事後修正與釋出元數據治理變更 |

### 2.3 架構決策記錄 (Architecture Decision Records)

- **[P02:DR-01] 已安裝版本 `.build` 後綴相容性正規化**：在 `AtomicEngine` 與 `UpdateChecker` 判斷已安裝之 `core`（如 `1.2.0.build`）是否滿足依賴約束（如 `>=1.2.0`）時，將 `.build` 後綴剝離後作為正式版號比對，確保母倉 Dogfooding 環境與正式環境行為一致。
- **[P02:DR-02] 跨版本嚴重度聚合納管 `pruned` 版本**：`UpdateChecker` 聚合 `(cur_ver, latest_ver]` 區間時，直接遍歷 `index.json["releases"]` 字典而非僅遍歷 `index.json["versions"]`，確保即使帶 `critical` 的中間版本已被滑動視窗標為 `pruned`，舊版使用者仍能收到 `[CRITICAL UPDATE]` 告警。

---

## 3. 介面契約與 API 簽名 (P03)

### 3.1 介面契約與核心簽名 (Interface Inventory & Method Signatures)

```python
# ys_codebase/source/core/core/engine.py
class AtomicEngine:
    def _get_installed_core_version_for_compat(self) -> Optional[str]: ...
    def _is_dependencies_compatible_with_env(self, deps: Dict[str, Any]) -> bool: ...
    def _cache_release_index_to_mirror(self, module_name: str, index_data: Dict[str, Any]) -> None: ...
    def _apply_release_index_override_to_staging(self, mod: str, ver: str, staging_dir: str) -> None: ...

# ys_codebase/source/core/core/update_checker.py
KNOWN_URGENCIES: Dict[str, int] = {"optional": 1, "recommended": 2, "critical": 3}
def normalize_release_metadata(entry: Optional[Dict[str, Any]]) -> Dict[str, Any]: ...

class UpdateChecker:
    def _fetch_module_update_candidate(
        self, mod_name: str, current_ver: str, provider_url: str, installed_core_ver: Optional[str] = None
    ) -> Optional[Dict[str, Any]]: ...

# ys_codebase/source/dev/dev/releaser.py
class Releaser:
    def release_module(
        self,
        module_name: str,
        force: bool = False,
        _skip_check: bool = False,
        release_meta: Optional[Dict[str, str]] = None,
    ) -> Tuple[bool, str]: ...
    def release_git(
        self,
        module_name: str,
        commit_msg: str,
        force: bool = False,
        release_meta: Optional[Dict[str, str]] = None,
    ) -> Tuple[bool, str]: ...
    def patch_release_index(
        self,
        module_name: str,
        version: str,
        dependencies: Optional[Dict[str, str]] = None,
        status: Optional[str] = None,
        release_type: Optional[str] = None,
        urgency: Optional[str] = None,
        summary: Optional[str] = None,
    ) -> Tuple[bool, str]: ...
```

- **錯誤與例外契約 (Error & Exception Contracts)**：
  - `act_solve_deps` 當 `dep_name == "core"` 且當前已安裝 `core` 版本不滿足 `dep_ver` 時，拋出 `RuntimeError(f"Cannot resolve dependency for '{mod_name}': required core version '{dep_ver}' is not satisfied by installed core@{installed_core_ver}.")`。
  - `Releaser.patch_release_index` 遇到無效 `status`（非 `active`/`pruned`）或無效版號格式時，回傳 `(False, "<error message>")`，由 CLI 印出錯誤並回傳非零狀態碼 `1`。
- **階段決策紀錄**：`[P03:DR-01]` `Releaser.release_module` 與 `release_git` 新增之 `release_meta` 設為預設 `None` 之選填參數，100% 相容既有呼叫端。

---

## 4. 定稿審查與文檔衝擊規劃 (P04)

### 4.1 交叉驗證與靈魂拷問 (Cross-Validation & Resilience Review)

- [x] **需求對齊**：FR-01 ~ FR-04 完整映射至 `core` 與 `dev` 介面簽名
- [x] **邊界防護**：EC-01 ~ EC-05 皆具備明確過濾、降級與離線快取策略
- [x] **依賴純淨**：100% 符合 NFR-01 與 NFR-02 約束
- **靈魂拷問與防護解法**：
  - *拷問 1：若開發者先用 `dev index-patch <mod> --ver=1.0.0.1 --dep="core:>=1.2.0"` 修正了歷史版本的依賴，之後又發布了新版本 `1.0.0.2` 觸發 `Builder._update_release_index`，原本在 `1.0.0.1` 修補的 `dependencies` 或 `urgency` 會不會被 `1.0.0.1.zip` 內的舊 `manifest.json` 覆蓋掉？*
    - **防護解法**：在 `Builder._update_release_index` 中，僅對本次新發布之 `new_version`（或尚未有 `dependencies` 的版本）從 `manifest_data` / `.zip` 提取依賴與元數據；對於已存在於 `existing_releases` 的歷史版本，嚴格保留其既有 `dependencies`、`type`、`urgency`、`summary` 欄位，僅根據滑動視窗結果更新其 `"status"` (`active` 或 `pruned`)。

### 4.2 知識庫文檔衝擊與交付規劃 (Documentation Impact Plan)

| 維度 | 文件路徑 | 變更類型 | 交付內容與重點 |
| :--- | :--- | :---: | :--- |
| **模組手冊** | `docs/dev/README.md`, `docs/dev/user_guide.md` | Modify | 新增 `dev index-patch` 指令與 `dev release` 元數據選項 (`--type`, `--urgency`, `--summary`) 說明 |
| **專題手冊** | `docs/dev/topics/release_governance.md` | Modify | 增補事後相容性修補 (`index-patch`)、雙軌元數據與跨版本 `[CRITICAL UPDATE]` 治理專節 |
| **設計決策** | `docs/core/DESIGN_NOTES.md`, `docs/dev/DESIGN_NOTES.md` | Modify | 登記 `index.json["releases"]` 依賴覆寫、`mirror://` 離線快取與跨版本嚴重度聚合設計筆記 |
| **微觀註解** | 源碼檔案 Docstrings | Modify | 更新 `engine.py`、`installer.py`、`update_checker.py`、`builder.py`、`releaser.py`、`checker.py` Docstring |
| **發布日誌** | `CHANGELOG.md` | Modify | 記錄 `sub_02` 變更摘要 |

- **決策定稿**：**[P04:DR-01]** 規格審查通過，進入實作與驗證階段。

---

## 5. 實作任務清單與偏差紀錄 (P05)

### 5.1 實作任務清單 (Task Breakdown)

- [x] **TASK-01**：實作 `core` 模組 `engine.py`（`index.json["releases"]` 依賴覆寫、候選相容性過濾、`core` 依賴檢核、`mirror://` 離線快取與 `reload` 覆寫）、`installer.py`（`cmd_update` 相容過濾與快取清除）及 `update_checker.py`（向前相容解析、跨版本 `critical` 聚合與警告橫幅）
- [x] **TASK-02**：實作 `dev` 模組 `builder.py`、`releaser.py` (`patch_release_index` 與 `release_meta` 雙軌寫入)、`checker.py` (`_check_manifest` `"release"` 校驗)、`scripts/cli.py`、`contributes/` 與 `bump-revision/SKILL.md`
- [x] **TASK-03**：新增並執行 `core` (`test_update_checker.py`, `test_distribution_lifecycle.py`) 與 `dev` (`test_release_pipeline.py`) 單元與邊界測試
- [x] **TASK-DOC**：更新 `docs/dev/topics/release_governance.md`、`docs/dev/README.md`、`docs/dev/user_guide.md`、`docs/core/DESIGN_NOTES.md`、`docs/dev/DESIGN_NOTES.md` 與 `CHANGELOG.md`

### 5.2 實作偏差紀錄表 (Implementation Deviations)

| 任務編號 | 偏差等級 | 偏離描述與決策理由 | 處置方式 / 記錄 |
| :--- | :---: | :--- | :--- |
| - | - | 無偏差 | - |

