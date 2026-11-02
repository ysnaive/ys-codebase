# 自動連續推進綜合規格與實作紀錄 (Consolidated Auto Plan & Task Log)

> 功能名稱：post_abstraction_audit_and_update_deps  
> 建立日期：2026-11-02  
> 所屬主計畫：N/A  
> 狀態：Completed  
> 模型：Gemini 4 Argon (Low)  

> 依據 P00：[P00_discuss.md](./P00_discuss.md)  
> 模板版本：v1.0  

---

## 1. 需求規格與邊界契約 (P01)

### 1.1 功能需求清單 (Functional Requirements)

| 需求編號 | 需求名稱 | 詳細規格與驗收條件 (Acceptance Criteria) | 優先級 | 對應 P00 語意 |
| :--- | :--- | :--- | :---: | :--- |
| **FR-01** | `cmd_update` 聯合拓撲相依解析與自動拉取升級 | 升級 `Installer.cmd_update`，將 `"core"` 置於候選評估首位（當 `core` 具有相容新版時，同步提供候選 `core` 版號供同批次下游模組相容性判定）；接著將待更新模組目標版號與其餘已安裝模組送入聯合相依解析：自動拉取新版新增之未安裝相依模組（如 `file-space`、`ast`）或連帶升級已安裝相依模組，並對所有版號上升之模組執行 `act_migrate`、對新安裝之相依模組輸出 Onboarding 指引。 | P0 | [P00:DR-01] |
| **FR-02** | 標準重載與自癒管線相依交集自檢 (`reconcile_installed_dependencies`) | 於 `AtomicEngine` 實作 `reconcile_installed_dependencies(provider_url: Optional[str] = None) -> List[Tuple[str, Optional[str], str]]`，並嵌入 `act_reload` Stage 1.5（於 Stage 2 物化與 Stage 4 `on_reload` 事件廣播前執行）：① 本地未安裝之相依模組直接解析約束交集並自動下載、註冊與物化；② 本地已安裝之相依模組若不滿足上游新增約束，自動計算所有上游對該模組之約束交集並升級至最高相容版號；③ 若兩模組對同一相依模組之約束不存在版號交集（衝突），拋出明確例外阻斷升級。 | P0 | [P00:DR-05] |
| **FR-03** | `ISS-01` & `ISS-04` 空間表 Provider 收斂與 PEP 562 延遲匯入 | 於 `file_space/providers.py` 統一實作 `get_registered_file_spaces_table` 與 `get_knowledge_db_spaces`；`knowledge_db/providers.py` 移除頂層 `import knowledge_db`，改以純標準庫路徑掛載 `file_space` 並委派呼叫 `file_space.providers.get_knowledge_db_spaces`；同步將 `knowledge_db/__init__.py` 與 `ast_engine/__init__.py` 改為 PEP 562 `_LAZY_EXPORTS` + `__getattr__` 延遲匯入，確保無 `.venv`（無 `networkx` / `fastembed`）時 `KNOWLEDGE_DB_SPACE` 計算與頂層套件匯入 100% 零崩潰。 | P0 | [P00:DR-02] |
| **FR-04** | `ISS-02` `knowledge-db` 版號對齊與 `dev check` 守門 | 將 `knowledge_db/__init__.py` 之 `__version__` 與 `CHANGELOG.md` 對齊為 `"1.2.0.0"`；於 `dev/checker.py` 新增套件 `__init__.py` 之 `__version__` 常數與 `manifest.json["version"]` 一致性靜態 AST 檢核（不一致時回報 `CheckSeverity.FAIL`）。 | P1 | [P00:DR-03] |
| **FR-05** | `ISS-03` 根目錄 `README.md` 與 `docs/README.md` 七大模組三階 DAG 同步 | 更新根目錄 `README.md` 與 `docs/README.md` 之架構圖、模組總覽表（擴充為 7 大模組，納入 `file-space` $\to$ `ast` $\to$ `knowledge-db` 三階 DAG）、`README.md` §3.3 空間設定教學（`config/file-space/contribute.json` 與 `config/knowledge-db/contribute.json` 之 `space_weights`）及 §4 CLI 速查表（新增 `file-space` 與 `ast` 指令）。 | P1 | [P00:DR-04] |

### 1.2 邊界與異常情況 (Edge Cases & Failure Modes)

| 邊界編號 | 情境說明 | 預期防禦與處理行為 |
| :--- | :--- | :--- |
| **EC-01** | 兩個模組對同一相依模組宣告無交集之版本約束（如 `mod_a` 要求 `dep>=2.0.0` 而 `mod_b` 要求 `dep<2.0.0` 或已安裝鎖定無交集） | `act_solve_deps` / `reconcile_installed_dependencies` 檢測出可用版本池中無任何版本同時滿足雙方約束，立即拋出 `RuntimeError`（含雙方模組名與約束明細），`cmd_update` / `cmd_install` 捕獲後執行 `act_restore_snapshot` 100% 回滾。 |
| **EC-02** | 已安裝模組處於 `@build`（或 `X.Y.Z.build`）開發模式時執行 `update` 或 `act_reload` 相依自檢 | `cmd_update` 跳過 `@build` 模組本身的版本升級，但仍讀取該 `@build` 模組 `manifest.json` 的 `dependencies` 納入相依自檢；且當其他模組依賴該 `@build` 模組時，以剝除 `.build` 後之基底版號比對約束相容性。 |
| **EC-03** | 全新環境執行 `restore` 或 `install` 時 `.venv` 尚未安裝 `networkx` 或 `fastembed`，隨即觸發 `act_reload` -> `on_reload` -> `agents-workflow release` 解算 `KNOWLEDGE_DB_SPACE` | `knowledge_db/providers.py` 與 `file_space/providers.py` 100% 僅依賴 Python 標準庫與 `core`，不觸發 `ast_engine.graph` (`networkx`) 或 `fastembed` 載入，正確渲染完整 Markdown 空間表格。 |
| **EC-04** | 模組未定義 `__version__` 或 `__version__` 為動態表達式而非字串常數 | `dev/checker.py` 僅在套件 `__init__.py` 頂層存在靜態字串常數賦值 `__version__ = "..."` 時比對 `manifest.json["version"]`，未定義時不誤報。 |

### 1.3 非功能需求 (Non-Functional Requirements)

| 需求編號 | 類別 | 指標與量化約束 |
| :--- | :--- | :--- |
| **NFR-01** | 零第三方啟動依賴 | `knowledge_db/providers.py`、`file_space/providers.py`、以及 `import knowledge_db` / `import ast_engine` 頂層匯入在無第三方套件環境下 100% 成功且耗時 `< 20ms`。 |
| **NFR-02** | 向下相容性 | `from knowledge_db import ...` 與 `from ast_engine import ...` 原有 `__all__` 匯出符號 100% 透過 PEP 562 `__getattr__` 無損相容。 |

### 1.4 知識庫與踩坑紀錄查閱 (Known Gotchas & CAUTIONs)

- **`[!CAUTION]` `act_reload` 與 `sync_pip_dependencies` 時序（`core` `[DN-14]` / `agents-workflow`）**：`act_reload` 內部廣播 `on_reload` 時尚未執行 `sync_pip_dependencies()`，因此所有掛載於 `on_reload` 或 `agents-workflow` Stage 1 Computed Token 的 Provider 函式必須 100% 零第三方 pip 依賴。
- **`[!NOTE]` `index.json["releases"]` 依賴覆寫優先權（`core` `[DN-15]`）**：讀取已安裝或候選模組之 `dependencies` 時，若 `module.mirror://<mod>/index.json` 或 Provider `index.json` 之 `releases[<ver>]["dependencies"]` 存在事後修補覆寫，必須優先採用覆寫後之 `dependencies`。

---

## 2. 架構設計與異動檔案清單 (P02)

### 2.1 模組架構與核心資料流 (Architecture & Data Flow)

```text
[yscb.py update / restore / reload]
       │
       ▼
[Installer.cmd_update] ──(1. Core 先行評估 candidate_core_ver)──► [AtomicEngine._discover / act_solve_deps]
       │                                                                    │
       │  (2. 收集已安裝模組 + 更新目標，驗證約束交集並展開新相依模組)          ▼
       └───────────────────────────────────────────────────────► [reconcile_installed_dependencies]
                                                                  ├── 未安裝相依 D -> 求交集 v* -> 自動下載 + 註冊
                                                                  ├── 已安裝相依 D 不滿足新約束 -> 求交集 v* -> 自動升級
                                                                  └── 約束無交集 (C_A ∩ C_B = ∅) -> 拋出衝突阻斷 + Snapshot 回滾
                                                                            │
                                                                            ▼
                                                                 [AtomicEngine.act_reload]
                                                                  ├── Stage 1: 鏡像自癒拉取
                                                                  ├── Stage 1.5: reconcile_installed_dependencies 自檢補齊
                                                                  ├── Stage 2 & 3: 解壓物化 .modules/ + 組態剝離
                                                                  └── Stage 4: contributes 注入 + on_reload 廣播
                                                                            │
                                                                            ▼
                                                             [KNOWLEDGE_DB_SPACE 計算錨點]
                                                              knowledge_db.providers.get_knowledge_db_spaces
                                                                └── 純標準庫委派 -> file_space.providers.get_knowledge_db_spaces
```

### 2.2 受影響與新建檔案清單 (Impacted & New Files Inventory)

| 檔案路徑 | 類型 | 職責與變更說明 |
| :--- | :---: | :--- |
| `ys_codebase/source/core/core/engine.py` | Modify | 支援候選 `core` 版號覆寫相容性探針、新增 `_read_installed_module_dependencies` 與 `reconcile_installed_dependencies` 相依交集自檢與自動補齊/升級方法，並嵌入 `act_reload` Stage 1.5 及強化 `act_solve_deps` 雙向來源約束衝突診斷訊息。 |
| `ys_codebase/source/core/core/installer.py` | Modify | 升級 `cmd_update`：優先評估 `"core"` 候選升級版號，結合 `act_solve_deps` 與 `reconcile_installed_dependencies` 自動驗證並拉取新版新增之相依模組或連帶升級相依模組，執行 `act_migrate` 與新相依模組 Onboarding。 |
| `ys_codebase/source/core/tests/test_engine.py` | Modify | 新增 `update` 新相依自動拉取、已安裝相依自動交集升級、無交集相依衝突阻斷回滾與 `act_reload` Stage 1.5 自動補齊缺失相依之單元與邊界測試。 |
| `ys_codebase/source/file-space/file_space/providers.py` | Modify | 收斂實作共用空間載入與 `get_knowledge_db_spaces(context=None, **kwargs)` 及 `get_registered_file_spaces_table(context=None)`。 |
| `ys_codebase/source/file-space/tests/test_service_and_cli.py` | Modify | 新增 `get_knowledge_db_spaces` 與 `get_registered_file_spaces_table` 渲染測試。 |
| `ys_codebase/source/knowledge-db/knowledge_db/providers.py` | Modify | 移除頂層 `import knowledge_db`，以純標準庫掛載 `file_space` 並直接轉發呼叫 `file_space.providers.get_knowledge_db_spaces`。 |
| `ys_codebase/source/knowledge-db/knowledge_db/__init__.py` | Modify | 將 `__version__` 修正為 `"1.2.0.0"`，並重構為 PEP 562 `_LAZY_EXPORTS` + `__getattr__` 延遲匯入。 |
| `ys_codebase/source/knowledge-db/tests/test_file_space.py` | Modify | 對齊 `file_space.providers.FileSpaceManager` mock 座標，並新增無 `networkx` / `fastembed` 下匯入 `knowledge_db.providers` 與 `knowledge_db` 頂層套件之隔離測試。 |
| `ys_codebase/source/ast/ast_engine/__init__.py` | Modify | 重構為 PEP 562 `_LAZY_EXPORTS` + `__getattr__` 延遲匯入，避免匯入頂層套件時載入 `networkx`。 |
| `ys_codebase/source/ast/tests/test_partial_and_outline.py` | Modify | 新增 `ast_engine` PEP 562 延遲載入與符號完整性驗證測試。 |
| `ys_codebase/source/dev/dev/checker.py` | Modify | 於 `_check_manifest` 新增套件 `__init__.py` 之 `__version__` 與 `manifest.json["version"]` 一致性 AST 檢核。 |
| `ys_codebase/source/dev/tests/test_checker.py` | Modify | 新增 `__version__` 與 `manifest.json` 不一致時回報 `FAIL` 之單元測試。 |
| `README.md` | Modify | 同步七大模組三階 DAG 架構圖、模組清單、`file-space`/`ast`/`knowledge-db` 設定步驟與 CLI 速查表。 |
| `docs/README.md` | Modify | 同步七大模組三階 DAG 架構圖、導覽地圖（新增 `docs/file-space/` 與 `docs/ast/`）與模組註冊表。 |
| `docs/core/DESIGN_NOTES.md` | Modify | 登錄 `[DN-16]` 標準重載與更新管線之相依交集自檢與自動自癒機制。 |
| `CHANGELOG.md` | Modify | 修正 `sub_02_knowledge_db_ast_consumer_migration` 版號標記為 `1.2.0.0` 並於結案時記錄本計畫變更。 |

### 2.3 架構決策記錄 (Architecture Decision Records)

- **[P02:DR-01] 相依交集自檢與衝突判定演算法 (`Constraint Intersection & Conflict Detection`)**：
  - 在 `AtomicEngine` 中維護每個相依目標模組 $D$ 的上游需求來源表 `requesters: Dict[str, List[Tuple[str, str]]]`（記錄 `(requester_mod, constraint)`）。
  - 當多個模組對同一模組 $D$ 提出約束時，合成聯合約束 $C_{\text{joint}} = c_1, c_2, \dots, c_k$：
    - 若 $D$ 已安裝（版號 $v_{\text{cur}}$）且不在主動降級範圍：先檢查 $v_{\text{cur}}$ 是否滿足 $C_{\text{joint}}$；若滿足則直接通過。
    - 若 $D$ 未安裝、或已安裝之 $v_{\text{cur}}$ 不滿足 $C_{\text{joint}}$：向 Provider 查詢 $D$ 的可用版本池並以 `semver.find_best_version(vers, C_joint)` 求交集最高版號 $v^*$（若 $D$ 已安裝且非顯式指定跨主版號，優先嘗試滿足當前 Major Lock 與 $C_{\text{joint}}$ 之交集，若無則在全可用版本中求 $C_{\text{joint}}$ 交集）。
    - 若可用版本池中無任何版本可同時滿足 `requesters` 的所有約束（即兩模組對 $D$ 的相依約束無交集），立即拋出包含完整來源對照（例如 `"Dependency conflict for 'ast': required '>=2.0.0' by 'mod_a' vs '<2.0.0' by 'mod_b' — no overlapping version available"`）之 `RuntimeError`。
- **[P02:DR-02] PEP 562 延遲匯入與 `providers.py` 單一真理收斂**：
  - `file_space/providers.py` 僅使用 Python 標準庫與同套件之 `FileSpaceManager`，同時提供 `get_registered_file_spaces_table` 與 `get_knowledge_db_spaces`；`knowledge_db/providers.py` 透過 `_ensure_file_space_path()` 掛載 `file_space` 後直接匯入並轉發 `get_knowledge_db_spaces`。
  - `ast_engine/__init__.py` 與 `knowledge_db/__init__.py` 將所有子模組匯出移入 `_LAZY_EXPORTS` 字典並由 `__getattr__` 與 `__dir__` 動態解析，使頂層 `import ast_engine` 與 `import knowledge_db` 僅執行路徑掛載與常數宣告，零第三方庫載入。

---

## 3. 介面契約與 API 簽名 (P03)

### 3.1 介面契約與核心簽名 (Interface Inventory & Method Signatures)

```python
# ys_codebase/source/core/core/engine.py
class AtomicEngine:
    def _get_installed_core_version_for_compat(self, candidate_core_version: Optional[str] = None) -> Optional[str]: ...
    def _is_dependencies_compatible_with_env(self, deps: Any, candidate_core_version: Optional[str] = None) -> bool: ...
    def _read_installed_module_dependencies(self, mod: str, ver: str, provider_url: str = "") -> Dict[str, str]: ...
    def reconcile_installed_dependencies(
        self,
        provider_url: Optional[str] = None,
        candidate_overrides: Optional[Dict[str, str]] = None,
        strict: bool = True,
    ) -> List[Tuple[str, Optional[str], str]]: ...

# ys_codebase/source/file-space/file_space/providers.py
def get_registered_file_spaces_table(context: Optional[Any] = None) -> str: ...
def get_knowledge_db_spaces(context: Optional[Any] = None, **kwargs: Any) -> str: ...

# ys_codebase/source/knowledge-db/knowledge_db/providers.py
def _ensure_file_space_path() -> None: ...
def get_knowledge_db_spaces(context: Optional[Any] = None, **kwargs: Any) -> str: ...

# ys_codebase/source/dev/dev/checker.py
class Checker:
    def _check_package_dunder_version(self, name: str, real_dir: str, manifest_ver: str, report: CheckReport) -> None: ...
```

- **錯誤與例外契約 (Error & Exception Contracts)**：
  - 當兩個模組對同一相依模組之版本約束不存在交集時，`act_solve_deps` 與 `reconcile_installed_dependencies` 拋出 `RuntimeError`，訊息格式明確列出衝突目標模組與各請求方之約束條件。
  - `Checker._check_package_dunder_version` 檢測到 `<pkg>/__init__.py` 頂層 `__version__` 字串常數與 `manifest.json["version"]` 不符時，附加 `CheckIssue(severity=CheckSeverity.FAIL, category="MANIFEST", ...)`。
- **階段決策紀錄**：`[P03:DR-01]` `reconcile_installed_dependencies` 回傳 `List[Tuple[str, Optional[str], str]]`（即 `(mod_name, old_ver_or_None, new_ver)`），供 `cmd_update` 與 `act_reload` 統一掌握哪些相依模組是新補裝（`old_ver is None`）或自動升級（`old_ver != new_ver`）。

---

## 4. 定稿審查與文檔衝擊規劃 (P04)

### 4.1 交叉驗證與靈魂拷問 (Cross-Validation & Resilience Review)

- [x] **需求對齊**：FR-01 ~ FR-05 皆已於介面簽名與實作中完整對齊
- [x] **邊界防護**：EC-01 ~ EC-04 皆有具體錯誤攔截與降級策略
- [x] **依賴純淨**：100% 符合 NFR-01 與 NFR-02 指標約束
- **靈魂拷問與防護解法**：
  - *問：若 `act_reload` Stage 1.5 執行 `reconcile_installed_dependencies` 時，某個模組處於離線環境且所有相依模組已存在於 `installed_modules` 且版號相容，是否會發起不必要的網路請求？*
  - *答*：不會。`_read_installed_module_dependencies` 優先直接讀取本地 `.modules/<mod>/manifest.json` 或 `.mirror/<mod>/<ver>.zip` 內之 `manifest.json`（並疊加本地 `.mirror/<mod>/index.json` 覆寫）；若所有宣告之相依模組皆已在 `installed_modules` 中且當前版號已滿足約束交集（`semver.match_constraint(cur_dep_ver, joint_constraint) == True`），**零 Provider 查詢、零網路請求直接 O(1) 放行**！唯有當發現缺失未安裝相依模組或已安裝版號不滿足約束時，才會查詢 Provider 解析最佳交集版本。

### 4.2 知識庫文檔衝擊與交付規劃 (Documentation Impact Plan)

| 維度 | 文件路徑 | 變更類型 | 交付內容與重點 |
| :--- | :--- | :---: | :--- |
| **模組手冊** | `README.md`, `docs/README.md` | Modify | 七大模組三階 DAG 架構圖、模組表、`file-space`/`ast`/`knowledge-db` 設定步驟與 CLI 速查表 |
| **專題手冊** | `docs/core/README.md` | N/A | 既有架構描述已涵蓋 `AtomicEngine` |
| **設計決策** | `docs/core/DESIGN_NOTES.md` | Modify | 登記 `[DN-16]` 標準重載與更新管線之相依交集自檢與自動自癒機制 |
| **微觀註解** | 源碼檔案 Docstrings | Modify | 同步更新 `engine.py`、`installer.py`、`providers.py`、`checker.py` Docstring |
| **發布日誌** | `CHANGELOG.md` | Modify | 修正 `1.2.0.0` 版號標記並記錄本計畫變更摘要 |

- **決策定稿**：**[P04:DR-01]** 確認 `reconcile_installed_dependencies` 在已滿足約束時採本地 Manifest 零網路短路設計，確保日常 `reload` 效能與離線韌性。

---

## 5. 實作任務清單與偏差紀錄 (P05)

### 5.1 實作任務清單 (Task Breakdown)

- [x] **TASK-01**：實作 `file_space/providers.py` 與 `knowledge_db/providers.py` 空間表收斂，以及 `knowledge_db/__init__.py`、`ast_engine/__init__.py` PEP 562 延遲匯入與 `1.2.0.0` 版號對齊（`FR-03`, `FR-04`, `EC-03`, `NFR-01`, `NFR-02`）
- [x] **TASK-02**：實作 `dev/checker.py` 套件 `__init__.py` 之 `__version__` 與 `manifest.json["version"]` 一致性 AST 檢核（`FR-04`, `EC-04`）
- [x] **TASK-03**：實作 `core/engine.py` 與 `core/installer.py` 之 `reconcile_installed_dependencies`、`act_reload` Stage 1.5 相依自癒與 `cmd_update` 聯合相依解析及無交集衝突阻斷回滾（`FR-01`, `FR-02`, `EC-01`, `EC-02`）
- [x] **TASK-04**：編寫與執行 `file-space`、`ast`、`knowledge-db`、`dev`、`core` 單元與邊界測試，並安裝 `@build` 熱部署與更新 `agents-workflow release`
- [x] **TASK-DOC**：同步更新 `README.md`、`docs/README.md`、`docs/core/DESIGN_NOTES.md` (`[DN-16]`) 與 `CHANGELOG.md`（`FR-05`）

### 5.2 實作偏差紀錄表 (Implementation Deviations)

| 任務編號 | 偏差等級 | 偏離描述與決策理由 | 處置方式 / 記錄 |
| :--- | :---: | :--- | :--- |
| - | - | 無偏差 | - |

