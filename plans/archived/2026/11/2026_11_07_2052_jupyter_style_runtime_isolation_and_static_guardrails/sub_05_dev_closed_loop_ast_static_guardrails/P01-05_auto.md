# 自動連續推進綜合規格與實作紀錄 (Consolidated Auto Plan & Task Log)

> 功能名稱：sub_05_dev_closed_loop_ast_static_guardrails  
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
| **FR-01** | 廢除動態 `custom_checks` 擴充點與清理殘留 | 物理刪除 `ys_codebase/source/dev/contributes/_format.json`；移除 `Checker._check_custom_rules` 與 `_resolve_callable` 動態載入邏輯；清理 `ys_codebase/source/dev/contributes/_manifest.md`、`docs/dev/architecture.md` 與 `docs/dev/README.md` 中關於 `custom_checks` 之描述。 | P0 | [P00:DR-01] |
| **FR-02** | 單次遍歷 `_SourceGuardrailVisitor` 與符號別名/反射防規避基座 | 於 `ys_codebase/source/dev/dev/checker.py` 實作 `_SourceGuardrailVisitor(ast.NodeVisitor)`，對每個非 `tests/` 之 `.py` 生產檔僅執行單次 AST 遍歷，內建 `import ... as ...` 與 `from <mod> import <symbol>` 符號綁定表，並攔截對受管基礎模組（`os`, `sys`, `subprocess`, `threading`, `signal`, `builtins`, `importlib`）之常數 `getattr`/`setattr`/`delattr` 反射規避，以及整合既有 `Zero Probing` 硬編碼字串檢查與裸 `except:` 警告。 | P0 | [P00:DR-02] |
| **FR-03** | 類別 A~B 靜態守門規則（I/O 串流、進程終止、CWD、`os.environ`、Signal） | 實作 `A1`（禁止 `print`、`pprint.pprint`、`sys.stdout/stderr.write/writelines`、`logging.*`、`traceback.print_exc/print_exception`）、`A2`（禁止 `input`、`sys.stdin.read/readline/readlines`）、`B3`（禁止 `sys.exit`、`os._exit`）、`B4`（禁止 `os.chdir`、`os.fchdir`、`os.getcwd`、`Path.cwd`）、`B5`（禁止 `os.environ` 寫入/刪除/原地方法與 `os.putenv`/`os.unsetenv`）、`B6`（禁止 `signal.signal`），違規一律回報 `CheckSeverity.FAIL`，並嚴格對齊底層基座座標豁免表。 | P0 | [P00:DR-02] |
| **FR-04** | 類別 C~F 靜態守門規則（記憶體狀態、動態載入、原子改名、子進程/執行緒） | 實作 `C7`（禁止函式可變預設參數含 `list()/dict()/set()/bytearray()/defaultdict()/deque()/Counter()/SimpleNamespace()`）、`C8`（禁止 `global`、函式內 `globals()[...] = ...`/`setdefault`/`update` 動態寫入、模組頂層含 `if/try/with` 分支與 `AugAssign` 之可變容器或 `= None` 單例賦值）、`C9`（禁止非 `frozen=True` 之 `@dataclass` 與非 `Enum` 類別頂層可變屬性）、`D10`（禁止非 `core` 修改 `sys.path`、直接寫入/刪除 `sys.modules`、直接呼叫 `spec_from_file_location`）、`D11`（禁止 `eval`/`exec`/`__import__`）、`E12`（禁止 `os.rename`/`os.renames`/`Path.rename`）、`F13`（禁止無 `timeout=` 之 `subprocess.run/call/check_call/check_output`、`os.system`/`os.popen` 與未受管 `threading.Thread`/`threading.Timer`）。 | P0 | [P00:DR-02] |
| **FR-05** | 通用化 Step 6 Hook 腳本檢查 (`scripts/hook.*.py`) 與全倉合規收斂 | 擴展 `Checker._check_sandbox_hooks` 檢查 `scripts/hook.*.py`（如 `hook.core.py`、`hook.dev.py`），移除頂層 `ast.Assign` 無條件放行漏洞（僅允許不可變常數/同步原語賦值），保留 Hook 函式參數簽名檢查；同步清理 `knowledge-db/scripts/hook.core.py` 殘留之 `globals()[...] = ...` 與 `dev/dev/testing/runner.py` 之 `getattr(sys, "modules")`，補齊 `dev/tests/test_checker.py` 單元測試並達成全倉 9 大模組 `dev check --all` 零違規 PASS。 | P0 | [P00:DR-03], [P00:DR-04] |

### 1.2 邊界與異常情況 (Edge Cases & Failure Modes)

| 邊界編號 | 情境說明 | 預期防禦與處理行為 |
| :--- | :--- | :--- |
| **EC-01** | 透過 `from os import getcwd, environ, rename` 或 `import subprocess as sp` 別名呼叫受禁 API | `_SourceGuardrailVisitor` 於 `visit_Import` / `visit_ImportFrom` 記錄符號映射，解析呼叫與下標目標時還原為真實 `(module, symbol)`，確保 100% 攔截無漏網。 |
| **EC-02** | 透過 `getattr(os, "environ")[k] = v`、`getattr(sys, "exit")(1)` 或函式內 `globals()["_CACHE"] = {}` 規避屬性檢查 | 識別常數字串參數之 `getattr`/`setattr`/`delattr` 並映射回等效 `module.attr` AST 檢查；識別函式內針對 `globals()` 的下標寫入/刪除與 `.setdefault()`/`.update()` 並觸發 `C8` `FAIL`（模組級 `__getattr__` 或相容遷移 `globals().pop(...)` 唯讀移除舊鍵不誤殺）。 |
| **EC-03** | 模組頂層合法不可變常數、同步原語或 `__all__` 匯出清單 | `C8` 明確允許 `__all__`（字串 list/tuple）、`Final` 標註常數、`tuple`/`frozenset`/`MappingProxyType`、`threading.Lock/RLock/Event/Condition/Semaphore`、`contextvars.ContextVar`、`re.compile`、`TypeVar` 與基礎常數字面量（`str`/`int`/`float`/`bool`/`bytes`/`Ellipsis`），僅對 `= None` 可變單例槽位與可變容器報 `FAIL`。 |
| **EC-04** | 各模組 `tests/` 目錄下之測試案例使用 `print()`、`os.environ`、`threading.Thread` 或 Mock 類別 | `_check_source_files` 維持排除 `tests/` 子目錄（`tests/` 由專屬 `_check_test_classes` 驗證 `YSCBTestCase` 繼承、裸 `except:` 與 `@require` 契約），確保測試彈性與生產執行期嚴格隔離。 |

### 1.3 非功能需求 (Non-Functional Requirements)

| 需求編號 | 類別 | 指標與量化約束 |
| :--- | :--- | :--- |
| **NFR-01** | 效能 / 單次遍歷 | 每個非 `tests/` `.py` 檔案於 `_check_source_files` 中僅解析 AST 1 次（複用 `_get_parsed_py` 快取）並以單一 `_SourceGuardrailVisitor` 遍歷 1 次；全倉 `dev check --all`（9 大模組）總耗時 $< 2.0\text{ s}$。 |
| **NFR-02** | 依賴與純靜態安全 | 100% 使用 Python 標準庫 `ast` 模組；執行 `dev check` 期間零動態 `importlib.import_module` / `exec` 外部模組代碼。 |

### 1.4 知識庫與踩坑紀錄查閱 (Known Gotchas & CAUTIONs)

- **`[!NOTE]`** 遵循 `CodeQualityStandards.md` `S6` 免拆守門 ②：`checker.py` 為針對同一 `CheckReport` 累加器依序執行的同質性線性規則管線，`_SourceGuardrailVisitor` 與 `Checker` 維持高內聚單檔結構，不拆散為零碎檔案；且生產代碼註解嚴禁寫入任何工單或規格編號（如 `FR-01`、`DR-01`）。

---

## 2. 架構設計與異動檔案清單 (P02)

### 2.1 模組架構與核心資料流 (Architecture & Data Flow)

```text
Checker.check_module(name)
  ├── Step 1: _check_manifest          (manifest.json & __version__ alignment)
  ├── Step 2: _check_core_injection    (contributes/*.json schema & locales alignment)
  ├── Step 3: _check_file_structure    (scripts/cli.py AST, configurable/, _manifest.md)
  ├── Step 4: _check_source_files      (Single-Pass _SourceGuardrailVisitor per .py file)
  │     ├── Alias & Import Table       (import X as Y / from X import Y)
  │     ├── Legacy Zero Probing & Bare Except
  │     └── 13 Runtime Guardrails      (A1~A2, B3~B6, C7~C9, D10~D11, E12, F13 + Reflection Defense)
  ├── Step 5: _check_test_classes      (tests/test_*.py YSCBTestCase & @require)
  ├── Step 6: _check_sandbox_hooks     (scripts/hook.*.py top-level immutability & signature)
  └── Step 7: _check_docs_pollution    (docs/*.md hardcoded path check)
  (Step 8 _check_custom_rules REMOVED -> 100% Pure Static Pipeline)
```

### 2.2 受影響與新建檔案清單 (Impacted & New Files Inventory)

| 檔案路徑 | 類型 | 職責與變更說明 |
| :--- | :---: | :--- |
| `ys_codebase/source/dev/contributes/_format.json` | Delete | 物理刪除無外部消費之動態 `custom_checks` Schema 宣告檔 |
| `ys_codebase/source/dev/contributes/_manifest.md` | Modify | 移除 `§2.1 custom_checks` 擴充點文檔段落，更新為內建封閉式 AST 靜態守門說明 |
| `ys_codebase/source/dev/dev/checker.py` | Modify | 移除 `_check_custom_rules`；實作單次遍歷 `_SourceGuardrailVisitor`（涵蓋 `A1`~`F13`、別名追蹤、反射規避攔截、裸 `except:` 與 `Zero Probing`）；擴展 `_check_sandbox_hooks` 至 `scripts/hook.*.py` |
| `ys_codebase/source/dev/dev/testing/runner.py` | Modify | 將測試模組重載清理之 `getattr(sys, "modules")` 還原為直觀的 `sys.modules`，並納入 `D10` 精確座標豁免 |
| `ys_codebase/source/dev/dev/testing/sandbox.py` | Modify | 將 `SandboxProvisioner._ACTIVE_SANDBOXES` 與 `_ADAPTED_SPECS` 遷移至 `_SandboxStateMeta` 屬性（由 `RuntimeContext` 託管），消除類別可變屬性 |
| `ys_codebase/source/dev/dev/scaffold.py` | Modify | 將 `Scaffolder` 生成之 `scripts/cli.py` 骨架模板由 `print()` 升級為 `core.log.log()`，使新建模組天然符合 `A1` 靜態守門 |
| `ys_codebase/source/core/core/commands/dispatcher.py` | Modify | 將 `_set_auto_spawn_warned` 對 `globals()` 舊鍵清理改為 `globals().pop(..., None)` |
| `ys_codebase/source/core/core/platform/process.py` | Modify | 將 `_set_can_spawn_cache` 對 `globals()` 舊鍵清理改為 `globals().pop(..., None)` |
| `ys_codebase/source/knowledge-db/scripts/hook.core.py` | Modify | 移除 `on_file_space_changed` 內殘留之 `globals()["get_engine"] = ...` 動態寫入，確保符合 `C8` 規範並維持單元測試 monkeypatch 相容性 |
| `ys_codebase/source/dev/tests/test_checker.py` | Modify | 移除或更新舊 `custom_checks` 測試，新增 `A1`~`F13`、別名匯入、反射規避與 `hook.*.py` 正負向單元測試 |
| `docs/dev/architecture.md` | Modify | 同步更新 `Checker` 7 步純靜態管線與 13 項 AST 靜態守門規則架構說明 |
| `docs/dev/README.md` | Modify | 同步更新 `dev check` 靜態守門能力概覽 |

### 2.3 架構決策記錄 (Architecture Decision Records)

- **[P02:DR-01] 單一 `_SourceGuardrailVisitor` 狀態機與精確 `(module_name, rel_path)` 白名單表**：
  - 於 `_SourceGuardrailVisitor` 維護輕量級上下文堆疊（`_scope_stack` 區分 `"module"` / `"class"` / `"enum"` / `"func"`，以及 `_with_call_ids`），在單次 AST 遍歷中同時完成所有頂層/類別/函式級別檢查，並透過不可變常數字典集中管理底層模組（如 `core/core/log.py`、`core/core/context.py`、`core/core/loader.py`、`server/server/worker.py`、`server/server/master.py`）之精確路徑豁免。

---

## 3. 介面契約與 API 簽名 (P03)

### 3.1 介面契約與核心簽名 (Interface Inventory & Method Signatures)

```python
class _SourceGuardrailVisitor(ast.NodeVisitor):
    def __init__(
        self,
        module_name: str,
        rel_path: str,
        is_test_file: bool,
        report: CheckReport,
    ) -> None: ...

    def analyze(self, tree: ast.Module) -> None: ...

class Checker:
    def check_module(self, name: str) -> CheckReport: ...
    def _check_source_files(self, name: str, real_dir: str, report: CheckReport) -> None: ...
    def _check_sandbox_hooks(self, name: str, real_dir: str, report: CheckReport) -> None: ...
```

- **錯誤與例外契約 (Error & Exception Contracts)**：
  - 所有 `A1`~`F13` 規則違規、硬編碼禁止路徑與 Hook 頂層非法語句皆產生 `CheckIssue(severity=CheckSeverity.FAIL, category="ANTIPATTERN" | "SECURITY" | "ISOLATION" | "STRUCTURE", message=..., file_path=rel_p, line_number=lineno)`，使 `report.passed` 為 `False`。
  - 裸 `except:` 維持 `CheckIssue(severity=CheckSeverity.WARN, category="ANTIPATTERN", ...)` 向後相容。
- **階段決策紀錄**：`[P03:DR-01]` 維持 `Checker.check_module(name: str) -> CheckReport` 與 `Checker.check_all() -> Dict[str, CheckReport]` 公開簽名 100% 不變，確保 CLI 與測試呼叫端零破壞。

---

## 4. 定稿審查與文檔衝擊規劃 (P04)

### 4.1 交叉驗證與靈魂拷問 (Cross-Validation & Resilience Review)

- [x] **需求對齊**：FR-01 ~ FR-05 皆已於介面簽名與實作中完整對齊
- [x] **邊界防護**：EC-01 ~ EC-04 皆有具體錯誤攔截與降級策略
- [x] **依賴純淨**：100% 符合 NFR 指標約束
- **靈魂拷問與防護解法**：
  - *問：如何確保 `C8` 頂層不可變檢查不會誤殺模組頂層合法的 `Final` 常數、`Lock()`、`re.compile()`、`ContextVar()` 或數值運算式（如 `MAX_BYTES = 2 * 1024 * 1024`）？*
  - *答*：`C8` 採用明確的「禁止可變構造與禁止 `= None` 單例槽位」雙向精準判定：若賦值右側為 `None`（且非型別別名）、`List`/`Dict`/`Set` 字面量、推導式（`ListComp`/`DictComp`/`SetComp`）或可變容器建構呼叫（`list`/`dict`/`set`/`bytearray`/`defaultdict`/`deque`/`Counter`/`SimpleNamespace`）則判定違規；同時禁止頂層 `AugAssign` 與 `global` / 函式內 `globals()` 寫入，對常數算術運算式、`frozenset`、`tuple`、`Lock`、`ContextVar` 等完全零誤殺。

### 4.2 知識庫文檔衝擊與交付規劃 (Documentation Impact Plan)

| 維度 | 文件路徑 | 變更類型 | 交付內容與重點 |
| :--- | :--- | :---: | :--- |
| **模組手冊** | `docs/dev/README.md` | Modify | 更新 `dev check` 封閉式靜態檢查管線概覽 |
| **專題手冊** | `docs/dev/architecture.md` | Modify | 更新 `Checker` 7 步純靜態管線與 13 項 AST 靜態守門規則說明，移除 `custom_checks` |
| **設計決策** | `docs/dev/DESIGN_NOTES.md` | N/A | 既有設計筆記無衝突 |
| **微觀註解** | 源碼檔案 Docstrings | Modify | 同步更新 `checker.py` 類別與方法 Docstring（零工單編號噪音） |
| **發布日誌** | `CHANGELOG.md` | Modify | 於 P07 結案時記錄本子計畫變更摘要 |

- **決策定稿**：**[P04:DR-01]** 確認 `sub_05` 跨模組影響面已完全收斂，進入 Pre-Code Analyze Gate 與代碼實作。

---

## 5. 實作任務清單與偏差紀錄 (P05)

### 5.1 實作任務清單 (Task Breakdown)

- [x] **TASK-01**：刪除 `ys_codebase/source/dev/contributes/_format.json`，清理 `dev/contributes/_manifest.md`、`knowledge-db/scripts/hook.core.py`、`dev/dev/testing/runner.py`、`dev/dev/testing/sandbox.py`、`dev/dev/scaffold.py`、`core/core/commands/dispatcher.py` 與 `core/core/platform/process.py`
- [x] **TASK-02**：於 `ys_codebase/source/dev/dev/checker.py` 移除 `_check_custom_rules`，實作單次遍歷 `_SourceGuardrailVisitor`（`A1`~`F13` + 別名/反射防規避）並升級 `_check_sandbox_hooks` 支援 `scripts/hook.*.py`
- [x] **TASK-03**：於 `ys_codebase/source/dev/tests/test_checker.py` 補齊 `A1`~`F13`、別名與反射規避、`hook.*.py` 正負向測試，執行靶向測試與全倉 `dev check --all` 驗收
- [x] **TASK-DOC**：同步更新 `docs/dev/architecture.md`、`docs/dev/README.md` 與微觀代碼 Docstrings

### 5.2 實作偏差紀錄表 (Implementation Deviations)

| 任務編號 | 偏差等級 | 偏離描述與決策理由 | 處置方式 / 記錄 |
| :--- | :---: | :--- | :--- |
| - | - | 無偏差 | - |
