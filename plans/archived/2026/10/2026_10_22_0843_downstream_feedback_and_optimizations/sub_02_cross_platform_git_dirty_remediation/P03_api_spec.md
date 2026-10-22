# API 與介面規格書 (API & Interface Specification)

> 功能名稱：sub_02_cross_platform_git_dirty_remediation  
> 建立日期：2026-10-22  
> 所屬主計畫：2026_10_22_0843_downstream_feedback_and_optimizations  
> 狀態：Confirmed  
> 模型：Gemini 3.8 Flash (Medium)  

> 模板版本：v1.2  

---

## 1. 介面契約清單 (Interface Inventory)

| 介面 / 類別名稱 | 所屬檔案路徑 | 存取層級 | 核心職責 |
| :--- | :--- | :---: | :--- |
| `PipManager` | `ys_codebase/source/core/core/pip_manager.py` | Public | 管理微環境 pip 相依與 site-packages 路徑解析；提供跨平台 site-packages 靜態路徑集合 |
| `IdeProjector` | `ys_codebase/source/core/core/ide_projector.py` | Public | 投射 IDE 設定（`.vscode/settings.json`）；管理 `extraPaths` 雙平台恆定性與零磁碟寫入比對 |
| `ReleasePublisher` | `ys_codebase/source/agents-workflow/agents_workflow/publisher.py` | Public | 物化發布流程控制；資產 SHA-1 正規化計算、物化清單 cache 儲存與舊版 storage 遷移清理 |

---

## 2. 核心 API 簽名與詳細規格 (Method Signatures & Contracts)

```python
# ---------------------------------------------------------------------------
# Module: core
# File: ys_codebase/source/core/core/pip_manager.py
# ---------------------------------------------------------------------------

class PipManager:
    ...
    def get_cross_platform_site_packages_dirs(self, py_tag: str) -> list[str]:
        """回傳當前虛擬環境在跨平台 (POSIX 與 Windows) 下對應之 site-packages 相對路徑清單。

        Args:
            py_tag (str): Python 版本標籤 (例如 "py312")。

        Returns:
            list[str]: 包含雙平台 site-packages 相對路徑 (以 "./" 開頭並使用正斜線)，例如:
                [
                    "./.yscb/.venv/py312/lib/python3.12/site-packages",
                    "./.yscb/.venv/py312/Lib/site-packages",
                ]
                清單經過排序保證順序恆定。
        """
        ...

# ---------------------------------------------------------------------------
# Module: core
# File: ys_codebase/source/core/core/ide_projector.py
# ---------------------------------------------------------------------------

class IdeProjector:
    ...
    @classmethod
    def sync_vscode_settings(
        cls,
        project_root: str,
        site_packages_paths: list[str] | None = None,
    ) -> str:
        """同步 VSCode 設定至 .vscode/settings.json。

        行為契約:
        1. 若專案根目錄不存在 .vscode/ 目錄，則靜默跳過，回傳 "skipped"（絕不主動新建 .vscode 目錄）。
        2. 將雙平台 site_packages_paths 注入 python.analysis.extraPaths 與 _yscb_managed.extraPaths。
        3. 停止向 settings.json 寫入 python.defaultInterpreterPath。
        4. 若 settings.json 存在 python.defaultInterpreterPath，比對其值是否等於先前
           _yscb_managed.defaultInterpreterPath 或符合 .yscb/.venv 託管模式；
           若符合則主動移除，開發者自訂之直譯器路徑則 100% 保留。
        5. 在磁碟寫入前進行 JSON 內容結構/文字比對 (Zero-Touch Check)，若與既有內容相同則跳過寫入，回傳 "skipped"。
        6. 若有變更則格式化寫盤並回傳 "updated"。

        Args:
            project_root (str): 專案根目錄。
            site_packages_paths (list[str] | None): 跨平台 site-packages 相對路徑列表。

        Returns:
            str: "updated" | "skipped"
        """
        ...

    @classmethod
    def revert_vscode_settings(cls, project_root: str) -> str:
        """回滾由 YSCB 託管之 VSCode 設定。

        行為契約:
        1. 依據 _yscb_managed 記錄之 extraPaths、excludes 等進行差集回滾。
        2. 若使用者自訂了非 YSCB 託管的設定，予以保留。
        3. 移除 _yscb_managed 鍵值。
        4. 若 settings.json 在移除後為空字典，清理或保留空白配置。

        Returns:
            str: "reverted" | "skipped"
        """
        ...

# ---------------------------------------------------------------------------
# Module: agents-workflow
# File: ys_codebase/source/agents-workflow/agents_workflow/publisher.py
# ---------------------------------------------------------------------------

class ReleasePublisher:
    # 遷移專案物化狀態檔常數至 cache:// 空間
    PROJECT_MANIFEST_CACHE_URI = "cache://agents-workflow/project_release_manifest.json"
    LEGACY_PROJECT_MANIFEST_STORAGE_URI = "storage://agents-workflow/release_manifest.json"

    def _get_source_file_sha1(self, source_path: str) -> str:
        """計算來源檔案或目錄資產之 SHA-1 摘要，保證換行符跨平台正規化。

        行為契約:
        1. 若為目錄，遞迴走訪所有檔案並按字母順序排序。
        2. 讀取檔案內容時，先嘗試以 UTF-8 解碼文字並執行 .replace("\r\n", "\n") 正規化為 LF；
           若遭遇 UnicodeDecodeError 則以原始二進位 bytes 計算雜湊。
        3. 利用 (st_mtime_ns, st_size) 快取正規化後之 SHA-1 摘要。

        Args:
            source_path (str): 實體磁碟路徑或專案相對路徑。

        Returns:
            str: 40 字元十六進位 SHA-1 雜湊。
        """
        ...

    def _migrate_legacy_storage_manifest(self) -> None:
        """舊版 storage:// 物化清單平滑遷移與物理清理。

        行為契約:
        1. 檢查 LEGACY_PROJECT_MANIFEST_STORAGE_URI 實體是否存在。
        2. 若存在且 PROJECT_MANIFEST_CACHE_URI 尚不存在，將其內容複製/遷移至 cache。
        3. 物理刪除 LEGACY_PROJECT_MANIFEST_STORAGE_URI。
        4. 若 storage://agents-workflow 目錄變為空，清理該目錄。
        """
        ...
```

- **錯誤與例外契約 (Error & Exception Contracts)**：
  - 二進位檔案處理：`_get_source_file_sha1` 遇到非 UTF-8 內容時捕獲 `UnicodeDecodeError` 並安全降級為二進位 chunk 雜湊，嚴禁拋出例外中斷發布流程。
  - 檔案存取權限：舊版 manifest 刪除與目錄清理若因權限問題失敗，以 warning 日誌記錄，不阻斷主發布流程。
  - 無 `.vscode` 目錄：`IdeProjector.sync_vscode_settings` 遇到不存在 `.vscode` 時直接靜默回傳 `"skipped"`，不引發例外。
- **階段決策紀錄**：
  - `[P03:DR-01]`：`PipManager.get_cross_platform_site_packages_dirs` 回傳格式一律使用正規化 POSIX 風格正斜線（`./.yscb/.venv/py312/...`），避免 Windows 反斜線引發 JSON 跳脫與 diff 振盪。

---

## 3. 依賴拓撲與實作順序 (Implementation Topology)

```text
[core.PipManager 跨平台路徑 (gitignore 不變更)]
                  |
                  v
[PipManager: get_cross_platform_site_packages_dirs]
                  |
                  v
[IdeProjector: sync_vscode_settings (雙路徑 + 移除 interpreter + Zero-Touch)]
                  |
                  v
[agents-workflow: _get_source_file_sha1 (CRLF->LF) & manifest 遷移至 cache://]
```

