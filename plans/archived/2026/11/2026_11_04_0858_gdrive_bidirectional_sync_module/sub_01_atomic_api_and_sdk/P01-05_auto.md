# 自動連續推進綜合規格與實作紀錄 (Consolidated Auto Plan & Task Log)

> 功能名稱：`module:gdrive-support` 模組骨架、組態映射與原子雲端操作 API/SDK (`sub_01_atomic_api_and_sdk`)  
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
| **FR-01** | `module:gdrive-support` 模組骨架與 Contributes 契約 | 於 `ys_codebase/source/gdrive-support/` 建立完整標準模組結構（`manifest.json`、`.yscbignore`、`contributes/{_format.json,_manifest.md,core.json}`、`configurable/{_format.json,config.project.json}`、`gdrive_support/__init__.py`、`scripts/cli.py`、`USAGE.md`），於 `contributes/core.json` 的 `"commands"` 下註冊 `"module_alias": ["gdrive"]` 與原子 CLI 指令樹，且預設組態 `auto_sync: false`，通過 `python yscb.py dev check gdrive-support` 合規檢查（0 FAIL / 0 WARN）。 | P0 | [P00:DR-01] |
| **FR-02** | `gdrive_support/config.py` 組態載入與 `file-space` / `mapping` 雙向映射 | 解析 `config://gdrive-support/` 與 `contributes` 之 `sync_spaces`；統一以 `abs_path.relative_to(project_root)` 正規化 `FileSpaceManager` 列舉之檔案路徑為 `project_rel_path`；支援選填 `mapping: [{local, remote}]`，驗證每個 `mapping.local` 必須位於該 `space` 的 `include` 根目錄之下，並提供最長前綴匹配之雙向可逆轉換 `local_to_remote_rel()` 與 `remote_to_local_rel()`。 | P0 | [P00:DR-02] |
| **FR-03** | `gdrive_support/transport.py` 100% 原檔案類型原子傳輸介面與雙模驅動 | 實作 `RemoteEntry` 與 `AbstractSyncTransport`（提供 `list_files`、`upload_file`、`download_file`、`trash_file`、`move_file`、`mkdir`、`create_shortcut` 等獨立原子 API），100% 保持原檔案類型與原始位元組 (`md5`/`sha256`/`size`) 傳輸；對 `application/vnd.google-apps.shortcut` 自動批次解析 `target_file_id` 與目標實體檔 `(md5, size, mtime_ns)`；完整實作 `LocalSandboxTransport` 與 `GoogleDriveApiTransport`。 | P0 | [P00:DR-03] |
| **FR-04** | 獨立原子 CLI 與 SDK 入口 (`ls`/`get`/`put`/`rm`/`mkdir`/`shortcut`/`auth`/`status`) | 於 `gdrive_support/__init__.py` 與 `scripts/cli.py` 暴露無須啟動背景服務即可獨立呼叫之原子 SDK 與 CLI 子命令：`ls`、`get`、`put`、`rm`、`mkdir`、`shortcut`、`auth`、`status`（支援 `--sandbox-dir` 與 `--json` 結構化輸出）。 | P0 | [P00:DR-01], [P00:DR-03] |

### 1.2 邊界與異常情況 (Edge Cases & Failure Modes)

| 邊界編號 | 情境說明 | 預期防禦與處理行為 |
| :--- | :--- | :--- |
| **EC-01** | `sync_spaces` 中設定之 `mapping.local` 越界（不在該 `space` 的 `include` 根目錄範圍內）或 `space` 未註冊 | `config.py` 載入與驗證時立即拋出 `GDriveConfigError`，明確指出越界之 `mapping.local` 與所屬 `space` 的允許 `include` 範圍。 |
| **EC-02** | 雲端目錄中存在 Google Workspace 原生線上文件（`application/vnd.google-apps.*`，且非 `folder` 與 `shortcut`） | `transport.list_files()` 不執行匯出轉檔，將該項目之 `skipped_reason` 標記為 `"SKIPPED_UNSUPPORTED_MIME"` 安全略過，若單檔直接對其呼叫 `download_file()` 則拋出 `GDriveUnsupportedMimeError`。 |
| **EC-03** | 雲端 Shortcut (`application/vnd.google-apps.shortcut`) 指向之 `target_file_id` 已被刪除或無法存取（懸空捷徑 Dangling Shortcut） | `transport.list_files()` 批次解析目標時，將無法取得目標之 Shortcut 標記 `dangling_shortcut=True` 並安全略過或於 `download_file` 時拋出明確 `GDriveFileNotFoundError`。 |
| **EC-04** | 遠端路徑穿越（如傳入 `../` 或絕對路徑）或雲端同目錄出現重複同名檔案 | 正規化遠端路徑時攔截 `..` 拋出 `GDrivePathError`；同目錄出現重複同名檔時，自動選取 `mtime_ns` 最新者作為有效版本，並可將較舊重複項目記錄/移入 `.trash/`。 |

### 1.3 非功能需求 (Non-Functional Requirements)

| 需求編號 | 類別 | 指標與量化約束 |
| :--- | :--- | :--- |
| **NFR-01** | 零外部第三方套件依賴與單向 DAG | 100% 使用 Python 標準庫（`urllib.request`、`hashlib`、`json`、`pathlib` 等）與母倉核心模組（`core`、`file-space`），嚴禁引入 `google-api-python-client` 等第三方 pip 依賴；嚴格維持 `config.py <- transport.py <- scripts/cli.py` 單向依賴。 |
| **NFR-02** | 自動化測試 100% 本地沙盒隔離 | `tests/` 下所有自動化測試案例 100% 僅針對 `config.py`、`LocalSandboxTransport` 與本地 CLI/SDK 編寫，**嚴禁對外 `GoogleDriveApiTransport` 編寫需使用者金鑰之自動化 test cases**。 |

### 1.4 知識庫與踩坑紀錄查閱 (Known Gotchas & CAUTIONs)

- **`[!NOTE]`** `FileSpaceManager` 在單根 `include` 空間下回傳之相對路徑為相對於 `inc_root` 而非 `project://`，因此 `config.py` 必須統一使用 `abs_path.relative_to(project_root)` 正規化為 POSIX 相對路徑。
- **`[!NOTE]`** `InterProcessLock` 必須傳入經 `core.uri.resolve("cache://gdrive-support/sync.lock")` 解析後之實體作業系統路徑。

---

## 2. 架構設計與異動檔案清單 (P02)

### 2.1 模組架構與核心資料流 (Architecture & Data Flow)

```text
CLI (scripts/cli.py) / SDK (gdrive_support/__init__.py)
  │
  ├──► gdrive_support/transport.py (AbstractSyncTransport)
  │      ├── LocalSandboxTransport (100% 本地檔案系統模擬 file_id, .trash/, .yscb_shortcut.json)
  │      └── GoogleDriveApiTransport (stdlib urllib.request 直連 Drive REST API v3)
  │
  └──► gdrive_support/config.py (GDriveConfig, SyncSpaceSpec, PathMappingRule)
         └── 復用 file_space.FileSpaceManager 驗證 space 與 include 根目錄邊界
```

### 2.2 受影響與新建檔案清單 (Impacted & New Files Inventory)

| 檔案路徑 | 類型 | 職責與變更說明 |
| :--- | :---: | :--- |
| `ys_codebase/source/gdrive-support/manifest.json` | New | 模組元數據宣告（依賴 `core`、`file-space`、`server`） |
| `ys_codebase/source/gdrive-support/.yscbignore` | New | 發布排除規則（排除 `tests/`、`*.tmp`、`*.bak`） |
| `ys_codebase/source/gdrive-support/USAGE.md` | New | 模組 CLI 與 SDK 使用說明 |
| `ys_codebase/source/gdrive-support/contributes/_manifest.md` | New | 模組雙向擴充契約總表（Ingress `_format.json` 與 Egress `core.json`） |
| `ys_codebase/source/gdrive-support/contributes/_format.json` | New | 宣告各模組可貢獻之 `sync_spaces`（`space` + 選填 `mapping`）Ingress Schema |
| `ys_codebase/source/gdrive-support/contributes/core.json` | New | 宣告 `"commands"`（含 `"module_alias": ["gdrive"]` 與原子 CLI 指令 `ls`, `get`, `put`, `rm`, `mkdir`, `shortcut`, `auth`, `status`）與預設 `gitignore` 規則 |
| `ys_codebase/source/gdrive-support/configurable/_format.json` | New | 宣告 `config://gdrive-support/` 組態 Schema（含 `auto_sync: bool? = false`） |
| `ys_codebase/source/gdrive-support/configurable/config.project.json` | New | 預設專案組態範本（`auto_sync: false`, `active_branch: "main"` 等） |
| `ys_codebase/source/gdrive-support/gdrive_support/__init__.py` | New | 模組公開 SDK 匯出（組態、例外、Transport 工廠與原子操作 API） |
| `ys_codebase/source/gdrive-support/gdrive_support/config.py` | New | 組態解析、`file-space` 路徑正規化、`mapping` 子集校驗與雙向路徑映射 |
| `ys_codebase/source/gdrive-support/gdrive_support/transport.py` | New | `RemoteEntry`、`AbstractSyncTransport`、`LocalSandboxTransport` 與 `GoogleDriveApiTransport` |
| `ys_codebase/source/gdrive-support/scripts/__init__.py` | New | CLI 腳本套件標記 |
| `ys_codebase/source/gdrive-support/scripts/cli.py` | New | 原子 CLI 子命令路由與格式化輸出 |
| `ys_codebase/source/gdrive-support/tests/test_atomic_api_and_config.py` | New | 100% 針對 `config.py`、`LocalSandboxTransport` 與本地 CLI/SDK 之單元與邊界測試 |
| `docs/gdrive-support/README.md` | New | `module:gdrive-support` 模組總覽、空間映射與原子操作手冊 |

### 2.3 架構決策記錄 (Architecture Decision Records)

- **[P02:DR-01]** `LocalSandboxTransport` 採用確定性 메타數據側車檔（於沙盒根目錄維護 `.yscb_sandbox_meta.json` 記錄虛擬 `file_id`、Shortcut `target_id` 與模擬雲端不支援 MIME 標記，並將實體檔案存放於沙盒對應路徑與 `.trash/`），使離線沙盒能 100% 精確重現 Google Drive `file_id`、原地 `PATCH` vs 新建 `POST`、Shortcut 解析與同名重複檔去重行為。

---

## 3. 介面契約與 API 簽名 (P03)

### 3.1 介面契約與核心簽名 (Interface Inventory & Method Signatures)

```python
# gdrive_support/config.py
class GDriveError(Exception): ...
class GDriveConfigError(GDriveError): ...
class GDrivePathError(GDriveError): ...
class GDriveFileNotFoundError(GDriveError): ...
class GDriveUnsupportedMimeError(GDriveError): ...
class GDriveTransportError(GDriveError): ...

@dataclass(frozen=True)
class PathMappingRule:
    local_uri: str
    local_rel_prefix: str
    remote_rel_prefix: str

@dataclass(frozen=True)
class SyncSpaceSpec:
    space: str
    mappings: tuple[PathMappingRule, ...] = ()
    def local_to_remote_rel(self, project_rel_path: str) -> Optional[str]: ...
    def remote_to_local_rel(self, remote_rel_path: str) -> Optional[str]: ...

@dataclass(frozen=True)
class GDriveConfig:
    root_folder_id: str = ""
    active_branch: str = "main"
    auto_sync: bool = False
    poll_interval_sec: float = 30.0
    pull_delete_default: bool = False
    push_delete_default: bool = False
    auth_mode: str = "oauth_user"
    credentials_uri: str = "config://gdrive-support/credentials.json"
    token_uri: str = "cache://gdrive-support/token.json"
    sandbox_dir: str = ""
    sync_spaces: tuple[SyncSpaceSpec, ...] = ()

def normalize_remote_rel_path(remote_path: str) -> str: ...
def load_gdrive_config(
    config_override: Optional[dict[str, Any]] = None,
    project_root: Optional[Path] = None,
    space_include_roots: Optional[ dict[str, list[Path]] ] = None,
) -> GDriveConfig: ...
def collect_space_local_files(
    spec: SyncSpaceSpec,
    project_root: Optional[Path] = None,
) -> dict[str, Path]: ...

# gdrive_support/transport.py
@dataclass(frozen=True)
class RemoteEntry:
    rel_path: str
    name: str
    file_id: str
    mime_type: str
    is_dir: bool = False
    size: int = 0
    md5: str = ""
    mtime_ns: int = 0
    parent_id: str = ""
    is_shortcut: bool = False
    target_file_id: str = ""
    target_mime_type: str = ""
    dangling_shortcut: bool = False
    skipped_reason: str = ""

class AbstractSyncTransport(ABC):
    @abstractmethod
    def list_files(self, remote_path: str = "", recursive: bool = False) -> list[RemoteEntry]: ...
    @abstractmethod
    def get_entry(self, remote_path: str) -> Optional[RemoteEntry]: ...
    @abstractmethod
    def mkdir(self, remote_path: str) -> RemoteEntry: ...
    @abstractmethod
    def upload_file(
        self,
        local_path: Path,
        remote_path: str,
        in_place_file_id: Optional[str] = None,
    ) -> RemoteEntry: ...
    @abstractmethod
    def download_file(self, remote_path: str, local_path: Path) -> RemoteEntry: ...
    @abstractmethod
    def trash_file(self, remote_path: str) -> bool: ...
    @abstractmethod
    def move_file(self, src_remote_path: str, dst_remote_path: str) -> RemoteEntry: ...
    @abstractmethod
    def create_shortcut(self, target_file_id: str, shortcut_remote_path: str) -> RemoteEntry: ...

class LocalSandboxTransport(AbstractSyncTransport):
    def __init__(self, sandbox_root: Path) -> None: ...

class GoogleDriveApiTransport(AbstractSyncTransport):
    def __init__(self, config: GDriveConfig) -> None: ...

def create_transport(config: GDriveConfig, sandbox_dir: Optional[str] = None) -> AbstractSyncTransport: ...
```

- **錯誤與例外契約 (Error & Exception Contracts)**：
  - 所有業務異常均繼承自 `GDriveError`；CLI 層捕捉 `GDriveError` 轉換為結構化錯誤訊息與非 0 Exit Code（`1` 為執行/設定錯誤）。
- **階段決策紀錄**：`[P03:DR-01]` `upload_file` 支援選填 `in_place_file_id: Optional[str]`，當傳入時對該 `file_id` 原地更新（保留同一 `file_id`），未傳入且強制新建時分配新 `file_id`，為 `sub_02` 的 Copy-on-Write (`.history/`) 分流奠定原子基礎。

---

## 4. 定稿審查與文檔衝擊規劃 (P04)

### 4.1 交叉驗證與靈魂拷問 (Cross-Validation & Resilience Review)

- [x] **需求對齊**：FR-01 ~ FR-04 皆已於介面簽名與實作中完整對齊
- [x] **邊界防護**：EC-01 ~ EC-04 皆有具體錯誤攔截與降級策略
- [x] **依賴純淨**：100% 符合 NFR-01 與 NFR-02 指標約束
- **靈魂拷問與防護解法**：
  - *問：當 `mapping` 同時定義了深層與淺層規則（例如 `module.source://core` 與 `module.source://core/sub`）時，如何避免短前綴吃掉長前綴？*
  - *答*：`SyncSpaceSpec` 在建構時將 `mappings` 依 `local_rel_prefix` / `remote_rel_prefix` 長度由長至短排序（Longest-Prefix Match First），確保雙向轉換 100% 唯一且可逆。

### 4.2 知識庫文檔衝擊與交付規劃 (Documentation Impact Plan)

| 維度 | 文件路徑 | 變更類型 | 交付內容與重點 |
| :--- | :--- | :---: | :--- |
| **模組手冊** | `docs/gdrive-support/README.md` | New | 模組概覽、空間與 `mapping` 配置、原子 CLI/SDK 使用手冊 |
| **專題手冊** | `ys_codebase/source/gdrive-support/USAGE.md` | New | 隨包 CLI 指令速查與範例 |
| **設計決策** | `docs/gdrive-support/README.md` | New | 內含原檔案類型傳輸與沙盒雙模設計說明 |
| **微觀註解** | 源碼檔案 Docstrings | Modify | 同步編寫關鍵介面契約與模組 Docstring |
| **發布日誌** | `CHANGELOG.md` | Modify | 於 P07 結案時記錄 `sub_01` 發布摘要 |

- **決策定稿**：**[P04:DR-01]** 確認 `sub_01` 鎖定於模組骨架、`config.py`、`transport.py` 與原子 CLI/SDK，且自動化測試 100% 僅針對本地沙盒與組態邏輯撰寫。

---

## 5. 實作任務清單與偏差紀錄 (P05)

### 5.1 實作任務清單 (Task Breakdown)

- [x] **TASK-01**：建立 `ys_codebase/source/gdrive-support/` 模組骨架（`manifest.json`、`contributes/`、`configurable/`、`USAGE.md`）
- [x] **TASK-02**：實作 `gdrive_support/config.py`（組態載入、`file-space` 路徑正規化、`mapping` 子集校驗與雙向轉換）
- [x] **TASK-03**：實作 `gdrive_support/transport.py`（`RemoteEntry`、`AbstractSyncTransport`、`LocalSandboxTransport` 與 `GoogleDriveApiTransport`）及 `gdrive_support/__init__.py`、`scripts/cli.py`
- [x] **TASK-04**：編寫 `tests/test_atomic_api_and_config.py`（100% 針對 `config.py`、`LocalSandboxTransport` 與 CLI 原子指令，零外部 Google API 測試）並通過 `dev check` 與 `dev test`
- [x] **TASK-DOC**：建立 `docs/gdrive-support/README.md` 並完善模組 Docstrings

### 5.2 實作偏差紀錄表 (Implementation Deviations)

| 任務編號 | 偏差等級 | 偏離描述與決策理由 | 處置方式 / 記錄 |
| :--- | :---: | :--- | :--- |
| - | - | 無偏差 | - |

