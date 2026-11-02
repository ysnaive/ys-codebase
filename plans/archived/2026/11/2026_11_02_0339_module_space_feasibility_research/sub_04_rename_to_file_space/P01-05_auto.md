# 自動連續推進綜合規格與實作紀錄 (Consolidated Auto Plan & Task Log)

> 功能名稱：全面將 `module:space` 更名為 `module:file-space`（基於 `git diff` 腳本精準掃描替換與反查驗收）  
> 建立日期：2026-11-02  
> 所屬主計畫：`2026_11_02_0339_module_space_feasibility_research`  
> 狀態：Completed  
> 模型：Gemini 4 Argon (Low)  

> 依據 P00：[P00_discuss.md](./P00_discuss.md)  
> 模板版本：v1.0  

---

## 1. 需求規格與邊界契約 (P01)

### 1.1 功能需求清單 (Functional Requirements)

| 需求編號 | 需求名稱 | 詳細規格與驗收條件 (Acceptance Criteria) | 優先級 | 對應 P00 語意 |
| :--- | :--- | :--- | :---: | :--- |
| **FR-01** | `module:space` 物理目錄、模組身分與擴充點全面更名為 `file-space` | 1. 將 `ys_codebase/source/space/` 搬移更名為 `ys_codebase/source/file-space/`，內部套件 `space/` 更名為 `file_space/`，`manifest.json["name"]` 設為 `"file-space"`。<br/>2. 將 `ys_codebase/config/space/` 搬移更名為 `ys_codebase/config/file-space/`，`ys_codebase/source/agents-workflow/contributes/space.json` 更名為 `contributes/file-space.json`，`docs/space/` 更名為 `docs/file-space/`。<br/>3. 模組內 `contributes/core.json`（事件 `on_file_space_changed`、語意 URI `file-space.storage://` -> `cache://file-space/`）、`contributes/server.json`（服務 `file-space-watcher` -> `file_space.service:FileSpaceWatcherServiceWorker`）與 `contributes/_format.json`（頂層鍵 `file_spaces`、型別 `FileSpaceDef`）100% 同步更名。 | P0 | [P00:DR-01] |
| **FR-02** | Python Package 符號、API 參數與 CLI 旗標全面更名為 `file_space` / `FileSpace` | 1. `file_space` 套件公開類別與例外全面更名：`FileSpaceManager`、`FileSpaceConfig`、`FileSpaceDef`、`FileSpaceOrigin`、`FileSpaceWatcherServiceWorker`、`FileSpaceError`、`FileSpaceNotFoundError`、`InvalidFileSpaceConfigError`。<br/>2. `knowledge-db` 內部與公開 API 對齊：`manifest.json` 依賴 `"file-space": ">=1.0.0"`、`scripts/hook.space.py` 更名為 `scripts/hook.file-space.py`（訂閱 `on_file_space_changed`）、設定檔與 Contributes 之 `space_weights` 更名為 `file_space_weights`、CLI 與 SDK 之 `space` / `--space` 參數與輸出全面更名為 `file_space` / `--file-space`（含 `total_file_spaces`、`file_spaces`、`get_knowledge_db_file_spaces`）。 | P0 | [P00:DR-01] |
| **FR-03** | 基於 `git diff` 範圍之自動化腳本掃描、批量替換與反向殘留查驗 | 1. 編寫自動化腳本，僅鎖定當前工作區相對於 `HEAD` 之新增與已修改檔案（`git status --porcelain` / `git diff HEAD`），過濾非本次 diff 之原生詞彙（如 `workspace`、`namespace`、`whitespace`、`2-space`），批次完成目錄搬移與識別符替換。<br/>2. 替換後執行反向查驗腳本，確認 `git diff` 範圍內無遺漏之裸 `space` 模組/類別/參數引用，且無誤替換 `workspace`/`namespace`/`2-space`。<br/>3. 清理舊有運行時殘留（`.modules/space`、`.cache/space`），並通過 `file-space`、`knowledge-db`、`agents-workflow` 之 `dev check`、`dev test` 與 `@build` 熱部署驗收。 | P0 | [P00:DR-02] |

### 1.2 邊界與異常情況 (Edge Cases & Failure Modes)

| 邊界編號 | 情境說明 | 預期防禦與處理行為 |
| :--- | :--- | :--- |
| **EC-01** | 檔案中包含 `workspace`、`workspace_root`、`namespace`、`whitespace`、`2-space` 等包含 `space` 子字串但語意完全無關之詞彙 | 腳本採用精確正則邊界 (`(?<![a-zA-Z0-9_-])space(?![a-zA-Z0-9_-])` 及有序 Token 映射表) 並顯式保護 `workspace`/`namespace`/`whitespace`/`2-space`，確保零誤傷。 |
| **EC-02** | 運行環境 `.modules/space`、`yscb.config.json` 或常駐 Server 仍載入舊 `space` 模組與 `space-watcher` | 先停止常駐 Server、清理 `.modules/space` 與 `.cache/space`，再執行 `install file-space@build knowledge-db@build agents-workflow@build --force` 及 `agents-workflow compile && release --force` 同步全部二層產物。 |
| **EC-03** | `knowledge-db` 測試或既有快取目錄中殘留舊索引或游標格式 | 重置測試沙盒與本機快取游標，確保 `file-space` 與 `knowledge-db` 單元測試 100% 獨立通過。 |

### 1.3 非功能需求 (Non-Functional Requirements)

| 需求編號 | 類別 | 指標與量化約束 |
| :--- | :--- | :--- |
| **NFR-01** | 一致性與測試覆蓋 | `file-space` 與 `knowledge-db` 之 `dev check` 與 `dev test` 100% 通過（0 Fail, 0 Error），且 `git diff` 反向掃描確認零遺漏。 |

### 1.4 知識庫與踩坑紀錄查閱 (Known Gotchas & CAUTIONs)

- **`[!NOTE]`** 修改 `agents-workflow` 與 `knowledge-db` 的 `contributes/agents-workflow.json`（如 `KNOWLEDGE_DB_SPACE` token provider 或技能說明）後，必須安裝 `@build` 並執行 `agents-workflow compile` 與 `release --force` 方能更新 `.agents/skills/`。

---

## 2. 架構設計與異動檔案清單 (P02)

### 2.1 模組架構與核心資料流 (Architecture & Data Flow)

```text
[1. git diff & untracked 範圍提取腳本]
       │ (鎖定本次新增目錄與修改行，排除 workspace / namespace / whitespace / 2-space)
       ▼
[2. 物理目錄與檔案搬移 (Path Renames)]
       ├─► ys_codebase/source/space/               ──► ys_codebase/source/file-space/
       ├─► ys_codebase/source/file-space/space/    ──► ys_codebase/source/file-space/file_space/
       ├─► ys_codebase/config/space/               ──► ys_codebase/config/file-space/
       ├─► docs/space/                             ──► docs/file-space/
       ├─► .../agents-workflow/contributes/space.json ► .../contributes/file-space.json
       └─► .../knowledge-db/scripts/hook.space.py  ──► .../scripts/hook.file-space.py
       │
       ▼
[3. 結構化 Token 批次替換 + 反向殘留查驗 ( Verification & Audit )]
       │
       ▼
[4. dev check + dev test (file-space / knowledge-db / agents-workflow) + @build 熱部署]
```

### 2.2 受影響與新建檔案清單 (Impacted & New Files Inventory)

| 檔案路徑 | 類型 | 職責與變更說明 |
| :--- | :---: | :--- |
| `ys_codebase/source/file-space/**` | Rename & Modify | 自 `ys_codebase/source/space/` 搬移並將套件 `space` 更名為 `file_space`，所有類別 (`FileSpace*`)、CLI、Contributes、README 與測試 (`tests/test_file_space.py`) 全面更名 |
| `ys_codebase/config/file-space/contribute.json` | Rename & Modify | 自 `ys_codebase/config/space/contribute.json` 搬移，頂層鍵改為 `file_spaces` |
| `ys_codebase/source/agents-workflow/contributes/file-space.json` | Rename & Modify | 自 `contributes/space.json` 搬移，頂層鍵改為 `file_spaces` |
| `ys_codebase/source/agents-workflow/contributes/_manifest.md` | Modify | 更新 Contributes 說明為 `file-space.json` |
| `ys_codebase/source/knowledge-db/**` | Modify | 更新 `manifest.json`、`contributes/`、`knowledge_db/*.py`、`scripts/cli.py`、`scripts/hook.file-space.py`、`README.md` 與 `tests/test_*.py`（`test_space.py` 更名為 `test_file_space.py`） |
| `ys_codebase/config/knowledge-db/contribute.json` | Modify | 將 `space_weights` 更名為 `file_space_weights` |
| `docs/file-space/**` | Rename & Modify | 自 `docs/space/` 搬移並全面更新文檔內模組、API 與 CLI 名稱 |
| `docs/knowledge-db/**` | Modify | 更新 `README.md`、`architecture.md`、`contributes_guide.md`、`incremental_hot_reload.md`、`DESIGN_NOTES.md` 中之 `file-space` 引用 |
| `yscb.config.json` | Modify | 將已安裝模組鍵 `space` 更新為 `file-space` |

### 2.3 架構決策記錄 (Architecture Decision Records)

- **[P02:DR-01] 有序長詞優先正則替換表與 `git diff` 行級校驗**：
  - 腳本替換時先將複合識別符（如 `SpaceWatcherServiceWorker` $\to$ `FileSpaceWatcherServiceWorker`、`InvalidSpaceConfigError` $\to$ `InvalidFileSpaceConfigError`、`SpaceNotFoundError` $\to$ `FileSpaceNotFoundError`、`SpaceManager` $\to$ `FileSpaceManager`、`SpaceConfig` $\to$ `FileSpaceConfig`、`on_space_changed` $\to$ `on_file_space_changed`、`space_weights` $\to$ `file_space_weights`、`space-watcher` $\to$ `file-space-watcher`、`space.storage://` $\to$ `file-space.storage://` 等）按長度由長到短精準替換，再替換邊界獨立之 `space` / `spaces` 變數與旗標，確保語法結構 100% 合法。

---

## 3. 介面契約與 API 簽名 (P03)

### 3.1 介面契約與核心簽名 (Interface Inventory & Method Signatures)

```python
# ys_codebase/source/file-space/file_space/__init__.py
class FileSpaceConfig: ...
class FileSpaceManager:
    def load_file_spaces(self) -> Dict[str, FileSpaceConfig]: ...
    def list_file_spaces(self) -> List[str]: ...
    def get_file_space(self, name: str) -> FileSpaceConfig: ...
    def resolve_file_space_include(self, name: str) -> List[Path]: ...
    def iter_file_space_files(self, name: Optional[str] = None) -> Iterator[Path]: ...

class FileSpaceWatcherServiceWorker(BaseServiceWorker): ...
class FileSpaceError(Exception): ...
class FileSpaceNotFoundError(FileSpaceError): ...
class InvalidFileSpaceConfigError(FileSpaceError): ...

# ys_codebase/source/knowledge-db/knowledge_db/engine.py
class KnowledgeEngine:
    def get_file_space_weight(self, file_space_name: str) -> float: ...
    def get_all_file_space_weights(self) -> Dict[str, float]: ...
    def status(self, file_space: Optional[str] = None) -> Dict[str, Any]: ...
    def search(self, query: str, file_space: Optional[Union[str, List[str]]] = None, ...) -> Any: ...
```

- **錯誤與例外契約 (Error & Exception Contracts)**：
  - 當查詢未註冊之檔案空間時，拋出 `FileSpaceNotFoundError`；當 `file_space_weights` 或 `file_spaces` 配置不合法時，拋出 `InvalidFileSpaceConfigError` 或 `InvalidConfigError`。
- **階段決策紀錄**：`[P03:DR-01]` 統一將公開與內部符號對齊為 `file_space` / `FileSpace`，不保留冗餘別名以維持 `Mode A` 純淨度。

---

## 4. 定稿審查與文檔衝擊規劃 (P04)

### 4.1 交叉驗證與靈魂拷問 (Cross-Validation & Resilience Review)

- [x] **需求對齊**：FR-01 ~ FR-03 皆已於介面簽名與實作中完整對齊
- [x] **邊界防護**：EC-01 ~ EC-03 皆有具體錯誤攔截與降級策略
- [x] **依賴純淨**：100% 符合 NFR 指標約束
- **靈魂拷問與防護解法**：
  - **問**：直接對檔案全文跑搜尋替換會不會改壞原本不在本次 `git diff` 裡的文字（例如 `2-space 縮排` 或 `workspace_root`）？
  - **解**：腳本顯式排除 `workspace`、`namespace`、`whitespace`、`2-space`、`codespace` 等保護詞，且僅針對當前 `git status` 中與本次變更相關之目標檔案集執行，替換後立刻跑 `git diff` 逐行反查腳本驗證。

### 4.2 知識庫文檔衝擊與交付規劃 (Documentation Impact Plan)

| 維度 | 文件路徑 | 變更類型 | 交付內容與重點 |
| :--- | :--- | :---: | :--- |
| **模組手冊** | `docs/file-space/README.md` & `docs/knowledge-db/README.md` | Modify | 全面更新 `file-space` 模組、CLI 與組態名稱 |
| **專題手冊** | `docs/knowledge-db/incremental_hot_reload.md` | Modify | 更新 `file-space-watcher` 與 `hook.file-space.py` |
| **設計決策** | `docs/file-space/DESIGN_NOTES.md` & `docs/knowledge-db/DESIGN_NOTES.md` | Modify | 同步更新設計決策中之 `file-space` 命名 |
| **微觀註解** | 源碼檔案 Docstrings | Modify | 同步更新 `file-space` 與 `knowledge-db` 源碼註解 |
| **發布日誌** | `CHANGELOG.md` | Modify | 於 Phase 7 結案時更新變更紀錄 |

- **決策定稿**：**[P04:DR-01]** 鎖定 `P01-05_auto.md` 規格，進入腳本化掃描替換與反查驗收。

---

## 5. 實作任務清單與偏差紀錄 (P05)

### 5.1 實作任務清單 (Task Breakdown)

- [x] **TASK-01**：編寫並執行 `git diff` 範圍掃描與物理目錄/檔案搬移及內容批次替換腳本（將 `space` 全面更名為 `file-space` / `file_space` / `FileSpace`）。
- [x] **TASK-02**：執行反向殘留查驗腳本，檢查所有 `git diff` 變更行確認零遺漏與零誤傷，並執行 `file-space`、`knowledge-db`、`agents-workflow` 之 `dev check` 與 `dev test -q`。
- [x] **TASK-DOC**：清理舊 `.modules/space` 與 `.cache/space`，執行 `install file-space@build knowledge-db@build agents-workflow@build --force` 與工作流編譯同步，驗證實機 `file-space status` 與 `knowledge-db status`。

### 5.2 實作偏差紀錄表 (Implementation Deviations)

| 任務編號 | 偏差等級 | 偏離描述與決策理由 | 處置方式 / 記錄 |
| :--- | :---: | :--- | :--- |
| - | - | 無偏差 | - |

