# 自動連續推進綜合規格與實作紀錄 (Consolidated Auto Plan & Task Log)

> 功能名稱：sub_04_dev 確定性代碼優化、實作邏輯/併發問題修復與測試套件純化  
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
| **FR-01** | `dev.testing` 沙盒、探索器、`@require` 與子行程樹生命週期修復 (`OPT-01~04, 11~13`) | 保留 `core`/`dev.testing` 模組快取、方法級 `@require` 覆蓋、`setUp` 異常回滾、子行程樹 `finally` 清理、鎖外清理沙盒與 `filter_suite` `target='mod:'` 過濾修復。 | P0 | [P00:DR-01] |
| **FR-02** | `Checker` 語法快取分離、Manifest 複用與決定性走訪 (`OPT-05~07`) | 分離 `_parsed_py_cache` 與 `_syntax_reported_files`、`_check_manifest` 回傳 `m_data`、`os.walk` 原地修剪快取目錄並排序。 | P0 | [P00:DR-01] |
| **FR-03** | `Builder`、`Releaser`、`Tester` 與 `scripts/cli.py` 確定性收斂 (`OPT-08~10, 14~15`) | 提取共用 `compare_semver_safe`、暫存 zip 加入 PID 與隨機後綴、`index.json` 原子寫入、依賴去重、`_run_single_module_worker` 顯式傳入 `target_modules` 與 CLI 零頂層常數賦值。 | P0 | [P00:DR-02] |
| **FR-04** | `tests/test_*.py` 測試套件純化與 115 項測試全覆蓋 (`AUD-01~17`) | 消除恆真測試與 91 個工單編號 token，重構 `release_git` 三階段測試並補齊 `cli.py` 全指令與 PEP 562 測試。 | P0 | [P00:DR-02] |

### 1.2 邊界與異常情況 (Edge Cases & Failure Modes)

| 邊界編號 | 情境說明 | 預期防禦與處理行為 |
| :--- | :--- | :--- |
| **EC-01** | `<pkg>/__init__.py` 存在語法錯誤且於 Step 1 被跳過 | 分離 `_parsed_py_cache` 與 `_syntax_reported_files`，確保後續步驟必定通報 `SYNTAX` 錯誤且不重複通報。 |
| **EC-02** | `YSCBTestCase.setUp` 中途發生異常或測試子行程逾時 | `setUp` 捕獲 `BaseException` 回滾環境並清理獨立沙盒；`run_subprocess_with_tree_timeout` 於 `finally` 終止子行程樹並關閉串流。 |

### 1.3 非功能需求 (Non-Functional Requirements)

| 需求編號 | 類別 | 指標與量化約束 |
| :--- | :--- | :--- |
| **NFR-01** | 靜態規範與向後相容 | `Checker().check_module('dev')` 達成 `0 FAIL, 0 WARN`，腳本頂層 `0 ast.Assign`，公開 SDK/CLI 100% 向後相容。 |
| **NFR-02** | 測試純淨度與資源零洩漏 | 115 項測試（Contract 3 + Custom 112）於 `python3 -W error::ResourceWarning` 下 100% 通過（`0 ResourceWarning`）。 |

### 1.4 知識庫與踩坑紀錄查閱 (Known Gotchas & CAUTIONs)

- **`[!CAUTION]` 公開契約相容與鎖可重入性**：所有內部鎖升級與快取深拷貝均須維持公開方法簽名與單元測試 Mock 攔截點 100% 相容。

---

## 2. 架構設計與異動檔案清單 (P02)

### 2.1 模組架構與核心資料流 (Architecture & Data Flow)

維持 `dev` 現有公開模組拓撲，透過內部純函式提煉、可重入鎖保護、原子寫入回滾與測試沙盒隔離消除競態與結構膨脹。

### 2.2 受影響與新建檔案清單 (Impacted & New Files Inventory)

| 檔案路徑 | 類型 | 職責與變更說明 |
| :--- | :---: | :--- |
| `ys_codebase/source/dev/dev/__init__.py` | Modify | 落實 `OPT-14`（`__dir__()` 集合聯集去重） |
| `ys_codebase/source/dev/dev/builder.py` | Modify | 落實 `OPT-08`（共用 `compare_semver_safe`、PID 隨機暫存 zip） |
| `ys_codebase/source/dev/dev/checker.py` | Modify | 落實 `OPT-05 ~ OPT-07`（語法錯誤快取分離、決定性目錄走訪） |
| `ys_codebase/source/dev/dev/releaser.py` | Modify | 落實 `OPT-08, OPT-09`（`index.json` 原子寫入與依賴去重） |
| `ys_codebase/source/dev/dev/tester.py` | Modify | 落實 `OPT-10`（顯式 `target_modules` 與 `report_data` 提取） |
| `ys_codebase/source/dev/dev/testing/case.py` | Modify | 落實 `OPT-02, OPT-03, OPT-12`（`@require` 對齊與 `setUp` 異常回滾） |
| `ys_codebase/source/dev/dev/testing/contract.py` | Modify | 落實 `OPT-13`（PascalCase 合約測試類別命名） |
| `ys_codebase/source/dev/dev/testing/requirement.py` | Modify | 落實 `OPT-02`（方法級與類別級裝飾器位元遮罩合併） |
| `ys_codebase/source/dev/dev/testing/runner.py` | Modify | 落實 `OPT-01, OPT-02, OPT-04, OPT-13`（保留核心模組快取與子行程樹 `finally` 清理） |
| `ys_codebase/source/dev/dev/testing/sandbox.py` | Modify | 落實 `OPT-11`（鎖外清理過期沙盒與 POSIX `file:///` URI 修正） |
| `ys_codebase/source/dev/scripts/cli.py` | Modify | 落實 `OPT-15`（雙向別名映射函數化與頂層 `0 ast.Assign`） |
| `ys_codebase/source/dev/tests/test_builder.py` | Modify | 落實 `AUD-05, AUD-06, AUD-09`（CRLF、`.yscbignore` 與 `cli.build` 驗證） |
| `ys_codebase/source/dev/tests/test_case.py` | Modify | 落實 `AUD-03, AUD-05, AUD-11, AUD-12`（獨立沙盒清理与斷言輔助驗證） |
| `ys_codebase/source/dev/tests/test_checker.py` | Modify | 落實 `AUD-04, AUD-05, AUD-06, AUD-17`（`_make_mod` 封裝與全模式檢核驗證） |
| `ys_codebase/source/dev/tests/test_release_pipeline.py` | Modify | 落實 `AUD-01, AUD-04, AUD-05, AUD-06, AUD-16`（三階段 `release_git` 與雙軌索引修補驗證） |
| `ys_codebase/source/dev/tests/test_sandbox.py` | Modify | 落實 `AUD-02, AUD-05, AUD-14`（移除標準庫恆真測試、補齊 URI 與回滾驗證） |
| `ys_codebase/source/dev/tests/test_scaffold.py` | Modify | 落實 `AUD-05, AUD-06, AUD-08`（非法模組名攔截與 `cli.create` 驗證） |
| `ys_codebase/source/dev/tests/test_tester.py` | Modify | 落實 `AUD-05, AUD-06, AUD-07, AUD-10, AUD-13, AUD-15`（PEP 562、子行程逾時與平行測試驗證） |

### 2.3 架構決策記錄 (Architecture Decision Records)

- **[P02:DR-01] 受控 CoW 雲端同步與零工單殘留**：全部 18 個修改檔案皆以受控 CoW（舊檔移入 `repo/.trash/` 後上傳原格式新檔）同步至 Google Drive，且源碼與測試內達成 0 工單編號殘留。

---

## 3. 介面契約與 API 簽名 (P03)

### 3.1 介面契約與核心簽名 (Interface Inventory & Method Signatures)

維持 `dev` 對外公開 SDK 與 `scripts/cli.py` 所有子指令、選項及回傳碼契約 100% 向後相容（`Mode B`），內部私有輔助函式採單一正統入口（`Mode A`）。

---

## 4. 定稿審查與文檔衝擊規劃 (P04)

### 4.1 交叉驗證與靈魂拷問 (Cross-Validation & Resilience Review)

- [x] 已通過 Step 2 魔鬼代言人（Devil's Advocate B1/B2）反向查驗、Step 4 盲測驗收（Subagent D `PASS`）與 Step 5 零錨定二次審計（Subagent E `P0=0, P1=0, P2=0` 融斷通過）。

### 4.2 知識庫文檔衝擊與交付規劃 (Documentation Impact Plan)

| 維度 | 文件路徑 | 變更類型 | 交付內容與重點 |
| :--- | :--- | :---: | :--- |
| **宏觀 (Macro)** | `CHANGELOG.md` | Modify | 於專案根目錄 `CHANGELOG.md` 登記 `sub_04_dev` 優化與修復摘要 |
| **中觀 (Meso)** | `docs/dev/README.md` | 免更 | 屬內部確定性重構與併發/邊界防禦強化，無公開架構或 CLI 語法變更 |
| **微觀 (Micro)** | `ys_codebase/source/dev/` | Modify | 清理工單編號註解並同步維護公開與內部輔助函式 Docstring |

---

## 5. 實作任務清單與偏差紀錄 (P05)

### 5.1 實作任務清單 (Task Breakdown)

- [x] **TASK-01**：完成 Loop 1 Step 1~2 盲測子代理 A1/A2 初審與 B1/B2 反向驗證（定案 `OPT-01 ~ OPT-15` 與 `AUD-01 ~ AUD-17`）
- [x] **TASK-02**：完成 Loop 1 Step 3 子代理 C1/C2 沙盒實作、測試純化與雲端受控 CoW 同步（共 18 檔）
- [x] **TASK-03**：完成 Loop 1 Step 4 盲測子代理 D 驗收（`PASS`）與 Step 5 盲測子代理 E 零錨定融斷判定（`P0=0, P1=0, P2=0`）
- [x] **TASK-04**：完成 Phase 07 SOP Review Gate 冷眼靜態審查、三層文檔對齊與 `P07_walkthrough.md` 結案

### 5.2 實作偏差紀錄表 (Implementation Deviations)

| 任務編號 | 偏差等級 | 偏離描述與決策理由 | 處置方式 / 記錄 |
| :---: | :---: | :--- | :--- |
| - | - | 無偏差 | - |
