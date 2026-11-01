# 自動連續推進綜合規格與實作紀錄 (Consolidated Auto Plan & Task Log)

> 功能名稱：存量發布遷移、新版本發布與 Git 歷史徹底淨化 (sub_03)  
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
| **FR-01** | 存量 38 個歷史發布包真實元數據考證與 `index.json` 完整回填 | 1. 掃描 `ys_codebase/release/` 全部 38 個存量 `.zip`，提取各包內 `manifest.json` 之 `dependencies`、修改時間戳，並交叉比對 Git Commit、`CHANGELOG.md` 與 `plans/archived/` 歸檔計畫，為全部 38 個歷史版本補齊真實之 `status`、`dependencies`、`type`、`urgency`、`summary`。<br/>2. 對已在 Commit `4e014d0` 打包之 `server@1.0.1.3`、`knowledge-db@1.1.2.3`、`agents-workflow@1.2.2.2`，不重壓 `.zip` 且不冗餘遞增版號，直接於 `index.json` 補齊 Issue #8 釋出元數據。 | P0 | [P00:DR-01] |
| **FR-02** | 本次變動資產（`yscb.py`、`core`、`dev`）之升版、正式發布與跨平台目錄鎖定三階段真偽鑑別加固 | 1. 將 `yscb.py` 之 `__version__` 升級為 `1.2.1.0`、`core` 升級為 `1.2.1.0`、`dev` 升級為 `1.1.3.0` (`dependencies.core: ">=1.2.1"`)，執行 `dev build`、`dev release` 與本機正式版安裝，確保 `yscb.config.json` 與 `source/<mod>/manifest.json` 100% 版號對齊。<br/>2. 於 `core/engine.py` (`_atomic_swap_dir`) 與 `yscb.py` (`_fetch_and_extract_zip`) 實作跨平台（POSIX `EACCES/EBUSY/EPERM` + Windows `winerror 5/32`）目錄鎖定三階段真偽鑑別（權限位元檢查 + 實機寫入探針 + 單檔失敗全量回滾之檔案級原子同步），並補強 `.build` 升版退回解析。 | P0 | [P00:DR-02], [P00:DR-04] |
| **FR-03** | 全專案外部備份、SHA256 校驗、母倉 `.gitignore` 切換、`git filter-repo` 歷史徹底淨化與 `releases` 孤兒分支建立 | 1. 完整備份全專案至 `/tmp/yscb_full_project_backup` 並獨立備份 36 個 Active `.zip` 與 5 份 `index.json` 至 `/tmp/yscb_release_backup`，完成 100% SHA256 與 Zip CRC 完整性校驗。<br/>2. 於根目錄 `.gitignore` 新增 `ys_codebase/release/**/*.zip`，執行 `git rm --cached 'ys_codebase/release/*/*.zip'`，使 `main` 分支僅追蹤 `ys_codebase/release/*/index.json`。<br/>3. 執行 `git filter-repo` 全歷史一次性清洗（移除二進位 `.zip`、早期解壓態發布目錄、`.modules/`、`.mirror/`、`.build/`、`.agents/` 等非源碼歷史產物）並執行 `git gc --prune=now --aggressive`。<br/>4. 驗證無 `.zip` 工作區下 `python yscb.py restore --force` 100% 自給自足還原成功，並將 36 個 Active `.zip` 與 5 份 `index.json` 寫入單層無父節點之 `releases` 孤兒分支。 | P0 | [P00:DR-03] |

### 1.2 邊界與異常情況 (Edge Cases & Failure Modes)

| 邊界編號 | 情境說明 | 預期防禦與處理行為 |
| :--- | :--- | :--- |
| **EC-01** | 跨系統容器掛載（Windows Host $\leftrightarrow$ Linux `virtiofs`）或 Windows 原生環境下，IDE / File Watcher 鎖定 `.modules/<mod>` 目錄句柄導致 `os.replace` 拋出 `PermissionError (EACCES)` | 三階段真偽鑑別器先檢查 `os.access` 權限位元並於目標目錄內執行 `.yscb_probe` 實機寫入探針；確認非真權限/I/O 故障後，自動轉入帶全量備份回滾之檔案級原子同步。 |
| **EC-02** | 目標目錄因磁碟空間耗盡 (`ENOSPC`)、唯讀掛載 (`EROFS`) 或真實權限不足導致寫入失敗 | 三階段鑑別器於階段一或階段二即判定為 `False`（或於階段三全量回滾），將原始 `OSError` / `PermissionError` 原封不動拋出，絕不靜默吞錯。 |
| **EC-03** | `git filter-repo` 預設移除 `origin` remote 且清除全部分支之被過濾路徑 | 先完成 `main` 分支清洗、重建 `origin` remote 並恢復 `.agents/` 物化產物後，最後才建立 `releases` 單層孤兒分支，避免 `releases` 分支內之 `.zip` 被洗除。 |

### 1.3 非功能需求 (Non-Functional Requirements)

| 需求編號 | 類別 | 指標與量化約束 |
| :--- | :--- | :--- |
| **NFR-01** | 歷史瘦身與純淨度 | `main` 分支歷史中 `ys_codebase/release/*/*.zip` 殘留數量降為 `0`，`.git/objects/pack` 體積顯著下降。 |
| **NFR-02** | 備份完整性 | 外部備份之 36 個 Active `.zip` 與 5 份 `index.json` 100% 通過 SHA256 與 `zipfile.testzip()` CRC 驗證。 |

### 1.4 知識庫與踩坑紀錄查閱 (Known Gotchas & CAUTIONs)

- **`[!CAUTION]` `virtiofs` 目錄重命名限制**：在 Windows 宿主機透過 `virtiofs` 掛載的工作區中，當子目錄被宿主機行程打開時，父目錄 `os.replace` 會回傳 `Errno 13 (EACCES)`，但內部單一檔案的 `os.replace` 完全正常。必須透過實機寫入探針鑑別真偽，嚴禁使用無差別的 `except Exception: pass`。
- **`[!CAUTION]` `git filter-repo` 與孤兒分支工序**：`git filter-repo` 預設作用於所有 refs，因此必須先對 `main` 執行 `git filter-repo`，完成後再建立含 `.zip` 的 `releases` 孤兒分支。

---

## 2. 架構設計與異動檔案清單 (P02)

### 2.1 模組架構與核心資料流 (Architecture & Data Flow)

```text
[Step 1: 存量元數據考證與回填]
  └── 38 個歷史 .zip (時間戳 + Commit + 歸檔計畫) -> 寫入 ys_codebase/release/{core,dev,server,knowledge-db,agents-workflow}/index.json

[Step 2: 三階段目錄鎖定鑑別與新版本發布]
  ├── core/engine.py & yscb.py: _is_dir_handle_locked_for_rename (Stage 1 位元 + Stage 2 探針) -> _inplace_atomic_sync_dir (Stage 3 備份與逐檔原子替換)
  └── 升版發布: yscb.py (1.2.1.0), core (1.2.1.0), dev (1.1.3.0) -> 滑動視窗保留 36 個 Active .zip

[Step 3 ~ 5: 外部備份、歷史淨化與孤兒分支建立]
  ├── 備份: /tmp/yscb_full_project_backup & /tmp/yscb_release_backup (SHA256 + CRC 100% 驗證)
  ├── 脫鉤: .gitignore 加入 ys_codebase/release/**/*.zip + git rm --cached
  ├── 清洗: git filter-repo + git gc --prune=now --aggressive + restore --force 自給自足驗證
  └── 孤兒分支: 建立無父節點之本地 releases 孤兒分支 (含 36 個 Active .zip 與 5 份 index.json)
```

### 2.2 受影響與新建檔案清單 (Impacted & New Files Inventory)

| 檔案路徑 | 類型 | 職責與變更說明 |
| :--- | :---: | :--- |
| `ys_codebase/release/{core,dev,server,knowledge-db,agents-workflow}/index.json` | Modify | 完整回填全部歷史版本與本次新版本 (`core@1.2.1.0`, `dev@1.1.3.0`) 之 `status`、`dependencies`、`type`、`urgency`、`summary` |
| `yscb.py` | Modify | `__version__` 升為 `1.2.1.0`；新增 `_is_dir_handle_locked_for_rename`、`_inplace_atomic_sync_dir` 與 `.build` 升版退回解析 |
| `ys_codebase/source/core/manifest.json` | Modify | 版本號由 `1.2.0.2` 升級為 `1.2.1.0` |
| `ys_codebase/source/core/core/engine.py` | Modify | 新增 `_is_dir_handle_locked_for_rename` 與 `_inplace_atomic_sync_dir` 三階段鑑別與全有全無檔案級原子同步 |
| `ys_codebase/source/core/core/installer.py` | Modify | `_restore_module_package` 支援 `.build` 版本升版後自動匹配最新 `.build.zip` 並同步更新組態 |
| `ys_codebase/source/core/tests/test_engine.py` | Modify | 新增 `test_atomic_swap_dir_three_stage_probe_and_inplace_sync_rollback` 測試 |
| `ys_codebase/source/dev/manifest.json` | Modify | 版本號由 `1.1.2.2` 升級為 `1.1.3.0`，`dependencies.core` 升級為 `>=1.2.1` |
| `.gitignore` | Modify | 新增 `ys_codebase/release/**/*.zip` 忽略規則 |
| `docs/core/DESIGN_NOTES.md` | Modify | 增補跨平台目錄鎖定三階段真偽鑑別與檔案級原子同步設計筆記 |
| `CHANGELOG.md` | Modify | 記錄 `sub_03` 存量遷移、新版發布、三階段目錄鎖定鑑別與 Git 歷史徹底淨化成果 |

### 2.3 架構決策記錄 (Architecture Decision Records)

- **[P02:DR-01] 三階段目錄鎖定真偽鑑別與全有全無回滾**：結合 `os.access` 權限位元檢查、目標目錄內 `.yscb_probe` 實機寫入/替換探針、以及 `.old_backup_*` 預備份回滾，確保僅在「目錄句柄被宿主機鎖定但內部檔案可正常原子替換」時轉入檔案級同步，100% 杜絕吞掉真實權限或磁碟錯誤。

---

## 3. 介面契約與 API 簽名 (P03)

### 3.1 介面契約與核心簽名 (Interface Inventory & Method Signatures)

```python
# ys_codebase/source/core/core/engine.py & yscb.py
def _is_dir_handle_locked_for_rename(err: OSError, parent_dir: str, target_dir: str) -> bool: ...
def _inplace_atomic_sync_dir(staging_dir: str, target_dir: str) -> None: ...
def _atomic_swap_dir(
    staging_dir: str,
    target_dir: str,
    retries: int = 3,
    retry_delay: float = 0.05,
) -> None: ...
```

- **錯誤與例外契約 (Error & Exception Contracts)**：
  - 若 `_is_dir_handle_locked_for_rename` 回傳 `False`（如 `ENOSPC`、`EROFS`、權限位元不足或寫入探針失敗），`_atomic_swap_dir` 直接將原始 `OSError` / `PermissionError` 拋出。
  - 若 `_inplace_atomic_sync_dir` 執行期間任一檔案寫入或替換失敗，立即自 `backup_dir` 還原所有已變更檔案並重新拋出原始例外。
- **階段決策紀錄**：`[P03:DR-01]` `_atomic_swap_dir` 與 `_fetch_and_extract_zip` 外部簽名維持不變，對呼叫端完全透明。

---

## 4. 定稿審查與文檔衝擊規劃 (P04)

### 4.1 交叉驗證與靈魂拷問 (Cross-Validation & Resilience Review)

- [x] **需求對齊**：FR-01 ~ FR-03 完整涵蓋存量元數據回填、新版本發布、三階段目錄鎖定鑑別與 Git 歷史淨化
- [x] **邊界防護**：EC-01 ~ EC-03 皆具備自動化測試與實機 SHA256 備份雙重保障
- [x] **依賴純淨**：100% Python 標準庫實作，零第三方運行時依賴
- **靈魂拷問與防護解法**：
  - *拷問 1：當 `main` 分支移除所有 `ys_codebase/release/*/*.zip` 後，開發者在母倉執行 `python yscb.py restore --force`（且 `.mirror/` 與 `.build/` 為空）時，是否會因為找不到 `.zip` 而失敗？*
    - **防護解法**：透過 `yscb.config.json` 中 5 大模組版本與 `ys_codebase/source/<mod>/manifest.json` 100% 嚴格對齊，`_restore_module_package` 自動觸發本地同版本 `source/<mod>` 動態打包自給自足機制，已在 Step 3 實機驗證 5/5 模組 100% 還原成功。

### 4.2 知識庫文檔衝擊與交付規劃 (Documentation Impact Plan)

| 維度 | 文件路徑 | 變更類型 | 交付內容與重點 |
| :--- | :--- | :---: | :--- |
| **模組手冊** | `docs/dev/README.md` | No-Op | 已於 `sub_01` 與 `sub_02` 完整更新發布架構說明 |
| **專題手冊** | `docs/dev/topics/release_governance.md` | No-Op | 已於 `sub_01` 與 `sub_02` 完整涵蓋單層 `releases` 孤兒分支與元數據治理 |
| **設計決策** | `docs/core/DESIGN_NOTES.md` | Modify | 於 `[DN-15]` 增補跨平台目錄鎖定三階段真偽鑑別與檔案級原子同步設計紀錄 |
| **微觀註解** | 源碼檔案 Docstrings | Modify | 為 `_is_dir_handle_locked_for_rename` 與 `_inplace_atomic_sync_dir` 撰寫完整 Docstring |
| **發布日誌** | `CHANGELOG.md` | Modify | 記錄 `sub_03` 存量元數據回填、新版本發布、三階段目錄鎖定鑑別與 Git 歷史淨化 |

- **決策定稿**：**[P04:DR-01]** 規格審查通過，完成實作與測試驗證。

---

## 5. 實作任務清單與偏差紀錄 (P05)

### 5.1 實作任務清單 (Task Breakdown)

- [x] **TASK-01**：考證全部 38 個存量 `.zip` 歷史版本並回填 `ys_codebase/release/{core,dev,server,knowledge-db,agents-workflow}/index.json`
- [x] **TASK-02**：實作跨平台目錄鎖定三階段真偽鑑別與檔案級原子同步，升級並發布 `yscb.py@1.2.1.0`、`core@1.2.1.0`、`dev@1.1.3.0`，通過 `core` (214/214) 與 `dev` (82/82) 測試
- [x] **TASK-03**：執行全專案與發布庫外部備份（通過 SHA256 與 CRC 校驗）、切換 `.gitignore`、驗證無 `.zip` 下 `restore --force` 自給自足還原、執行 `git filter-repo` 歷史淨化並建立 `releases` 孤兒分支
- [x] **TASK-DOC**：更新 `docs/core/DESIGN_NOTES.md`、`CHANGELOG.md` 與 `umbrella_overview.md`

### 5.2 實作偏差紀錄表 (Implementation Deviations)

| 任務編號 | 偏差等級 | 偏離描述與決策理由 | 處置方式 / 記錄 |
| :--- | :---: | :--- | :--- |
| **TASK-02** | Minor | 於實機安裝 `core@1.2.1.0` 時遭遇 `virtiofs` 目錄句柄鎖定 (`Errno 13`)，經 `/discuss` 開發者拍板新增三階段真偽鑑別與檔案級原子同步 | 已記錄於 `[P00:DR-04]` 並補齊單元測試 `test_atomic_swap_dir_three_stage_probe_and_inplace_sync_rollback` |
