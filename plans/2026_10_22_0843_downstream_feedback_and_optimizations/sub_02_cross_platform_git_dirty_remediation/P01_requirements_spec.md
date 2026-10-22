# 需求規格說明書 (Requirements Specification)

> 功能名稱：sub_02_cross_platform_git_dirty_remediation  
> 建立日期：2026-10-22  
> 所屬主計畫：2026_10_22_0843_downstream_feedback_and_optimizations  
> 狀態：Confirmed  
> 模型：Gemini 4 Argon (Low)  

> 依據 P00：[P00_discuss.md](./P00_discuss.md)  
> 模板版本：v1.5  

---

## 1. 功能需求清單 (Functional Requirements)

| 需求編號 | 需求名稱 | 詳細規格描述 | 優先級 | 對應 P00 語意 |
| :--- | :--- | :--- | :---: | :--- |
| **FR-01** | `ReleasePublisher` 來源資產雜湊跨平台 LF 正規化 | `ReleasePublisher._get_source_file_sha1` 在計算單一檔案或目錄型資產（如 `assets/skills/` 遞迴走訪）之 SHA-1 時，必須先將文字內容之換行符統一正規化為 LF（`\r\n` $\to$ `\n`），確保 Windows (`core.autocrlf=true`) 與 Linux/macOS 計算出的 `fingerprint` 與 `combined_fingerprint` 100% 恆定一致。 | P0 | [P00:DR-01] |
| **FR-02** | `release_manifest.json` 狀態檔本地隔離與舊版清理 | 將 `agents-workflow` 之 Project 軌物化狀態追蹤清單遷移至 `cache://agents-workflow/project_release_manifest.json`（並於 `ReleasePublisher.release_all` 執行時自動將舊版 `storage://agents-workflow/release_manifest.json` 平滑遷移至 `cache://` 後物理刪除舊檔與空目錄）；運行期狀態僅存於 `cache://`，Git 追蹤區不再產生任何寫入，徹底杜絕運行期狀態與 `updated_at` 污染 Git 工作區（不以新增忽略規則掩蓋，`[P05:DR-01]`）。 | P0 | [P00:DR-01] |
| **FR-03** | `.vscode/settings.json` 跨平台雙路徑恆定注入 (`extraPaths`) | `PipManager` 新增 `get_cross_platform_site_packages_dirs(py_tag)` 方法，同時回傳 POSIX (`lib/pythonX.Y/site-packages`) 與 Windows (`Lib/site-packages`) 雙平台結構路徑；`IdeProjector.sync_vscode_settings` 於微環境就緒時，將雙平台相對路徑一併寫入 `python.analysis.extraPaths` 與 `_yscb_managed.extraPaths`，使跨平台執行時陣列順序與內容 100% 恆定。 | P0 | [P00:DR-02] |
| **FR-04** | 移除 `.vscode/settings.json` 之 `defaultInterpreterPath` 託管寫入與舊值清理 | `IdeProjector.sync_vscode_settings` 停止向共用的 `.vscode/settings.json` 自動寫入隨作業系統變動的 `python.defaultInterpreterPath`；若既有 `settings.json` 中的 `python.defaultInterpreterPath` 等於舊版 `_yscb_managed.defaultInterpreterPath`（或屬 YSCB 託管之 `.venv` 路徑），同步時自動將其自 `settings.json` 與 `_yscb_managed` 移除，同時 100% 保留使用者自訂之非託管直譯器路徑。 | P0 | [P00:DR-02] |

---

## 2. 邊界與異常情況 (Edge Cases & Failure Modes)

| 邊界編號 | 情境說明 | 預期防禦與處理行為 |
| :--- | :--- | :--- |
| **EC-01** | 目錄型資產內含非 UTF-8 二進位檔案 | `_get_source_file_sha1` 在對目錄內檔案進行 CRLF $\to$ LF 正規化時，僅對可成功以 UTF-8 解碼之文字內容執行 `.replace("\r\n", "\n")`，若遇純二進位檔案（`UnicodeDecodeError`）則維持原始 bytes 雜湊，絕不拋出例外或損壞雜湊。 |
| **EC-02** | 既有專案工作區殘留舊版 `storage://agents-workflow/release_manifest.json` | `ReleasePublisher.release_all` 啟動時若偵測到舊版 `storage://agents-workflow/release_manifest.json` 存在，自動讀取其 `published_files` 遷移至 `cache://agents-workflow/project_release_manifest.json`（若新檔尚未存在），隨後立即移除舊檔並清理空的 `storage://agents-workflow` 目錄，確保舊專案升級後無殘留檔案。 |
| **EC-03** | 使用者已在 `.vscode/settings.json` 手動設定自訂 `python.defaultInterpreterPath` | 若 `settings.json` 中之 `python.defaultInterpreterPath` 與 `_yscb_managed.defaultInterpreterPath` 不同且非 YSCB `.venv` 託管路徑，則視為開發者自訂設定，在 `sync_vscode_settings` 與 `revert_vscode_settings` 中皆 100% 保留不予刪除。 |
| **EC-04** | `.vscode/settings.json` 內容與更新後完全相同 | `IdeProjector.sync_vscode_settings` 在寫盤前先比對更新前後之 JSON 結構或字串，若內容完全無異動則跳過磁碟寫入（Zero-Touch），避免無謂更新檔案 `mtime`。 |

---

## 3. 非功能需求 (Non-Functional Requirements)

| 需求編號 | 類別 | 指標與量化約束 |
| :--- | :--- | :--- |
| **NFR-01** | 跨平台冪等性 | 在 Linux 與 Windows 環境交替執行 `yscb.py` 任意指令、`install`、`restore` 或 `agents-workflow release` 後，`git status` 對 `.vscode/settings.json` 與 `.yscb/` 均保持 0 diff（Working Tree Clean）。 |
| **NFR-02** | 零外部依賴與向後相容 | 100% 使用 Python 標準庫；`core` 與 `agents-workflow` 既有單元測試與沙盒測試 100% 通過。 |

---

## 4. 知識庫與踩坑紀錄查閱 (Known Gotchas & CAUTIONs)

- **`[!NOTE]`** 查閱 [`docs/core/DESIGN_NOTES.md`](../../../docs/core/DESIGN_NOTES.md) `[DN-09]`：`IdeProjector` 必須嚴守「若 `project://.vscode` 不存在則完全靜默略過，絕不主動建立 `.vscode/` 目錄」以及「透過 `_yscb_managed` 差集追蹤並支援 `revert_vscode_settings` 無損回滾」之契約。
- **`[!NOTE]`** 查閱 [`docs/agents-workflow/DESIGN_NOTES.md`](../../../docs/agents-workflow/DESIGN_NOTES.md) `[DN-AW-04]`：`_get_source_file_sha1` 支援目錄遞迴排序聚合與 `(st_mtime_ns, st_size)` Stat-First 快取；加入 CRLF $\to$ LF 正規化時，快取寫入之 SHA-1 亦為正規化後之結果，確保快取命中與重算完全一致。

