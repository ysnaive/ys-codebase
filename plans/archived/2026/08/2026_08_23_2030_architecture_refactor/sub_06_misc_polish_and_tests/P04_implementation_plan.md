# 實作計畫書 (Implementation Plan)

> 功能名稱：核心模組雜項功能完善與 Core/Dev 標準測試套件建立 (Core Misc Polish & Core/Dev Standard Tests)  
> 建立日期：2026-08-24  
> 所屬主計畫：[2026_08_23_2030_architecture_refactor](../umbrella_overview.md)  
> 依據 P01 / P02 / P03：[P01_requirements_spec.md](./P01_requirements_spec.md) / [P02_architecture_plan.md](./P02_architecture_plan.md) / [P03_api_spec.md](./P03_api_spec.md)  
> 狀態：Confirmed  
> 擴充項目：none  
> 模板版本：v1.4  

---

## 1. 任務拆解清單 (Task Breakdown)

| 任務編號 | 目標檔案 / 產物 | 變更類型 | 實作內容概述與驗收標準 |
| :--- | :--- | :---: | :--- |
| **TASK-01** | [`source/core/core/engine.py`](file:///h:/UseFolder/CodeRepo/ys_codebase/ys_codebase/source/core/core/engine.py) | Modify | 1. 增強 `act_download`：支援 Provider `index.json` 之 `files: [...]` 批次 HTTP 請求下載。<br/>2. 實作 `act_lock` / `act_unlock`：基於 `temp://.yscb.lock` 排他建立與 10s 逾時自癒。 |
| **TASK-02** | [`source/core/core/installer.py`](file:///h:/UseFolder/CodeRepo/ys_codebase/ys_codebase/source/core/core/installer.py) | Modify | 1. 增強 `cmd_update`：向 Provider 查詢版本清冊並依 SemVer 升級。<br/>2. 固化預設 Provider 解析階層（`CLI` ➔ `config.project.json` ➔ `yscb.config.json`）。 |
| **TASK-03** | [`source/core/core/contributes.py`](file:///h:/UseFolder/CodeRepo/ys_codebase/ys_codebase/source/core/core/contributes.py)<br/>[`source/core/contributes.format.md`](file:///h:/UseFolder/CodeRepo/ys_codebase/ys_codebase/source/core/contributes.format.md) | Modify<br/>Add | 1. 增強 `scan_and_inject`：實作 5 大來源深度多層合併。<br/>2. 交付 [`contributes.format.md`](file:///h:/UseFolder/CodeRepo/ys_codebase/ys_codebase/source/core/contributes.format.md) 核心貢獻擴充規範說明書。 |
| **TASK-04** | [`yscb.py`](file:///h:/UseFolder/CodeRepo/ys_codebase/yscb.py)<br/>[`source/core/config.project.json`](file:///h:/UseFolder/CodeRepo/ys_codebase/ys_codebase/source/core/config.project.json) | Modify<br/>Add | 1. 實作 `yscb.py self-update`：下載 ➔ `py_compile` 驗證 ➔ 原子覆蓋。<br/>2. 交付 `config.project.json` 專案層級組態標準範本。 |
| **TASK-05** | [`source/core/tests/`](file:///h:/UseFolder/CodeRepo/ys_codebase/ys_codebase/source/core/tests/) | Add | 建立 Core 官方持久化標準測試套件：<br/>• `test_uri.py` (VFS I/O & URI 協議解析)<br/>• `test_engine.py` (12 大原子操作 & 檔案鎖)<br/>• `test_installer.py` (7 大 Installer 指令)<br/>• `test_contributes.py` (5 來源聚合與注入) |
| **TASK-06** | [`source/dev/tests/`](file:///h:/UseFolder/CodeRepo/ys_codebase/ys_codebase/source/dev/tests/) | Add | 建立 Dev 官方持久化標準測試套件：<br/>• `test_scaffold.py` (模組建立與範本)<br/>• `test_checker.py` (AST 語法與 Schema)<br/>• `test_builder.py` (雙層排除與版本化輸出)<br/>• `test_tester.py` (測試探索與 CLI 派發) |
| **TASK-07** | **Stage 0 (前置物化部署)** | Build & Sync | 執行 `dev build --all` 並透過 `install <mod> --force` 部署最新產物至 `modules/` 運行端。 |
| **TASK-08** | **Stage 1 (沙盒前置試跑)** | Verify | 複製完整環境至 `./sandbox/` 執行全套測試，觀察 100% 通過後**正式完全刪除 `./sandbox/`**。 |
| **TASK-09** | **Stage 2 (正式環境全量驗收)** | Verify | 於專案正式環境執行 `python yscb.py dev test --all` 驗證 Auto-Contract (6/6) + Custom Tests (30+ Cases) 全部通過。 |

---

## 2. 📚 知識庫文檔交付預排清單 (Documentation Delivery Schedule)

> 依據三維錨點 1:1 交付原則，預先排定 Phase 7 / FT-3 結案審查時必須交付或更新的 `docs/` 文件：

| 預排文檔路徑 | 知識維度 | 預計更新/新增內容 | 對應 P03/P05/P06 驗收錨點 |
| :--- | :---: | :--- | :--- |
| `docs/Core/contributes_guide.md` | 維度 3 (中觀專題) | 5 大來源 Contributes 合併機制與宣告規範 | P03 §2.1 / P06 FT-04 |
| `docs/Core/DESIGN_NOTES.md` | 維度 5 (工程妥協) | 登記 `DN-04` 跨進程檔案鎖 10s 逾時自癒機制 | P03 §1.2 / P06 FT-03 |
| `docs/Dev/testing_matrix.md` | 維度 3 (中觀專題) | Core/Dev 官方標準測試套件架構與測試案例索引 | P03 §3 / P06 FT-06, FT-07 |

---

## 3. 實作相依順序與執行策略

```text
[TASK-01, 02, 03, 04] (Core 機制補齊與規範產物)
         │
         ▼
[TASK-05, 06] (Core & Dev 官方持久化標準測試套件撰寫)
         │
         ▼
[TASK-07] (Stage 0: dev build --all ➔ install --force 部署)
         │
         ▼
[TASK-08] (Stage 1: ./sandbox/ 隔離前置試跑 ➔ 刪除 sandbox)
         │
         ▼
[TASK-09] (Stage 2: 正式環境 dev test --all 全量回歸守門)
```
