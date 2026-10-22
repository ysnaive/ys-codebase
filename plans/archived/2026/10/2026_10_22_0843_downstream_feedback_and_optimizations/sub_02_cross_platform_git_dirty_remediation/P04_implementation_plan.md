# 實作計畫與定稿審查書 (Implementation Plan & Review)

> 功能名稱：sub_02_cross_platform_git_dirty_remediation  
> 建立日期：2026-10-22  
> 所屬主計畫：2026_10_22_0843_downstream_feedback_and_optimizations  
> 狀態：Confirmed  
> 模型：Gemini 3.8 Flash (Medium)  

> 模板版本：v1.4  

---

## 1. 交叉驗證檢查清單 (Cross-Validation Checklist)

- [x] **需求對齊**：
  - `FR-01` (LF 正規化) 對應 `ReleasePublisher._get_source_file_sha1`
  - `FR-02` (Manifest 本地隔離與清理) 對應 `ReleasePublisher.PROJECT_MANIFEST_CACHE_URI` 與 `_migrate_legacy_storage_manifest`
  - `FR-03` (雙平台 extraPaths) 對應 `PipManager.get_cross_platform_site_packages_dirs` 與 `IdeProjector.sync_vscode_settings`
  - `FR-04` (移除 interpreter 託管寫入與清理舊值) 對應 `IdeProjector.sync_vscode_settings`
- [x] **邊界防護**：
  - `EC-01` (非 UTF-8 二進位檔) 在 `_get_source_file_sha1` 中有 `UnicodeDecodeError` 降級防護
  - `EC-02` (舊版 storage manifest 殘留) 在 `ReleasePublisher.release_all` 啟動階段自動遷移並物理清理
  - `EC-03` (使用者自訂直譯器保護) 在 `IdeProjector.sync_vscode_settings` 透過託管特徵檢查精確隔離，保留自訂值
  - `EC-04` (Zero-Touch 比對) 在 `sync_vscode_settings` 寫入前進行字串/JSON 等價比對，無異動則略過
- [x] **依賴純淨**：
  - 100% 依賴 Python 標準庫 (`hashlib`, `json`, `os`, `pathlib`)，符合 `NFR-02`
  - 跨平台雙機交替執行維持 Git Working Tree 乾淨，符合 `NFR-01`

---

## 2. 知識庫文檔衝擊與交付規劃 (Documentation Impact Plan)

| 維度 | 文件路徑 | 變更類型 | 交付內容與重點 |
| :--- | :--- | :---: | :--- |
| **模組手冊** | `docs/core/README.md` | Modify | 補充 `IdeProjector` 跨平台 IDE 投射與 Zero-Touch 機制 |
| **設計決策** | `docs/core/DESIGN_NOTES.md` | Modify | 新增 `[DN-10]` 記錄 IDE 雙平台路徑恆定性與直譯器託管解耦決策 |
| **設計決策** | `docs/agents-workflow/DESIGN_NOTES.md` | Modify | 補充 `[DN-AW-05]` 記錄資產 CRLF 換行符 LF 正規化與物化清單 cache 隔離決策 |
| **發布日誌** | CHANGELOG.md | Modify | 記錄跨平台 Git Working Tree 污染根治與雙平台 VSCode 恆定投射修復 |

---

## 3. 架構靈魂拷問 (Stress Test & Resilience Review)

> [?] **尖銳問題 1**：若開發者在 Windows 環境將某個 Python 二進位 wheel 或大型 zip 資產納入模組資產，`_get_source_file_sha1` 逐字解碼是否會損壞效能或引發記憶體爆炸？  
> [*] **防護解法**：`_get_source_file_sha1` 依舊維持分塊讀取（chunk size 64KB）機制；對 chunk 進行解碼與替換。同時 `(st_mtime_ns, st_size)` 快取優先命中機制仍持續生效，僅在 mtime 或大小改變時才重新計算。
>
> [?] **尖銳問題 2**：若使用者原先已在 VSCode 手動指定了全域的 Python 直譯器（例如 `/usr/bin/python3` 或 `conda` 環境），YSCB 清理舊託管值時會不會把使用者的設定清空？  
> [*] **防護解法**：`sync_vscode_settings` 僅在 `settings["python.defaultInterpreterPath"]` 等於前次 `_yscb_managed["defaultInterpreterPath"]` 或包含 `.yscb/.venv` 特徵時才執行清除；若為其他自訂路徑則完好保留。

---

## 4. 實作任務清單 (Task Breakdown & Topological Sequence)

- [ ] **TASK-01**：~~增強 `.yscb/.gitignore` 忽略規則~~ 依 `[P05:DR-01]` 撤銷，不變更任何忽略規則。
- [ ] **TASK-02**：在 `ys_codebase/source/core/core/pip_manager.py` 實作 `get_cross_platform_site_packages_dirs`，回傳 POSIX 與 Windows 雙路徑。
- [ ] **TASK-03**：在 `ys_codebase/source/core/core/ide_projector.py` 改造 `sync_vscode_settings`（雙路徑恆定注入、移除 `defaultInterpreterPath` 託管寫入、清除舊託管值、Zero-Touch 比對），並更新 `revert_vscode_settings`。
- [ ] **TASK-04**：在 `ys_codebase/source/agents-workflow/agents_workflow/publisher.py` 實作換行符 CRLF $\to$ LF 正規化，將物化狀態清單路徑遷移至 `cache://agents-workflow/project_release_manifest.json`，並加入舊版 storage manifest 遷移與自動清理邏輯。
- [ ] **TASK-05**：編寫 `core` 與 `agents-workflow` 之單元測試（`test_ide_projector_cross_platform.py` 與 `test_publisher_cross_platform.py`），並執行回歸驗證。
- [ ] **TASK-DOC**：更新 `docs/core/DESIGN_NOTES.md`、`docs/agents-workflow/DESIGN_NOTES.md` 與代碼 Docstrings。

---

## 5. 決策定稿 (Confirmed Decision Records)

- **[P04:DR-01]**：全面採納 Option A1 與 Option B1 架構路線，將跨平台環境差異引起的 Git Working Tree 污染問題從根本隔離（IDE 靜態併存、直譯器解耦、文本正規化、狀態移至 cache）。

