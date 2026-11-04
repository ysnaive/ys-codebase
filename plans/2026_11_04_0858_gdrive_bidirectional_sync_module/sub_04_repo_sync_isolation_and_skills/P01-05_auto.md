# 自動連續推進綜合規格與實作紀錄 (Consolidated Auto Plan & Task Log)

> 功能名稱：`module:gdrive-support` `repo_sync` 組態與子目錄隔離、雙層 `README.md` 本地狀態快取軟合併及本地/外部雙軌分離 Skills (`sub_04_repo_sync_isolation_and_skills`)  
> 建立日期：2026-11-04  
> 所屬主計畫：`2026_11_04_0858_gdrive_bidirectional_sync_module`  
> 狀態：Completed  
> 模型：Gemini 4 Argon (Low)  

> 依據 P00：[P00_discuss.md](./P00_discuss.md)  
> 模板版本：v1.0  

---

## 1. 需求規格與邊界契約 (P01)

### 1.1 功能需求清單 (Functional Requirements)

| 需求編號 | 需求名稱 | 詳細規格與驗收條件 (Acceptance Criteria) | 優先級 | 對應 P00 語意 |
| :--- | :--- | :--- | :---: | :--- |
| **FR-01** | `repo_sync` 巢狀組態結構與 `enable: false` 總開關 | 於 `configurable/_format.json`、`configurable/config.project.json` 與 `config.py` 將分支與同步組態收納至 `"repo_sync"` 物件（`enable: bool = False`, `repo_sync_root: str = "repo"`, `active_branch: str = "main"`, `auto_sync: bool = False`, `poll_interval_sec: float = 30.0`, `pull_delete_default: bool = False`, `push_delete_default: bool = False`）；當 `repo_sync.enable == False` 時，`auto_sync` 強制為 `False`，且所有 `repo_sync` 內部設定皆不生效。 | P0 | [P00:DR-01] |
| **FR-02** | `repo_sync.enable: false` 命令攔截、`<root>/<repo_sync_root>/` 雲端物理隔離與原生 30 天垃圾桶 | 當 `repo_sync.enable == False` 時，呼叫 `init`, `branch`, `checkout`, `pull`, `push`, `sync` 均拋出 `GDriveRepoSyncDisabledError` 拒絕執行，僅允許原子操作（`status`, `auth`, `ls`, `get`, `put`, `rm`, `mkdir`, `shortcut`）；當 `repo_sync.enable == True` 時，`SyncCoordinator` 所有倉庫元數據與分支一律建立於 `<root_folder_id>/<repo_sync_root>/`（預設 `repo/`）下（`repo/.yscb_gdrive.json`、`repo/README.md`、`repo/.history/`、`repo/.trash/`、`repo/main/`、`repo/<branch>/`）；雲端刪除直接移入 Google Drive 原生 30 天垃圾桶 (`trashed=true`)，且本地 `sync/pull/push/branch delete` 自動清空外部 AI 放入 `repo/.trash/` 之暫存檔。 | P0 | [P00:DR-01], [P00:DR-02] |
| **FR-03** | 本地快取驅動之頂層 `root/README.md` 軟合併 / 軟移除與 `<repo_sync_root>/README.md` 雙層維護 | 於本地 `cache://gdrive-support/readme_sync_state.json` 記錄最後啟用狀態 `(enable, repo_sync_root)`；當偵測到狀態與本地快取不一致（或首次初始化）時，自動同步頂層 `root/README.md`：`enable == True` 時建立或以 `<!-- === YSCB GDRIVE REPO_SYNC BEGIN === --> ... <!-- === YSCB GDRIVE REPO_SYNC END === -->` 軟合併託管區塊（保留非託管內容）；`enable == False` 時剝除託管區塊，若剩餘內容為空則移入原生垃圾桶（沙盒為 `.trash/`）移除，否則原地寫回保留非託管內容（軟移除）。 | P0 | [P00:DR-02] |
| **FR-04** | 本地 `agents-workflow` Skill 與外部雲端隨包 Skill 雙軌分離 | 建立本地端技能 `ys_codebase/source/gdrive-support/assets/skills/gdrive-local-ops/SKILL.md` 與導引 `assets/{usage_guide,config_guide}.md`，並透過 `contributes/agents-workflow.json` 注入本地工作流；同時建立獨立之外部雲端隨包技能 `ys_codebase/source/gdrive-support/assets/external_cloud_skill/SKILL.md`（不注入本地 `agents-workflow`），供外部 AI / 雲端 Web Gemini 操作雲端目錄時遵循。 | P0 | [P00:DR-03] |

### 1.2 邊界與異常情況 (Edge Cases & Failure Modes)

| 邊界編號 | 情境說明 | 預期防禦與處理行為 |
| :--- | :--- | :--- |
| **EC-01** | `repo_sync.enable: false` 時使用者或腳本嘗試執行 `init`, `branch`, `checkout`, `pull`, `push`, `sync` | 立即拋出 `GDriveRepoSyncDisabledError`（CLI 回傳非零退出碼 `1` 並提示需將 `repo_sync.enable` 設為 `true`），絕不觸碰雲端或本地工作區。 |
| **EC-02** | 頂層 `root/README.md` 已存在且包含使用者手寫之非託管內容，隨後 `repo_sync.enable` 由 `false -> true -> false` 切換 | `false -> true` 時保留手寫內容並附加/更新託管區塊（軟合併）；`true -> false` 時僅剝除託管區塊並完整保留手寫內容（軟移除），絕不誤刪使用者手寫說明。 |
| **EC-03** | 頂層 `root/README.md` 僅包含 YSCB 託管區塊（無其他手寫內容），隨後 `repo_sync.enable` 由 `true -> false` 切換 | 剝除託管區塊後剩餘非空白內容為空，自動呼叫 `transport.trash_file("README.md")` 將頂層 `README.md` 移入 `.trash/`。 |
| **EC-04** | `root/` 頂層已存放使用者不拉到本地同步之純雲端檔案（如 `root/archive/design.psd`），此時於 `repo_sync.enable: true` 下執行 `init`、`sync`、`branch` 或 `checkout` | 因為同步倉完全隔離於 `root/repo_sync/` 子目錄內，外層 `root/archive/design.psd` 既不會觸發 `GDriveRepoUninitializedError`，也不會被拉到本地或被 `checkout` / `--delete` 影響。 |

### 1.3 非功能需求 (Non-Functional Requirements)

| 需求編號 | 類別 | 指標與量化約束 |
| :--- | :--- | :--- |
| **NFR-01** | 零額外網路輪詢 | 當 `repo_sync.enable` 未發生變動時，本地快取 `readme_sync_state.json` 比對短路，對頂層 `root/README.md` 產生 `0` 次額外雲端 API 請求。 |
| **NFR-02** | 測試邊界鐵律 | 自動化測試 100% 基於 `LocalSandboxTransport` 執行，零外部 Google Drive API test cases。 |

### 1.4 知識庫與踩坑紀錄查閱 (Known Gotchas & CAUTIONs)

- **`[!NOTE]`** 修改模組內 `contributes/agents-workflow.json` 或 `assets/` 後，需先 `install gdrive-support@build --force` 更新 `module://` 運行空間，再執行 `agents-workflow compile` 與 `release --force`。

---

## 2. 架構設計與異動檔案清單 (P02)

### 2.1 模組架構與核心資料流 (Architecture & Data Flow)

```text
<root_folder_id>/ (Atomic API Root: ls / get / put / rm / mkdir / shortcut)
  ├── README.md (Root README: Soft-merged / Soft-removed on repo_sync.enable state transition)
  ├── <pure_cloud_files...> (Never pulled by repo_sync)
  └── <repo_sync_root>/ (Default: repo/ — Managed only when repo_sync.enable == True)
        ├── .yscb_gdrive.json
        ├── README.md (Repo-sync dedicated README)
        ├── .history/
        ├── .trash/ (External AI staging buffer; auto-flushed into native 30-day Trash on local sync)
        ├── main/
        └── <branch>/
```

### 2.2 受影響與新建檔案清單 (Impacted & New Files Inventory)

| 檔案路徑 | 類型 | 職責與變更說明 |
| :--- | :---: | :--- |
| `ys_codebase/source/gdrive-support/configurable/_format.json` | Modify | 將分支與同步欄位收納至 `"repo_sync"` 巢狀結構 |
| `ys_codebase/source/gdrive-support/configurable/config.project.json` | Modify | 更新預設組態範本為 `"repo_sync": {"enable": false, ...}` |
| `ys_codebase/config/gdrive-support/config.project.json` | Modify | 同步更新專案組態為新 `"repo_sync"` 結構 |
| `ys_codebase/source/gdrive-support/gdrive_support/config.py` | Modify | 新增 `GDriveRepoSyncDisabledError`、`RepoSyncConfig` 與 `GDriveConfig.repo_sync_enabled` 解析，支援寫回 `repo_sync.active_branch` |
| `ys_codebase/source/gdrive-support/gdrive_support/coordinator.py` | Modify | 將同步倉根路徑隔離至 `repo_sync/`、入口強制檢查 `ensure_repo_sync_enabled()`，並實作頂層 `root/README.md` 軟合併/軟移除與本地狀態快取 `reconcile_root_readme_state()` |
| `ys_codebase/source/gdrive-support/gdrive_support/__init__.py` | Modify | 匯出 `GDriveRepoSyncDisabledError`、`RepoSyncConfig`、`merge_root_readme_block`、`strip_root_readme_block` |
| `ys_codebase/source/gdrive-support/scripts/cli.py` | Modify | 於 CLI 整合本地狀態快取 `README.md` 變動檢查與 `repo_sync.enable` 狀態顯示 |
| `ys_codebase/source/gdrive-support/contributes/agents-workflow.json` | New | 向本地 `agents-workflow` 匯出 `gdrive-local-ops` 技能與 `usage_guide` / `config_guide` |
| `ys_codebase/source/gdrive-support/contributes/_manifest.md` | Modify | 補充 `agents-workflow.json` 貢獻說明 |
| `ys_codebase/source/gdrive-support/assets/skills/gdrive-local-ops/SKILL.md` | New | 給本地 Agent 操作 `module:gdrive-support`（區分純雲端原子存取與 `repo_sync` 同步）之技能 |
| `ys_codebase/source/gdrive-support/assets/external_cloud_skill/SKILL.md` | New | 給外部雲端 Agent / Web Gemini 操作雲端目錄結構之隨包獨立技能 |
| `ys_codebase/source/gdrive-support/assets/usage_guide.md` | New | `/how-to-yscb` 模組導覽片段 |
| `ys_codebase/source/gdrive-support/assets/config_guide.md` | New | `/how-to-config-yscb` 組態診斷片段 |
| `ys_codebase/source/gdrive-support/tests/test_atomic_api_and_config.py` | Modify | 更新組態測試並驗證 `repo_sync` 結構解析 |
| `ys_codebase/source/gdrive-support/tests/test_branch_and_sync_engine.py` | Modify | 驗證 `repo_sync/` 子目錄隔離、`enable: false` 攔截、以及頂層 `root/README.md` 軟合併/軟移除與本地快取狀態機 |
| `ys_codebase/source/gdrive-support/README.md` | Modify | 同步更新模組隨包手冊 |
| `ys_codebase/source/gdrive-support/USAGE.md` | Modify | 同步更新 CLI 使用手冊 |
| `docs/gdrive-support/README.md` | Modify | 同步更新系統知識庫手冊 |

### 2.3 架構決策記錄 (Architecture Decision Records)

- **[P02:DR-01]** 頂層 `root/README.md` 託管區塊採用 `<!-- === YSCB GDRIVE REPO_SYNC BEGIN === -->` 與 `<!-- === YSCB GDRIVE REPO_SYNC END === -->` 定界符，透過純函數 `merge_root_readme_block(existing_text, block_body)` 與 `strip_root_readme_block(existing_text)` 處理軟合併與軟移除，確保可 100% 離線單元測試。

---

## 3. 介面契約與 API 簽名 (P03)

### 3.1 介面契約與核心簽名 (Interface Inventory & Method Signatures)

```python
# gdrive_support/config.py
DEFAULT_REPO_SYNC_ROOT = "repo"

class GDriveRepoSyncDisabledError(GDriveError):
    """Raised when a repo_sync operation (init/branch/checkout/pull/push/sync) is invoked while repo_sync.enable is False."""

# gdrive_support/coordinator.py
REPO_SYNC_ROOT_PREFIX = DEFAULT_REPO_SYNC_ROOT
ROOT_README_BEGIN_MARKER = "<!-- === YSCB GDRIVE REPO_SYNC BEGIN === -->"
ROOT_README_END_MARKER = "<!-- === YSCB GDRIVE REPO_SYNC END === -->"

def merge_root_readme_block(
    existing_text: str,
    managed_body: str = "",
    *,
    repo_sync_root: str = DEFAULT_REPO_SYNC_ROOT,
) -> str: ...
def strip_root_readme_block(existing_text: str) -> str: ...
```

- **錯誤與例外契約 (Error & Exception Contracts)**：
  - `GDriveRepoSyncDisabledError`：當 `config.repo_sync_enabled is False` 時呼叫任何 `SyncCoordinator` 同步或分支方法即刻拋出。
- **階段決策紀錄**：`[P03:DR-01]` 本地快取檔 `cache://gdrive-support/readme_sync_state.json` 以 `root_folder_id`（或 `sandbox_dir`）為 key 記錄 `{"states": {"<key>": bool}}`，僅在 `last_state != current_enable`（且首次若為 `False` 則僅記錄 `False` 免觸發雲端請求；若首次為 `True` 則觸發軟合併並記錄 `True`）時執行雲端 `root/README.md` 更新。

---

## 4. 定稿審查與文檔衝擊規劃 (P04)

### 4.1 交叉驗證與靈魂拷問 (Cross-Validation & Resilience Review)

- [x] **需求對齊**：FR-01 ~ FR-04 皆已於介面簽名與實作中完整對齊
- [x] **邊界防護**：EC-01 ~ EC-04 皆有具體錯誤攔截與降級策略
- [x] **依賴純淨**：100% 符合 NFR 指標約束
- **靈魂拷問與防護解法**：
  - *Q：若一專案剛安裝 `gdrive-support`（預設 `repo_sync.enable: false`），首次執行 `gdrive ls` 時會不會去雲端檢查或刪除 `root/README.md`？*
  - *A*：不會！當本地快取尚無該 `target_key` 的紀錄且當前 `repo_sync.enable == False` 時，快取直接初始化記錄為 `False` 而不發起任何 `README.md` 雲端操作；唯有當 `enable` 設為 `True`（觸發建立/軟合併），或曾經為 `True` 後改回 `False`（觸發移除/軟移除）時，才會操作雲端 `root/README.md`。

### 4.2 知識庫文檔衝擊與交付規劃 (Documentation Impact Plan)

| 維度 | 文件路徑 | 變更類型 | 交付內容與重點 |
| :--- | :--- | :---: | :--- |
| **模組手冊** | `docs/gdrive-support/README.md` | Modify | 更新 `root/` 純雲端區 vs `root/repo_sync/` 同步倉架構、雙層 `README.md` 軟合併與雙軌 Skills 說明 |
| **專題手冊** | `ys_codebase/source/gdrive-support/USAGE.md` | Modify | 更新組態範例與指令守門說明 |
| **設計決策** | `docs/gdrive-support/DESIGN_NOTES.md` | N/A | 整合於 `docs/gdrive-support/README.md` |
| **微觀註解** | `gdrive_support/*.py` Docstrings | Modify | 同步更新公開 API Docstring |
| **發布日誌** | `CHANGELOG.md` | Modify | 記錄 `sub_04_repo_sync_isolation_and_skills` 變更摘要 |

- **決策定稿**：**[P04:DR-01]** 確認通過。

---

## 5. 實作任務清單與偏差紀錄 (P05)

### 5.1 實作任務清單 (Task Breakdown)

- [x] **TASK-01**：更新 `configurable/_format.json`、`configurable/config.project.json` 與 `gdrive_support/config.py`（支援 `repo_sync` 巢狀組態與 `GDriveRepoSyncDisabledError`）
- [x] **TASK-02**：更新 `gdrive_support/coordinator.py` 與 `scripts/cli.py`（將同步倉隔離至 `repo_sync/`、實作 `ensure_repo_sync_enabled()` 守門、頂層 `root/README.md` 軟合併/軟移除與本地狀態快取）
- [x] **TASK-03**：建立本地 `agents-workflow` 技能 (`assets/skills/gdrive-local-ops/SKILL.md`, `contributes/agents-workflow.json`, `assets/{usage_guide,config_guide}.md`) 與外部雲端隨包技能 (`assets/external_cloud_skill/SKILL.md`)
- [x] **TASK-04**：更新本地沙盒測試 (`tests/test_atomic_api_and_config.py`, `tests/test_branch_and_sync_engine.py`) 與三層文檔，通過 `dev check` 與 `dev test`

### 5.2 實作偏差與決策紀錄 (Implementation Deviations)

- **[P05:DR-01]** 無架構偏差；為避免單元測試傳入臨時 `--sandbox-dir` 時寫入全域 `cache://gdrive-support/readme_sync_state.json`，於 `scripts/cli.py` 之 `_maybe_reconcile_root_readme()` 針對帶有 `--sandbox-dir` 覆寫之呼叫將狀態快取導向 `<sandbox_dir>/.yscb_readme_state.json`。
