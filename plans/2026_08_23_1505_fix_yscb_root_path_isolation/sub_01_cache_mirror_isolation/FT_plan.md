# Fast Track 變更計畫 (Fast Track Plan)

> 功能名稱：sub_01_cache_mirror_isolation (Git 遠端倉庫鏡像快取目錄空間隔離)  
> 建立日期：2026-08-23  
> 所屬主計畫：[2026_08_23_1505_fix_yscb_root_path_isolation](../P00_semantic_requirements.md)  
> 依據 P00：[P00_semantic_requirements.md](../P00_semantic_requirements.md)  
> 狀態：Completed  
> 擴充項目：dogfooding_pipeline_ext  
> 模板版本：v1.4  

---

## FT-1：變更說明

### P00 語意需求摘要（引用自 P00）

- **計畫類型**：Refactor / Bug Fix / Architecture
- **核心訴求**：將遠端 Git 倉庫 Shallow Clone 快取目錄由 `yscb://.yscb_cache/` 根目錄收斂隔離至 `yscb://.yscb_cache/mirror/` 專屬子目錄，徹底消除與模組執行期快取 (`cache://`)、備份快照 (`backup/`) 及暫存區 (`temp://`) 的空間混雜與誤刪隱患。
- **P00 關鍵情境 / 復現步驟摘要**：
  > 於主計畫 Phase 6 UX 驗證期間發現：`GitRemoteClient` 將遠端 Git 倉庫直接 Clone 於 `.yscb_cache` 根目錄，導致 `.yscb_cache/modules/` 與 `.yscb_cache/backup/` 被 Git 視為 Working Tree Untracked Files；當遠端同步失敗觸發 `sync_cache(force_refresh=True)` 時，`shutil.rmtree(self.cache_dir)` 會將所有模組快取與歷史快照備份一併抹除。

### 修改動機

1. **空間職責分離 (Spatial Separation)**：落實 `yscb://.yscb_cache/` 內部 4 大目錄的清晰職責邊界（`mirror/`、`modules/`、`backup/`、`tmp/`）。
2. **防範災難性快取抹除**：確保遠端 Git 倉庫同步刷新或異常重試時，僅清理 `mirror/` 目錄，絕對不波及使用者的模組執行期快取與備份快照。
3. **消除 Git Working Tree 污染**：使 Git Clone 的本地倉庫 Working Tree 保持純淨，不將其他子目錄視為未追蹤檔案。

### 修改內容

1. 修改 [`ys_codebase/yscb_installer.py`](file:///d:/repos/ys_codebase/ys_codebase/yscb_installer.py) 的 `GitRemoteClient.__init__`，將 `self.cache_dir` 預設路徑設為 `root_dir / CACHE_DIRNAME / "mirror"`。
2. 調整 `ModuleManager._locate_module_dir`，使快取候選搜尋路徑對齊 `self.git_client.cache_dir`（即 `mirror/`）。
3. 同步調整 `test/test_installer.py`、`test/test_hardening.py` 中涉及快取鏡像路徑的測試案例與斷言。
4. 執行 Dogfooding 四步標準閉環流水線（`build --all` ➔ `run_regression.py` ➔ 同步根目錄起手腳本 ➔ 自引用部署）。

### 受影響的檔案和函式

| 檔案路徑 | 影響範圍 | 說明 |
|---------|---------|------|
| [`ys_codebase/yscb_installer.py`](file:///d:/repos/ys_codebase/ys_codebase/yscb_installer.py) | `GitRemoteClient.__init__`, `ModuleManager._locate_module_dir` | 隔離 Git 快取至 `mirror/` 子目錄 |
| [`test/test_installer.py`](file:///d:/repos/ys_codebase/test/test_installer.py) | `TestYSCBInstaller` | 更新涉及 `.yscb_cache` 鏡像路徑之單元測試斷言並新增 `test_18_git_remote_mirror_isolation` |
| [`test/test_hardening.py`](file:///d:/repos/ys_codebase/test/test_hardening.py) | `TestHardening` | 更新 Hardening 相關快取路徑測試斷言 |

### 專案擴充特化判定矩陣 (Extension Specialization Matrix)

| 擴充項目名稱 | 觸發模式 | 本計畫適用性判定 | 納入 / 排除具體理由 |
| :--- | :--- | :--- | :--- |
| `dogfooding_pipeline_ext` | `always` | ✅ 納入 (Included) | 本計畫涉及修改核心安裝器 `yscb_installer.py`，必須嚴格遵循三層空間隔離與 4-Stage 閉環流水線 |

### Decision Records

---

**[ARCH:DR-CACHE-02] `[NEW]` 遠端 Git 鏡像快取目錄空間隔離規範**
- 結論：所有透過 `GitRemoteClient` 進行之 `clone`、`pull`、`sync` 與快取發布物定位，其根目錄強制統一錨定至 `yscb://.yscb_cache/mirror/`，嚴禁佔用 `yscb://.yscb_cache/` 頂層根目錄。
- 理由：防止 Git 鏡像同步失敗時觸發 `rmtree` 誤刪 `modules/` 快取與 `backup/` 快照，並徹底杜絕 Git Working Tree 污染。

### 閉合確認 (Closing Confirmation)

- [x] 開發者已確認：目前討論已完整，同意採用方案 A 開立 Fast Track 子計畫實施

---

## FT-2：實作清單

- [x] **Task 1: 重構 `GitRemoteClient` 快取目錄** ([`ys_codebase/yscb_installer.py`](file:///d:/repos/ys_codebase/ys_codebase/yscb_installer.py))
  - [x] `self.cache_dir` 預設設為 `root_dir / CACHE_DIRNAME / "mirror"`
  - [x] 檢查 `sync_cache` 與 `push_changes` 確保安全建立並操作 `mirror/`
- [x] **Task 2: 更新 `ModuleManager` 模組來源探索** ([`ys_codebase/yscb_installer.py`](file:///d:/repos/ys_codebase/ys_codebase/yscb_installer.py))
  - [x] `_locate_module_dir` 對齊 `git_client.cache_dir` (`mirror/`)
- [x] **Task 3: 測試套件路徑對齊與驗證** ([`test/`](file:///d:/repos/ys_codebase/test/))
  - [x] 更新 `test_installer.py` 與 `test_hardening.py`
  - [x] 實機執行 `python -m unittest discover -s test`
- [x] **Task 4: Dogfooding 4-Stage 閉環執行**
  - [x] 遞進版本號（`installer` v2.3.1）
  - [x] `python yscb_cli.py installer build --all`
  - [x] `python test/run_regression.py` (77/77 全量測試 + E2E 100% Passed)
  - [x] 覆蓋同步根目錄起手腳本並執行自引用安裝部署

### 偏差記錄

| 等級 | 偏差內容 | 處理方式 |
|------|---------|---------|
| *(無偏差)* | - | - |

---

## FT-3：品質與 UX 審查

### 代碼清理

- [x] 移除所有 debug 輸出、未使用的變數、被註解掉的死代碼

### 測試與 UX 驗證

- [x] Agent CLI 自動化測試結果：已實機完成 `python test/run_regression.py` 並無 Error/Warning (77/77 + E2E 100% Passed)
- [x] 開發者 UX / 手動測試確認：開發者回覆「UX 驗證通過」或指示免測

### 命名規範

- [x] 所有新增/修改的命名符合專案命名規範

### 文檔與知識庫同步 (詳見 DocumentationStandards.md)

- [x] 新增或修改的 public API 已加上標準文檔註解
  → 操作：N/A：無 public API 變更
- [x] 涉及的模組/命名空間/套件對應之 `docs/` 文件已更新
  → 操作：已於 `AGENTS.md` 與 `AGENTS.template.md` 載明 4 大快取目錄職責規範
- [ ] 根目錄 `CHANGELOG.md` 已按 `global_changelog.md` 模板追加本次 Plan 之高階變更摘要
  → 操作：待主計畫與子計畫結案時一併追加
- [x] `docs/README.md` 根層知識地圖已同步更新
  → 操作：確認無需修改
- [x] 若發現坑點或工程妥協，已紀錄至對應模組之 `DESIGN_NOTES.md`
  → 操作：N/A

### Commit 訊息

```text
refactor(installer): isolate git remote cache to .yscb_cache/mirror

- update GitRemoteClient.cache_dir to .yscb_cache/mirror
- prevent git sync and refresh from wiping module runtime caches
- align test suites and pass 100% regression tests
```

### 變更摘要

已成功將遠端 Git 倉庫快取隔離至 `yscb://.yscb_cache/mirror/`，徹底分離 Git 倉庫鏡像與模組執行期快取/備份快照，消除潛在誤刪與 untracked files 污染風險。
