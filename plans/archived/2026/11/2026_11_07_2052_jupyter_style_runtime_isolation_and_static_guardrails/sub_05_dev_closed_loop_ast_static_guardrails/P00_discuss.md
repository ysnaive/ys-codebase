# 需求討論說明書 (Semantic Requirements Discovery)

> 功能名稱：sub_05_dev_closed_loop_ast_static_guardrails  
> 建立日期：2026-11-08  
> 所屬主計畫：2026_11_07_2052_jupyter_style_runtime_isolation_and_static_guardrails  
> 狀態：Confirmed  
> 模型：Unknown  

> 計畫類型：Feature  
> 模板版本：v1.2  

---

## 1. 使用者原始需求與意圖 (User Intent)

- **原始陳述**：完成 `sub_04` 結案與 commit 後，推進 Umbrella 主計畫最後一個子計畫 `sub_05_dev_closed_loop_ast_static_guardrails`，並結合舊有靜態檢查管線共同審計，從純 `core` / `dev` 基座視角補齊語法防規避檢查與 Hook 腳本檢查。
- **核心目標**：
  1. **拔除廢棄之動態 `custom_checks` 機制（100% 純靜態化）**：
     - 物理刪除無任何外部模組消費之 `ys_codebase/source/dev/contributes/_format.json`；
     - 同步清理 `ys_codebase/source/dev/contributes/_manifest.md`（移除 §2.1 `custom_checks` 段落）與 `docs/dev/architecture.md` / `docs/dev/README.md` 相關描述；
     - 從 `ys_codebase/source/dev/dev/checker.py` 移除 `_check_custom_rules` 方法與動態 `importlib` / `_resolve_callable` 載入邏輯，確保 `dev check` 成為 100% 純靜態、零動態代碼載入之安全檢查器。
  2. **重構 `Checker._check_source_files` 為封閉式單次遍歷（Single-Pass `ast.NodeVisitor`）AST 靜態守門管線（含別名與反射防規避）**：
     - 對每個非 `tests/` 生產 `.py` 檔案僅執行單次 AST 遍歷（Single-Pass `_SourceGuardrailVisitor(ast.NodeVisitor)`），內建檔案級符號別名追蹤表（追蹤 `import ... as ...` 與 `from <mod> import <symbol>`），同時整合舊有規則（`Zero Probing` 字串常數攔截與裸 `except:` 檢查）與 6 大類共 13 項強制靜態守門規則（`A1`~`F13` 違規一律判定 `CheckSeverity.FAIL`）：
       - **(A1) 禁止未受管原生輸出與 `logging`**：禁止呼叫 `print()`、`pprint.pprint()`、`sys.stdout.write/writelines`、`sys.stderr.write/writelines`、`logging.*`、`traceback.print_exc/print_exception`（豁免：`core/core/log.py` 底層串流封裝、`dev/dev/testing/runner.py` 沙盒串流攔截器 `OutputCapturer`/`SafeStreamWriter`）。
       - **(A2) 禁止阻塞式標準輸入讀取**：禁止呼叫 `input()`、`sys.stdin.read/readline/readlines`（豁免：`server/server/worker.py` JSON-RPC 控制通道讀取）。
       - **(B3) 禁止非啟動器直接終止進程**：禁止呼叫 `sys.exit()`、`os._exit()` 及 `getattr(sys, "exit")` / `getattr(os, "_exit")`（豁免：僅單檔啟動器 `yscb.py`；模組內部一律使用 `raise SystemExit(code)` 或返回狀態碼）。
       - **(B4) 禁止全域工作目錄查詢與切換**：禁止呼叫 `os.chdir()`、`os.fchdir()`、`os.getcwd()`、`Path.cwd()` 及 `getattr(os, "chdir"|"fchdir"|"getcwd")`（豁免：`core/core/context.py` 之 `get_virtual_cwd()` 兜底實作與 `core/core/platform/venv.py` 之 `restore_process_env_and_cwd` 沙盒環境還原）。
       - **(B5) 禁止執行期原地突變 `os.environ`**：禁止 `os.environ[...] = ...`、`del os.environ[...]`、`os.environ |= ...`、`os.environ.pop/clear/update/setdefault`、`os.putenv()`、`os.unsetenv()` 及 `getattr(os, "environ"|"putenv"|"unsetenv")`（豁免：`core/core/platform/venv.py` 之 `restore_process_env_and_cwd` 沙盒環境還原）。
       - **(B6) 禁止非監控進程註冊 OS Signal Handler**：禁止呼叫 `signal.signal()` 及 `getattr(signal, "signal")`（豁免：`server/server/master.py` Master 守護進程）。
       - **(C7) 禁止函式可變預設參數**：禁止 `def fn(x=[], y={}, z=set(), w=list()/dict()/bytearray()/defaultdict()/deque()/Counter()/SimpleNamespace())` 可變容器字面量、推導式或建構呼叫作為參數預設值。
       - **(C8) 禁止模組頂層可變快取/容器、`global` 關鍵字與 `globals()` 動態寫入**：禁止 `global` 敘述；禁止函式內透過 `globals()[...] = ...`、`globals().setdefault(...)`、`globals().update(...)` 動態寫入模組變數（一併清理 `knowledge-db/scripts/hook.core.py` 殘留之 `globals()["get_engine"] = ...`）；禁止模組頂層（含頂層 `if/try/with` 分支與 `AugAssign`）賦值可變容器（`list`/`dict`/`set`/`bytearray`/`defaultdict`/`deque`/`Counter`/`SimpleNamespace` 字面量、推導式或建構呼叫）與 `= None` 頂層可變單例變數（合法允許：`__all__` 匯出清單，以及 `tuple`、`frozenset`、`types.MappingProxyType`、`threading.Lock/RLock/Event/Condition/Semaphore`、`contextvars.ContextVar`、`re.compile`、`TypeVar` 等不可變或同步原語頂層常數）。
       - **(C9) 禁止非 `frozen=True` 之 `@dataclass` 與類別頂層可變屬性**：所有 `@dataclass` 裝飾器必須顯式指定 `@dataclass(frozen=True)`；非 `Enum` 類別頂層禁止直接賦值可變容器字面量、推導式或可變建構呼叫。
       - **(D10) 禁止未受管動態模組載入與 `sys.path` / `sys.modules` 直接突變**：合併舊 `_find_sys_path_mutations`，禁止非 `core` 模組直接修改 `sys.path`、禁止直接寫入/刪除 `sys.modules[...]`（含 `getattr(sys, "modules"|"path")`）或直接呼叫 `spec_from_file_location`（豁免：`core/core/loader.py`、`core/core/platform/venv.py` 與 `dev/dev/testing/runner.py` 測試隔離卸載）。
       - **(D11) 禁止動態代碼執行**：禁止呼叫 `eval()`、`exec()`、`__import__()`（含 `builtins.eval/exec/__import__` 與 `importlib.__import__`）。
       - **(E12) 禁止非原子檔案改名**：禁止呼叫 `os.rename()`、`os.renames()`、`Path.rename()`（強制使用 `os.replace()` / `Path.replace()` 或 `core.vfs`）。
       - **(F13) 禁止缺少 `timeout=` 之 `subprocess` 同步呼叫、阻塞式 `os.system`/`os.popen` 與野生 `threading.Thread`/`Timer`**：禁止 `subprocess.run/call/check_call/check_output` 未傳入 `timeout=` 關鍵字參數（豁免：`core/core/platform/process.py` 底層進程工具）；禁止呼叫 `os.system()`、`os.popen()`；禁止直接實例化 `threading.Thread(...)` 或 `threading.Timer(...)`（豁免：`server/server/service.py`、`server/server/master.py`、`dev/dev/testing/runner.py` 與 `core/core/log.py` 底層串流緩衝計時器）。
  3. **通用化 Step 6 Hook 腳本檢查（`_check_sandbox_hooks` 擴展至 `scripts/hook.*.py`）**：
     - 擴展檢查 `scripts/hook.core.py` 與 `scripts/hook.dev.py`，移除舊有 `elif isinstance(node, ast.Assign): continue` 無條件放行漏洞（頂層賦值必須為不可變常數/同步原語），並保留 Hook 函式至少接受 1 個參數（`context`）之檢查。
  4. **補齊 `dev/tests/test_checker.py` 正負向單元測試並達成全倉 9 大模組 `dev check --all` 零違規 PASS**。
- **既有組件復用與查重 (Reuse Discovery)**：
  - 直接於 `ys_codebase/source/dev/dev/checker.py` 既有 `Checker` 架構與 `_get_parsed_py` AST 快取基礎上升級 `_check_source_files` 與 `_check_sandbox_hooks`，無須拆散同質性線性檢查管線（遵循 `CodeQualityStandards.md` `S6` 免拆守門 ②）。
- **邊界排除 (Explicitly Excluded)**：
  - 各模組 `tests/` 目錄下之測試腳本豁免 A1~F13 生產執行期限制（仍維持既有 `YSCBTestCase` 繼承、裸 `except:` 與 `@require` 檢查）。
  - 靜態檢查器純粹從 `core` / `dev` 基座角度設計，不耦合特定選配模組之業務特化規則。
- **架構影響範圍**：
  - `ys_codebase/source/dev/contributes/_format.json` (Delete)
  - `ys_codebase/source/dev/contributes/_manifest.md` (Modify)
  - `ys_codebase/source/dev/dev/checker.py` (Modify)
  - `ys_codebase/source/dev/dev/testing/runner.py` (Modify — 將 `getattr(sys, "modules")` 改為顯式直觀的 `sys.modules` 並由 `D10` 精確豁免)
  - `ys_codebase/source/knowledge-db/scripts/hook.core.py` (Modify — 移除殘留之 `globals()["get_engine"] = ...` 動態寫入，改由 `RuntimeContext` 讀取测试注入覆寫或直接呼叫 `get_engine` / `get_active_worker`)
  - `ys_codebase/source/dev/tests/test_checker.py` (Modify)
  - `docs/dev/architecture.md` & `docs/dev/README.md` (Modify)

---

## 2. 核心討論與決策紀錄 (Discussion & Decisions)

- **[P00:DR-01] 物理刪除 `dev/contributes/_format.json` 與移除 `_check_custom_rules` 動態載入**：
  - `dev` 模組不再宣告 `custom_checks` 擴充點；`Checker.check_module` 由 8 步簡化為 7 步純靜態檢查管線，徹底根除 `dev check` 執行期間動態 import 外部模組造成的副作用與 `sys.path` 污染。
- **[P00:DR-02] 單次遍歷 `_SourceGuardrailVisitor(ast.NodeVisitor)`、別名/反射防規避與精準白名單豁免表**：
  - 將 A1~F13、別名追蹤（`import ... as ...` / `from ... import ...`）、反射攔截（`getattr`/`setattr`/`delattr`/`globals()[...] = ...`）、裸 `except:` 與 `Zero Probing` 字串常數檢查整合於單一 `_SourceGuardrailVisitor` 中，每檔僅遍歷 AST 一次；底層基座特權豁免以不可變 `(module_name, rel_path)` 精確座標表管理。
- **[P00:DR-03] 通用化 `scripts/hook.*.py` 靜態結構守門（純 `core`/`dev` 視角）**：
  - `_check_sandbox_hooks` 涵蓋 `scripts/hook.core.py` 與 `scripts/hook.dev.py`，移除頂層 `ast.Assign` 無條件放行漏洞（頂層賦值須符合 `C8` 不可變規範），不掺雜特定業務模組特化邏輯。
- **[P00:DR-04] 既有測試沙盒 Mock 模組模板與全倉 9 大模組 100% 合規對齊**：
  - 清理 `knowledge-db/scripts/hook.core.py` 殘留之 `globals()[...] = ...` 與 `dev/dev/testing/runner.py` 之 `getattr(sys, "modules")`，確保全倉 9 大模組與 `test_checker.py` 100% 通過新規則。

---

## 3. 開放議題與確認紀錄

- 開發者已確認最終工單並觸發 `/auto`，進入 Phase 01~06 自動連續推進。
