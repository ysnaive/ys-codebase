# 自動連續推進綜合規格與實作紀錄 (Consolidated Auto Plan & Task Log)

> 功能名稱：sub_04_ecosystem_modules_compliance_migration  
> 建立日期：2026-11-08  
> 所屬主計畫：2026_11_07_2052_jupyter_style_runtime_isolation_and_static_guardrails  
> 狀態：Completed  
> 模型：Unknown  

> 依據 P00：[P00_discuss.md](./P00_discuss.md)  
> 模板版本：v1.0  

---

## 1. 需求規格與邊界契約 (P01)

### 1.1 功能需求清單 (Functional Requirements)

| 需求編號 | 需求名稱 | 詳細規格與驗收條件 (Acceptance Criteria) | 優先級 | 對應 P00 語意 |
| :--- | :--- | :--- | :---: | :--- |
| **FR-01** | 7 大業務模組生產輸出與日誌全量遷移 (`A1` & `A2`) | 將 `dev`、`file-space`、`ast`、`knowledge-db`、`agents-workflow`、`vscode-support`、`gdrive-support` 所有非測試 `.py` 檔案中之原生 `print()`、`sys.stdout.write`、`sys.stderr.write`、`logging.*` 與自建 `_append_log` 100% 遷移至 `core.log`（`log`, `log_stream`, `log_info`, `log_warn`, `log_error`, `log_debug`, `log_file`），並消除生產檔案中之裸 `input()` / `sys.stdin` 讀取，確保前景 CLI 與測試斷言輸出 100% 相容。 | P0 | [P00:DR-01] |
| **FR-02** | 虛擬工作目錄、環境變數與子進程超時收斂 (`B4` / `B5` / `F13`) | 將 7 大模組生產代碼中之 `os.chdir()`、`os.getcwd()`、`Path.cwd()` 遷移至 `core.context.get_virtual_cwd()`（及 `bind_runtime_context`）；消除生產代碼執行期對 `os.environ` 的原地寫入/突變（改透過 `get_env`、`bind_runtime_context(env=...)` 或子進程 `env=` 傳遞）；為 `dev/tester.py` 等缺少 `timeout=` 之 `subprocess.run` 補齊明確超時防禦。 | P0 | [P00:DR-01], [P00:DR-02] |
| **FR-03** | 頂層可變狀態清零、動態載入收斂與 PEP 562 相容代理 (`C8` / `D10`) | 將 7 大模組生產代碼頂層可變容器字面量（`list`/`dict`/`set`，不含 `__all__`）轉為 `tuple` / `frozenset` / `types.MappingProxyType`；將模組級可變快取與單例狀態（如 `knowledge-db` 之 `_GLOBAL_ENGINE_INSTANCE` / `_GLOBAL_INDEX_CACHE` / `_ACTIVE_WORKER`、`file-space` 之 `_SUBSCRIBERS`、`ast` 之單例快取等）收斂至 `core.context.get_runtime_context()`，消除所有 `global` 關鍵字並提供 PEP 562 模組 `__getattr__` 相容代理；將 `dev` 與 `ast` 直接操作 `sys.modules` / `spec_from_file_location` 之邏輯收斂至 `core.loader.load_module_from_path`。 | P0 | [P00:DR-02] |
| **FR-04** | `@dataclass(frozen=True)` 與類別可變屬性收斂 (`C9`) | 將 7 大模組生產代碼中所有未設 `frozen=True` 之 `@dataclass` 補齊 `@dataclass(frozen=True)`（`__post_init__` 內之正規化賦值改用 `object.__setattr__(self, ...)`），並將類別頂層可變屬性轉為不可變容器或實例屬性。 | P0 | [P00:DR-03] |

### 1.2 邊界與異常情況 (Edge Cases & Failure Modes)

| 邊界編號 | 情境說明 | 預期防禦與處理行為 |
| :--- | :--- | :--- |
| **EC-01** | 白箱單元測試直接讀取或賦值模組私有狀態（如 `kdb_engine._GLOBAL_ENGINE_INSTANCE = None` 或 `svc_mod._IDLE_EVENT.set()`） | 透過 `RuntimeContext` 槽位結合模組輔助存取器或 PEP 562 `__getattr__`，且針對測試中會原地 `.clear()` / `.update()` 之字典（如 `_GLOBAL_INDEX_CACHE`）於 `RuntimeContext` 保存同一字典實例，確保白箱測試 100% 向後相容。 |
| **EC-02** | `@dataclass(frozen=True)` 實例於業務流程中被外部原地修改屬性（如 `InvertedIndex.doc_count = ...` 或 `SearchResult.score = ...`） | 盤點區分「純資料值物件 (`@dataclass(frozen=True)`)」與「有狀態可變容器/引擎類別（移除 `@dataclass` 改為標準 `__init__` 類別或使用 `dataclasses.replace`）」，杜絕 `FrozenInstanceError`。 |
| **EC-03** | 沙盒測試中透過 `contextlib.redirect_stdout` / `unittest.mock.patch("sys.stdout")` 攔截模組輸出 | `core.log.log()` 與 `log_stream()` 動態寫入當前 `sys.stdout` / `sys.stderr`，100% 相容所有 `redirect_stdout` / `patch("sys.stdout")` 測試斷言。 |
| **EC-04** | `knowledge-db` 於导入或初始化時設定 HuggingFace 環境變數 (`HF_HUB_DISABLE_SYMLINKS_WARNING`) | 改於模型實際載入前透過受控環境輔助或 `os.environ.setdefault` 等效上下文處理，不在生產代碼直接執行裸 `os.environ[...] = ...` 違規寫入。 |

### 1.3 非功能需求 (Non-Functional Requirements)

| 需求編號 | 類別 | 指標與量化約束 |
| :--- | :--- | :--- |
| **NFR-01** | 靜態合規零違規 | 上層 7 大模組共 115 個非測試 `.py` 檔案達成 0 處 `A1` (`print`/`stdout`/`stderr`/`logging`)、0 處 `A2` (`input`/`stdin`)、0 處 `B3` (`sys.exit`/`os._exit`)、0 處 `B4` (`os.chdir`/`os.getcwd`/`Path.cwd`)、0 處 `B5` (`os.environ` 寫入)、0 處 `C8` (頂層可變快取與 `global`)、0 處 `C9` (非 `frozen` `@dataclass` 與類別可變屬性)、0 處 `D10` (`sys.path`/`sys.modules` 直接突變)、0 處 `F13` (缺 `timeout` `subprocess` 與野執行緒)。 |
| **NFR-02** | 測試回歸率 | `dev`、`file-space`、`ast`、`knowledge-db`、`agents-workflow`、`vscode-support`、`gdrive-support` 7 大模組沙盒單元測試與 `dev check` 100% 通過。 |

### 1.4 知識庫與踩坑紀錄查閱 (Known Gotchas & CAUTIONs)

- **`[!CAUTION]` 區分不可變值物件與有狀態可變資料結構**：例如 `InvertedIndex` 或 AST 節點累積器若在建構後頻繁原地修改欄位，直接加 `@dataclass(frozen=True)` 會引發 `FrozenInstanceError`；此類有狀態容器應使用標準 `class` + `__init__`（而非無 `frozen=True` 之 `@dataclass`），以同時滿足 C9 靜態守門與執行期效率。
- **`[!NOTE]` `core.log` 參數映射**：`print(msg, file=sys.stderr, flush=True)` 對應 `log(msg, stream="stderr", flush=True)`；`print(msg, end="")` 對應 `log(msg, end="")` 或 `log_stream(msg)`。

---

## 2. 架構設計與異動檔案清單 (P02)

### 2.1 模組架構與核心資料流 (Architecture & Data Flow)

```text
[7 Upper-Layer Modules: dev, file-space, ast, knowledge-db, agents-workflow, vscode-support, gdrive-support]
   │
   ├── Terminal & File Output (A1) ──────────► core.log.{log, log_stream, log_info, log_warn, log_error, log_debug, log_file}
   ├── CWD & Env Lookup (B4, B5) ────────────► core.context.{get_virtual_cwd, get_env, bind_runtime_context}
   ├── Module-Level Runtime State (C8) ──────► core.context.get_runtime_context().module_states + PEP 562 __getattr__
   ├── Immutable Value Contracts (C9) ───────► @dataclass(frozen=True) / MappingProxyType / tuple / frozenset
   └── Dynamic Script Loading (D10) ─────────► core.loader.load_module_from_path
```

### 2.2 受影響與新建檔案清單 (Impacted & New Files Inventory)

| 檔案路徑 | 類型 | 職責與變更說明 |
| :--- | :---: | :--- |
| `ys_codebase/source/core/core/context.py` | Modify | 擴充 `RuntimeContext.module_states` 通用命名空間狀態槽位輔助方法，供上層 7 大模組收斂頂層可變快取 |
| `ys_codebase/source/file-space/file_space/*.py` & `scripts/*.py` | Modify | 遷移 `print`/`logging` 至 `core.log`、收斂 `_SUBSCRIBERS` 等頂層狀態至 `RuntimeContext`、凍結 `@dataclass(frozen=True)` |
| `ys_codebase/source/vscode-support/vscode_support/*.py` & `scripts/*.py` | Modify | 遷移 `print`/`logging` 至 `core.log`、轉化頂層可變常數為不可變容器、凍結 `@dataclass(frozen=True)` |
| `ys_codebase/source/gdrive-support/gdrive_support/*.py` & `scripts/*.py` | Modify | 遷移 `print`/`logging` 與 `_append_log` 至 `core.log`、收斂頂層可變狀態、凍結 `@dataclass(frozen=True)` |
| `ys_codebase/source/dev/dev/*.py` & `scripts/*.py` | Modify | 遷移 `print`/`logging` 至 `core.log`、將 `os.getcwd`/`Path.cwd` 遷移至 `get_virtual_cwd`、消除 `os.environ` 寫入、為 `subprocess.run` 補齊 `timeout=`、收斂頂層狀態與 `@dataclass(frozen=True)` |
| `ys_codebase/source/ast/ast_engine/**/*.py` & `scripts/*.py` | Modify | 遷移 `print`/`logging` 至 `core.log`、將 `os.getcwd`/`Path.cwd` 遷移至 `get_virtual_cwd`、收斂頂層可變快取/容器與 `global`、處理 `@dataclass(frozen=True)` 與 `core.loader` |
| `ys_codebase/source/knowledge-db/knowledge_db/*.py` & `scripts/*.py` | Modify | 遷移 `print`/`logging` 至 `core.log`、將 `os.getcwd`/`Path.cwd` 遷移至 `get_virtual_cwd`、消除 `os.environ` 直接寫入、收斂 `_GLOBAL_ENGINE_INSTANCE`/`_GLOBAL_INDEX_CACHE`/`_ACTIVE_WORKER` 等頂層狀態與 `global`、處理 `@dataclass(frozen=True)` |
| `ys_codebase/source/agents-workflow/agents_workflow/**/*.py` & `scripts/*.py` | Modify | 遷移 `print`/`logging` 至 `core.log`、消除裸 `input()`、將 `os.getcwd`/`Path.cwd` 遷移至 `get_virtual_cwd`、收斂頂層可變容器與 `@dataclass(frozen=True)` |
| `docs/_project/STANDARDS.md` & `docs/README.md` | Modify | 更新全倉 9 大模組統一遵循 `core.log`、`RuntimeContext` 與不可變契約之說明 |

### 2.3 架構決策記錄 (Architecture Decision Records)

- **[P02:DR-01] `RuntimeContext.get_module_state(namespace, factory)` 通用狀態槽位**：
  - 於 `core.context.RuntimeContext` 提供執行緒安全的 `get_module_state(key: str, default_factory: Callable[[], Any]) -> Any`，使上層業務模組（如 `knowledge-db`、`ast`、`file-space`、`agents-workflow`）無需在模組頂層宣告可變字典或 `global` 變數，同時當 `RuntimeContext.reset_all_caches()` 被呼叫時可一併重置或維持受控生命週期。
- **[P02:DR-02] 有狀態引擎/索引類別與純資料 `@dataclass(frozen=True)` 邊界**：
  - 凡屬純資料傳輸物件（DTO / Config / Result / Spec）一律標註 `@dataclass(frozen=True)`（`__post_init__` 使用 `object.__setattr__`）；凡屬建構後需頻繁原地增刪內部結構之有狀態物件（如 `InvertedIndex`、`VectorIndex` 或 AST 建立期累加器），改用標準 `class` + 顯式 `__init__`，徹底杜絕未凍結 `@dataclass` (C9) 與 `FrozenInstanceError`。

---

## 3. 介面契約與 API 簽名 (P03)

### 3.1 介面契約與核心簽名 (Interface Inventory & Method Signatures)

```python
# ys_codebase/source/core/core/context.py
class RuntimeContext:
    module_states: Dict[str, Any]
    def get_module_state(self, key: str, default_factory: Callable[[], Any]) -> Any: ...
    def set_module_state(self, key: str, value: Any) -> None: ...
```

- **錯誤與例外契約 (Error & Exception Contracts)**：
  - 所有遷移至 `core.log` 之 CLI 錯誤輸出於 `stream="stderr"` 時自動觸發 `record_error_hint`，保持既有返回碼（`0` / `1` / 非零整數）與例外型別 100% 不變。
- **階段決策紀錄**：`[P03:DR-01]` 對既有測試透過 `setattr(module, "_PRIVATE_VAR", ...)` 進行白箱覆寫的屬性，於模組讀取端優先檢查 `globals().get("_PRIVATE_VAR")` 或同步映射至 `RuntimeContext.module_states`，確保白箱測試零破壞。

---

## 4. 定稿審查與文檔衝擊規劃 (P04)

### 4.1 交叉驗證與靈魂拷問 (Cross-Validation & Resilience Review)

- [x] **需求對齊**：FR-01 ~ FR-04 皆已於介面簽名與實作中完整對齊
- [x] **邊界防護**：EC-01 ~ EC-04 皆有具體錯誤攔截與降級策略
- [x] **依賴純淨**：100% 符合 NFR 指標約束
- **靈魂拷問與防護解法**：
  - *問：7 大模組檔案數眾多（共 115 個非測試 `.py` 檔），如何確保遷移過程不遺漏任何一處 A1~F13 違規且不破壞既有測試？*
  - *答*：採用分批正交模組推進並搭配 AST 靜態掃描驗證腳本逐模組確認 A1~F13 違規數歸零，每完成一批模組立即執行對應 `dev test <mod> -q --sync` 與 `dev check <mod>`。

### 4.2 知識庫文檔衝擊與交付規劃 (Documentation Impact Plan)

| 維度 | 文件路徑 | 變更類型 | 交付內容與重點 |
| :--- | :--- | :---: | :--- |
| **模組手冊** | `docs/_project/STANDARDS.md` & `docs/README.md` | Modify | 更新全生態系模組統一採用 `core.log`、`RuntimeContext` 與 `@dataclass(frozen=True)` 之架構規範 |
| **專題手冊** | `docs/<Category>/[topic].md` | N/A | 內部實作合規遷移，無公開 CLI 語法變更 |
| **設計決策** | `docs/<Category>/DESIGN_NOTES.md` | N/A | 無新增反直覺妥協 |
| **微觀註解** | 源碼檔案 Docstrings | Modify | 同步維護遷移後函式與類別之 Docstring |
| **發布日誌** | `CHANGELOG.md` | Modify | 於 Phase 7 結案時記錄 `sub_04` 7 大模組全量合規遷移摘要 |

- **決策定稿**：**[P04:DR-01]** 規格確認無誤，啟動 `Pre-Code Analyze Gate` 與分批模組遷移。

---

## 5. 實作任務清單與偏差紀錄 (P05)

### 5.1 實作任務清單 (Task Breakdown)

- [x] **TASK-01**：擴充 `core/context.py` 之 `module_states` 輔助方法，並完成輕量模組群（`file-space`、`vscode-support`、`gdrive-support`）之 A1~F13 全量合規遷移與測試驗證
- [x] **TASK-02**：完成 `dev` 與 `knowledge-db` 模組之 A1~F13 全量合規遷移（含 `core.log`、`get_virtual_cwd`、`subprocess` timeout、`RuntimeContext` 狀態收斂與 `@dataclass(frozen=True)`）與測試驗證
- [x] **TASK-03**：完成 `ast` 與 `agents-workflow` 模組之 A1~F13 全量合規遷移（含 `core.log`、移除裸 `input()`、`get_virtual_cwd`、頂層不可變容器與 `@dataclass(frozen=True)`）與測試驗證
- [x] **TASK-04**：執行上層 7 大模組全量 AST 13 項守門規則零違規掃描與沙盒回歸測試（`dev test` & `dev check`）
- [x] **TASK-DOC**：同步更新 `docs/_project/STANDARDS.md`、`docs/README.md` 與微觀代碼 Docstrings

### 5.2 實作偏差紀錄表 (Implementation Deviations)

| 任務編號 | 偏差等級 | 偏離描述與決策理由 | 處置方式 / 記錄 |
| :--- | :---: | :--- | :--- |
| - | - | 無偏差 | - |
