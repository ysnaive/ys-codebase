# 自動連續推進綜合規格與實作紀錄 (Consolidated Auto Plan & Task Log)

> 功能名稱：sub_07_ast 確定性代碼優化、實作邏輯/併發問題修復與測試套件純化  
> 建立日期：2026-11-06  
> 所屬主計畫：2026_11_06_0110_codebase_deterministic_optimization_umbrella  
> 狀態：Completed  
> 模型：Gemini 3.1 Pro  
> 依據 P00：[P00_discuss.md](./P00_discuss.md)  
> 模板版本：v1.0  

---

## 1. 需求規格與邊界契約 (P01)

### 1.1 功能需求清單 (Functional Requirements)

| 需求編號 | 需求名稱 | 詳細規格與驗收條件 (Acceptance Criteria) | 優先級 | 對應 P00 語意 |
| :--- | :--- | :--- | :---: | :--- |
| **FR-01** | `ASTEngine` 與 `GrammarProvisioner` 跨進程/執行緒鎖、Lazy 圖譜自癒與警告收集 (`OPT-01~03`) | 修正 `_provision_lock` `timeout=60.0` 簽名、`outline()` 命中 `_FAILED_PACKAGES` 補發警告、`ASTEngine` 查詢加 `self._lock` 與 `ensure_jit_synced` 保持 Lazy Graph Loading。 | P0 | [P00:DR-01] |
| **FR-02** | `ASTBundler` 重載子符號 `parent_id` 同步、`ASTSnapshot` 反向索引與 `TreeSitterDriver` 快取 (`OPT-04~06`) | `ensure_unique_overload_ids` 納入 `scope_path` 並更新子符號 `parent_id`、`partial_files` 反向索引與首行切片解碼。 | P0 | [P00:DR-01] |
| **FR-03** | `SymbolLinker`、`OverloadResolver` 與各語系 Dialect/Parser 精準解析 (`OPT-07~13`) | 括號深度感知與泛型逗號分割、`self: Self` 剔除、0 參數重載消歧、Python 多行簽名與 `super().method()`、Markdown 代碼塊隔離、CSS/HTML 行內尾隨註解保留與 C++ `ClassName<T>::method` 解析。 | P0 | [P00:DR-01] |
| **FR-04** | `ASTResultFormatter`、`scripts/cli.py`、`hook.file-space.py`、`1.0.1.x.py` 與雙模態測試套件 (`OPT-14~18, AUD-01~18`) | `outline` 錯誤返回碼 `1`、`impact` `detail_mode`/`limit_mode`、腳本頂層 `0 ast.Assign`、`ASTTestCase` 7 項全域狀態還原與 33/33 測試 0 `ResourceWarning`。 | P0 | [P00:DR-02] |

### 1.2 邊界與異常情況 (Edge Cases & Failure Modes)

| 邊界編號 | 情境說明 | 預期防禦與處理行為 |
| :--- | :--- | :--- |
| **EC-01** | `ensure_jit_synced()` 驗證圖譜快取但呼叫端僅查詢 `outline()` 或 `search_symbols()` | 僅檢查 `graph_index_path.exists() and stat().st_size > 0` 與 `_ensure_symbols_loaded()`，不提前載入 `_graph`，維持 Lazy Graph Loading 契約。 |
| **EC-02** | CSS 或 HTML 定義行尾附帶行內區塊註解（如 `.btn { /* note */` 或 `<h1>Title</h1> <!-- note -->`） | 先剝除行內已閉合之 `/* ... */` 或 `<!-- ... -->` 後再執行規則提取，避免整行被 `continue` 跳過。 |

### 1.3 非功能需求 (Non-Functional Requirements)

| 需求編號 | 類別 | 指標與量化約束 |
| :--- | :--- | :--- |
| **NFR-01** | 靜態規範與向後相容 | `Checker().check_module('ast')` 達成 `0 FAIL, 0 WARN`，4 支腳本頂層 `0 ast.Assign`，公開 SDK/CLI 100% 向後相容。 |
| **NFR-02** | 雙模態測試純淨度與執行效能 | 33 項單元測試於 `python3 -W error::ResourceWarning` 下 100% 通過（耗時 `0.22s`，`0 ResourceWarning`）。 |

### 1.4 知識庫與踩坑紀錄查閱 (Known Gotchas & CAUTIONs)

- **`[!CAUTION]` 公開契約相容與鎖可重入性**：所有內部鎖升級與快取深拷貝均須維持公開方法簽名與單元測試 Mock 攔截點 100% 相容。

---

## 2. 架構設計與異動檔案清單 (P02)

### 2.1 模組架構與核心資料流 (Architecture & Data Flow)

維持 `ast` 現有公開模組拓撲，透過內部純函式提煉、可重入鎖保護、原子寫入回滾與測試沙盒隔離消除競態與結構膨脹。

### 2.2 受影響與新建檔案清單 (Impacted & New Files Inventory)

| 檔案路徑 | 類型 | 職責與變更說明 |
| :--- | :---: | :--- |
| `ys_codebase/source/ast/ast_engine/__init__.py` & `schema.py` | Modify | 落實 `OPT-05, OPT-14, OPT-18`（`partial_files` 反向索引、`OutlineResult.error` 與 `from_dict` 空值防禦） |
| `ys_codebase/source/ast/ast_engine/bundler.py` & `io_utils.py` | Modify | 落實 `OPT-04, OPT-05, OPT-17`（重載子符號 `parent_id` 同步與 `compute_project_relpath`） |
| `ys_codebase/source/ast/ast_engine/engine.py` & `provisioner.py` | Modify | 落實 `OPT-01 ~ OPT-03, OPT-05`（執行緒鎖、`InterProcessLock` 簽名與 Lazy Graph Loading 自癒） |
| `ys_codebase/source/ast/ast_engine/formatter.py` & `graph.py` | Modify | 落實 `OPT-14, OPT-18`（`detail_mode`/`limit_mode` 與 `SnippetExtractor` 加鎖） |
| `ys_codebase/source/ast/ast_engine/linker.py` & `resolver.py` | Modify | 落實 `OPT-07, OPT-08, OPT-18`（泛型簽名分割、0 參數消歧與 `_LAST_LINKER_CACHE` 加鎖） |
| `ys_codebase/source/ast/ast_engine/dialects/*.py` (7 檔) | Modify | 落實 `OPT-09, OPT-10, OPT-12, OPT-13`（多行簽名、C++ 模板類別解析與正則預編譯） |
| `ys_codebase/source/ast/ast_engine/parsers/*.py` (5 檔) | Modify | 落實 `OPT-01, OPT-06, OPT-09 ~ OPT-11, OPT-13`（Markdown 代碼塊隔離與 CSS/HTML 行內註解修復） |
| `ys_codebase/source/ast/scripts/cli.py`, `hook.file-space.py`, `migrations/1.0.1.x.py` | Modify | 落實 `OPT-15, OPT-16, OPT-18`（CLI 空白選項、`outline` 退出碼 `1` 與頂層 `0 ast.Assign`） |
| `ys_codebase/source/ast/tests/__init__.py` & `tests/test_*.py` (6 檔) | Modify | 落實 `AUD-01 ~ AUD-18`（雙模態確定性隔離、7 項全域狀態還原與 33 項測試） |

### 2.3 架構決策記錄 (Architecture Decision Records)

- **[P02:DR-01] 受控 CoW 雲端同步與零工單殘留**：全部 31 個修改檔案皆以受控 CoW（舊檔移入 `repo/.trash/` 後上傳原格式新檔）同步至 Google Drive，且源碼與測試內達成 0 工單編號殘留。

---

## 3. 介面契約與 API 簽名 (P03)

### 3.1 介面契約與核心簽名 (Interface Inventory & Method Signatures)

維持 `ast` 對外公開 SDK 與 `scripts/cli.py` 所有子指令、選項及回傳碼契約 100% 向後相容（`Mode B`），內部私有輔助函式採單一正統入口（`Mode A`）。

---

## 4. 定稿審查與文檔衝擊規劃 (P04)

### 4.1 交叉驗證與靈魂拷問 (Cross-Validation & Resilience Review)

- [x] 已通過 Step 2 魔鬼代言人（Devil's Advocate B1/B2）反向查驗、Step 4 盲測驗收（Subagent D `PASS`）與 Step 5 零錨定二次審計（Subagent E `P0=0, P1=0, P2=0` 融斷通過）。

### 4.2 知識庫文檔衝擊與交付規劃 (Documentation Impact Plan)

| 維度 | 文件路徑 | 變更類型 | 交付內容與重點 |
| :--- | :--- | :---: | :--- |
| **宏觀 (Macro)** | `CHANGELOG.md` | Modify | 於專案根目錄 `CHANGELOG.md` 登記 `sub_07_ast` 優化與修復摘要 |
| **中觀 (Meso)** | `docs/ast/README.md` | 免更 | 屬內部確定性重構與併發/邊界防禦強化，無公開架構或 CLI 語法變更 |
| **微觀 (Micro)** | `ys_codebase/source/ast/` | Modify | 清理工單編號註解並同步維護公開與內部輔助函式 Docstring |

---

## 5. 實作任務清單與偏差紀錄 (P05)

### 5.1 實作任務清單 (Task Breakdown)

- [x] **TASK-01**：完成 Loop 1 Step 1~2 盲測子代理 A1/A2 初審與 B1/B2 反向驗證（定案 `OPT-01 ~ OPT-18` 與 `AUD-01 ~ AUD-18`）
- [x] **TASK-02**：完成 Loop 1 Step 3 子代理 C1/C2 沙盒實作、測試純化與雲端受控 CoW 同步（共 31 檔）
- [x] **TASK-03**：完成 Loop 1 Step 4 盲測子代理 D 驗收（`PASS`）與 Step 5 盲測子代理 E 零錨定融斷判定（`P0=0, P1=0, P2=0`）
- [x] **TASK-04**：完成 Phase 07 SOP Review Gate 冷眼靜態審查、三層文檔對齊與 `P07_walkthrough.md` 結案

### 5.2 實作偏差紀錄表 (Implementation Deviations)

| 任務編號 | 偏差等級 | 偏離描述與決策理由 | 處置方式 / 記錄 |
| :---: | :---: | :--- | :--- |
| - | - | 無偏差 | - |
