# 實作計畫與文檔衝擊盤點 (Implementation Plan)

> 功能名稱：core contribute 系統優化與路徑系統打磨 (Core Contribute Optimization & URI Polish)  
> 建立日期：2026-08-26  
> 所屬主計畫：[2026_08_25_2200_agents_workflow_migration](../umbrella_overview.md)  
> 依據需求/設計：[P01_requirements_spec.md](./P01_requirements_spec.md), [P02_architecture_plan.md](./P02_architecture_plan.md), [P03_api_spec.md](./P03_api_spec.md)  
> 狀態：`Confirmed`  
> 擴充項目：none  
> 模板版本：v1.4  

---

## 1. 實作任務清單 (Task Breakdown)

- [ ] **TASK-01 (Contributes `__provider__` 自動注入與拓撲排序)**：
  - 修改 `source/core/core/contributes.py` 之 `ContributesAggregator.scan_and_inject()`。
  - 在搜集階段為 Dict 與 List[Dict] 項目自動注入 `"__provider__": donor_module_name`（非破壞性）。
  - 對接 `core.installer` 依賴解析器，按照已安裝模組之 Topological Order 有序合併。
- [ ] **TASK-02 (微內核標準 Contribute 查詢 SDK)**：
  - 在 `source/core/core/contributes.py` 實作 `get(target_module, key=None, default=None)` 與 `get_for_current_module()`。
  - 支援自動讀取快取與損毀自動重聚自愈。
- [ ] **TASK-03 (URI 系統 JIT 攔截、選單與 `--help` 清冊展開)**：
  - 修改 `source/core/core/uri.py`，定義 `UndefinedURIError` 與 `CyclicURIDependencyError`。
  - 在 `uri.resolve()` 中攔截 `!undefined`，在 TTY 互動終端彈出 `[-y <path> / -n / --help]` 選單（標明 `yscb://` 基準）。
  - 實作 `list_registered_schemes_summary()` 供 `--help` 格式化輸出已註冊 URI 清單。
- [ ] **TASK-04 (自動持久化寫回、連鎖遞迴與熱刷新)**：
  - 實作 `reconcile_undefined_uri()`：依據 `__provider__` 定位 `config.root://{__provider__}/config.project.json` 並原子寫回。
  - 支援連鎖未定義協議遞迴先補齊基礎協議，並以 `_reconciling_tokens` 阻斷自引用死鎖循環。
  - 記憶體即時刷新 URI 快取並無縫返回實體路徑。
- [ ] **TASK-05 (單元測試套件與全系統回歸驗證)**：
  - 在 `source/core/tests/test_contributes.py` 與 `test_uri.py` 實作 FT-01~FT-08 與 ET-01~ET-04 測試案例。
  - 實機執行全系統回歸測試 (`python yscb.py dev test --all`) 確保 100% Passed。

---

## 2. 跨階段對齊核對表 (Cross-Phase Traceability Checklist)

| 需求編號 | 對應 P00 決策 | 架構/API 規格 | 實作任務 | 測試案例 |
| :--- | :---: | :---: | :---: | :---: |
| **FR-01** | [P00:DR-01] | `P02:§1`, `P03:§1.2` | TASK-01 | FT-01, FT-02 |
| **FR-02** | [P00:DR-02] | `P02:§2.2`, `P03:§1.2` | TASK-01 | FT-03 |
| **FR-03** | [P00:DR-03] | `P02:§1`, `P03:§1.2` | TASK-02 | FT-04, FT-05 |
| **FR-04** | [P00:DR-04] | `P02:§2.1`, `P03:§1.1` | TASK-03 | FT-06 |
| **FR-05** | [P00:DR-04] | `P02:§2.1`, `P03:§1.1` | TASK-03 | FT-07 |
| **FR-06** | [P00:DR-04] | `P02:§2.1`, `P03:§1.1` | TASK-04 | FT-08 |
| **FR-07** | [P00:DR-04] | `P02:§2.1`, `P03:§1.1` | TASK-04 | FT-06 |
| **FR-08** | [P00:DR-04] | `P02:§2.1`, `P03:§1.1` | TASK-03 | ET-03 |
| **EC-01** | - | `P03:§1.1` | TASK-04 | ET-01 |
| **EC-02** | - | `P03:§3` | TASK-03 | ET-02 |
| **EC-03** | - | `P03:§1.1` | TASK-04 | FT-06 |
| **EC-04** | - | `P03:§3` | TASK-01 | ET-04 |

---

## 3. 專案知識庫文檔衝擊與交付預排 (Documentation Impact Plan)

| 維度 | 預排交付文件路徑 | 預定更新重點 |
| :---: | :--- | :--- |
| **維度 1** | [`docs/core/README.md`](file:///h:/UseFolder/CodeRepo/ys_codebase/docs/core/README.md) | 更新 VFS JIT 熱補齊機制與 `core.contributes` SDK 快速入門說明。 |
| **維度 3** | [`docs/core/VFS_AND_CONTRIBUTES.md`](file:///h:/UseFolder/CodeRepo/ys_codebase/docs/core/VFS_AND_CONTRIBUTES.md) | 專題手冊：詳解 JIT 熱補齊流程、連鎖拓撲遞迴解算與 Contributes 拓撲排序。 |
| **維度 5** | [`docs/core/DESIGN_NOTES.md`](file:///h:/UseFolder/CodeRepo/ys_codebase/docs/core/DESIGN_NOTES.md) | 登記 `[DN-CORE-05]`（JIT 協議熱補齊哲學）與 `[DN-CORE-06]`（`__provider__` 追溯性）。 |
| **全域日誌** | [`CHANGELOG.md`](file:///h:/UseFolder/CodeRepo/ys_codebase/CHANGELOG.md) | 追加 `sub_02` 微內核 Contributes 拓撲排序與 JIT 協議熱補齊發布摘要。 |

---

## 4. 深度靈魂拷問與極端壓力自省 (Stress Test Questions)

### 拷問 1：使用者若在非 TTY 終端（如 CI/CD 或背景腳本）執行指令遇到 `!undefined`，是否會造成程序無窮阻塞掛起？
- **防禦回答**：**絕對不會**。JIT 引擎在觸發 prompt 前，強制以 `sys.stdin.isatty()` 進行 TTY 探測；若為非 TTY 環境或 `interactive=False`，立即拋出結構化 `UndefinedURIError` 包含明確的命令修復引導，絕不調用 `input()` 造成阻塞。

### 拷問 2：若使用者在熱補齊輸入了自引用或循環語意路徑（例 `a://` 指向 `b://` 且 `b://` 指向 `a://`），是否會造成遞迴爆棧死鎖？
- **防禦回答**：**已徹底防護**。JIT 連鎖遞迴引擎內部維護執行序專屬的 `_reconciling_tokens: Set[str]` 集合。在解析每層協議前先進行集合探測，一旦發現同名 Token 再次進入遞迴鏈，立即拋出 `CyclicURIDependencyError` 阻斷，100% 保證拓撲收斂性。
