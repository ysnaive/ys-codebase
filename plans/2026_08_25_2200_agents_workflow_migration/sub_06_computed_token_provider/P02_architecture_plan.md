# 架構與模組設計說明書 (Phase 2: Architecture Plan)

> 功能名稱：Contributes 擴充支援 Computed Token 與 code.func:// 函式定位協議  
> 建立日期：2026-08-26  
> 所屬主計畫：[2026_08_25_2200_agents_workflow_migration](../umbrella_overview.md)  
> 狀態：Confirmed  
> 模板版本：v1.2  

---

## 1. 系統架構分層與模組職責 (Architecture Layers)

```text
┌─────────────────────────────────────────────────────────────────┐
│                    contributes.json / manifest                  │
│   { "type": "computed", "value": "code.func://pkg/mod:func" }  │
└────────────────────────────────┬────────────────────────────────┘
                                 │
                                 ▼
┌─────────────────────────────────────────────────────────────────┐
│               core: SymbolResolver (symbols.py)                 │
│  - 解析 URI: code.func://<module>/<subpath>:<func_name>        │
│  - 動態尋址: 探測 package namespace / module.root:// 實體路徑    │
│  - 安全載入: importlib 加載與 sys.modules 隔離快取              │
│  - 輸出產物: Python Callable 物件                               │
└────────────────────────────────┬────────────────────────────────┘
                                 │
                                 ▼
┌─────────────────────────────────────────────────────────────────┐
│                Artifact Compiler / Resolver                     │
│  - 工廠解算: 偵測 type: "computed"                              │
│  - 注入調用: target_fn(CompilerContext) -> str                  │
│  - 渲染替換: replace / append 寫入目標 Artifact                 │
└─────────────────────────────────────────────────────────────────┘
```

---

## 2. 核心架構決策 (Design Decisions, DR)

- **[SUB06:DR-04] SymbolResolver 雙軌尋址策略**：
  1. **軌道 1 (Package Import)**：若目標模組已在 Python `sys.modules` 或為已安裝 package（如 `agents_workflow`、`core`），直接 `importlib.import_module`。
  2. **軌道 2 (VFS Spec Import)**：若未直接在 `sys.path`，透過 `uri.resolve("module.root://<mod>/...")` 或 `uri.resolve("module.source.root://<mod>/...")` 解析實體路徑，透過 `importlib.util.spec_from_file_location` 載入模組，確保 Zip 與開發源碼態皆能無縫執行。
- **[SUB06:DR-05] CompilerContext 執行期上下文注入契約**：
  提供給 Provider 函式的上下文物件具備：
  - `uri`: 全域語意 URI SDK 實例。
  - `contributes`: 完整貢獻資料集。
  - `project_config`: 當前專案組態設定。
  - `env`: 執行環境與模組名稱。

---

## 3. 受影響檔案清單 (Impacted Files Matrix)

| 檔案路徑 | 操作類型 | 職責與變更摘要 |
| :--- | :---: | :--- |
| `source/core/core/symbols.py` | `NEW` | 實作 `code.func://` 語法解析、模組尋址與 `resolve_callable`。 |
| `source/core/core/__init__.py` | `MODIFY` | 導出 `symbols` 與 `resolve_callable` 標準 API。 |
| `source/core/core/compiler.py` *(及 agents-workflow 複製品)* | `MODIFY` | 解算器支援 `type: "computed"`，即時調用 Provider 並注入 Context。 |
| `source/agents-workflow/agents_workflow/providers.py` | `NEW` | 實作 `get_dynamic_context_map(ctx)` 動態路徑地圖生成函式。 |
| `source/agents-workflow/manifest.json` | `MODIFY` | 宣告 `DYNAMIC_CONTEXT_MAP` 的 Computed Insert。 |
| `source/core/tests/test_symbols.py` | `NEW` | 符號定位協議單元測試套件（涵蓋 FR-01~02, EC-01~02）。 |
| `source/agents-workflow/tests/test_compiler.py` | `MODIFY` | 編譯器 Computed Token 注入端對端測試。 |

---

## 4. 依據需求 (Traceability)

- 本架構直接對應 [P01_requirements_spec.md](./P01_requirements_spec.md) 之 FR-01 ~ FR-05 與 EC-01 ~ EC-04。
