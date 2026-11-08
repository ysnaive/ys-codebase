# 測試計畫與驗證報告 (Test Plan & Verification)

> 功能名稱：AST 四大不可變內核原子結構、平權交換律提取器與 core.space 規則範圍綁定  
> 建立日期：2026-11-08  
> 所屬主計畫：2026_11_07_1548_ast_architecture_research  
> 狀態：Passed  
> 模型：Gemini 4 Argon (Low)  

> 模板版本：v1.4  

---

## 1. 自動化測試案例清單 (Automated Test Cases)

| 測試編號 | 測試類型 | 驗證目標與斷言 | 對應需求 | 執行指令 / 測試方法 |
| :--- | :--- | :--- | :--- | :--- |
| **FT-01** | 單元測試 | 驗證 `Span`, `ProvenanceStep`, `SymbolNode`, `RelationEdge`, `FileSymbolGraph` 之 `@dataclass(frozen=True)` 不可變性、`hash()` 可計算性、`compute_canonical_id`（解耦 `space` 與行號，並支援同名多載參數後綴）、`to_dict()` / `from_dict()` 雙向無損序列化、無效欄位拋出 `SchemaValidationError`，以及 `ast_engine.__all__` 62 個公開符號延遲載入 | FR-01, EC-01, EC-03, NFR-01 | `python yscb.py dev test --target=ast:TestASTEngineCore.test_atomic_kernel_schema_immutability_serialization_and_canonical_id && python yscb.py dev test --target=ast:TestASTEngineCore.test_ast_engine_all_56_public_symbols_lazy_loading` |
| **FT-02** | 單元測試 | 驗證 `TreeSitterDriver` 官方 `tags.scm` 與擴充標籤捕獲、多 `.scm` 以 `@name` 物理座標為錨點的交換律聯集（$A \cup B = B \cup A$）、超過 2 層深層巢狀類別/方法遞迴 `SymbolNode.children`（`OuterService -> InnerHandler -> execute_task`）、`SymbolProcessor` 管線精煉、`LanguageConfig` 之 `query_files`/`spaces`/`processors` 解析，以及 `core.space` 規則範圍過濾（`spaces: ["core/contributes"]` 匹配與攔截） | FR-02, FR-03, FR-04, FR-05, EC-02, EC-04 | `python yscb.py dev test --target=ast:TestDialectsAndParsers.test_commutative_multi_scm_merge_recursive_hierarchy_and_space_scoping` |
| **FT-03** | 靜態與回歸測試 | 執行 `dev check ast` 13 大靜態 AST 護欄檢查與 `ast` 全量測試集回歸（40 個測試案例），驗證單次解析與既有 `UnifiedSymbol` / `SemanticBundler` / `ASTEngine` 100% 向後相容 | NFR-01, NFR-02 | `python yscb.py dev check ast && python yscb.py dev test ast -q` |

---

## 2. 測試執行紀錄表 (Test Execution Log)

| 測試編號 | 執行狀態 | 實機測試日誌摘要 / 失敗根因 | 驗證時間 |
| :--- | :---: | :--- | :---: |
| **FT-01** | `Passed` | `Summary: 1 Total, 1 Passed, 0 Failed (0.146s)` & `Summary: 1 Total, 1 Passed, 0 Failed (0.152s)` — 四大原子結構不可變性、Hash、穩定 ID 與正負向序列化全數通過 | 2026-11-08 |
| **FT-02** | `Passed` | `Summary: 1 Total, 1 Passed, 0 Failed (0.191s)` — 多 `.scm` 交換律聯集（`roots_ab == roots_ba`）、3 層巢狀結構、局部關係邊、`SymbolProcessor` 與 `core.space` 範圍綁定全數通過 | 2026-11-08 |
| **FT-03** | `Passed` | `dev check ast: PASSED (0 Warnings, 0 Failed)`；`dev test ast -q: Pass: 40(100.0%), Fail: 0, Skip: 0` | 2026-11-08 |

---

## 3. 人工 / UX 驗證 Checkpoint (UX Verification Matrix)

> 驗證結果強制二元標定：`[測試通過]`（開發者實機驗收無誤）或 `[跳過/免測]`（開發者指示免測/暫緩）。嚴禁未測標記為已測！

| 驗證編號 | 驗證操作與預期效果 | 驗證結果標記 | 開發者確認紀錄 / 備註 |
| :--- | :--- | :---: | :--- |
| **UX-01** | 檢視 `sub_01` 實作之四大不可變原子結構（`Span`, `ProvenanceStep`, `SymbolNode`, `RelationEdge`）、`FileSymbolGraph`、平權交換律提取器與 `core.space` 規則範圍綁定測試報告，確認符合 `R01` 設計預期 | `[跳過/免測]` | 開發者指示免測，進入 P07 結案 |
