# API 與介面規格書 (API & Interface Specification)

> 功能名稱：sub_05_ecosystem_integration_and_acceptance  
> 建立日期：2026-10-24  
> 所屬主計畫：2026_10_23_1122_ecosystem_modules_hardening_and_test_purification  
> 狀態：Confirmed  
> 模型：Gemini 4 Argon (Low)  

> 模板版本：v1.2  

---

## 1. 介面契約清單 (Interface Inventory)

| 介面 / 類別名稱 | 所屬檔案路徑 | 存取層級 | 核心職責 |
| :--- | :--- | :---: | :--- |
| `ContributesManager.check_all` | `ys_codebase/source/core/core/contributes.py` | Public | 檢驗所有已安裝模組與 `config://<target>/contribute.json` 專案級覆寫之 Schema 合規性 |
| `Checker.check_all` | `ys_codebase/source/dev/dev/checker.py` | Public | 掃描 `ys_codebase/source/*` 執行模組結構與跨模組自訂規則檢驗 |
| `Tester.run_tests` | `ys_codebase/source/dev/dev/tester.py` | Public | 建立隔離沙盒並執行各模組 `tests/test_*.py`，攔截 `UNKNOWN` 與失敗案例 |
| `ServiceManager` | `ys_codebase/source/server/server/service.py` | Public | 動態載入 `server.services` 宣告之背景 Worker，透過私有 `_ipc_stdout` 與 `exit` 握手管理生命週期 |
| `KnowledgeEngine` | `ys_codebase/source/knowledge-db/knowledge_db/engine.py` | Public | 提供 `search`、`callers`、`callees`、`impact` 檢索與調用圖譜熱修補雙階保真能力 |

---

## 2. 核心 API 簽名與詳細規格 (Method Signatures & Contracts)

```python
# 1. CLI 跨模組驗證與熱派發命令契約 (CLI Verification & Hot-Dispatch Contracts)
# - python yscb.py contributes check -> exit_code: int (0 on 100% valid)
# - python yscb.py dev check --all -> exit_code: int (0 on 0 Error / 0 Warning)
# - python yscb.py dev test --all -q -> exit_code: int (0 on 100% Passed, 0 Unknown)
# - python yscb.py server start | status | stop -> exit_code: int (0)
# - python yscb.py uri resolve <uri> -> exit_code: int (0)
# - python yscb.py config get <key> -> exit_code: int (0)
# - python yscb.py knowledge-db status -> exit_code: int (0)
```

- **錯誤與例外契約 (Error & Exception Contracts)**：
  - `contributes check` 或 `dev check --all` 若發現任何契約違規，必須返回非 0 退出碼並明確列印違規欄位路徑。
  - `dev test --all -q` 若有任何測試未呼叫 `self.mark_passed()`（狀態 `UNKNOWN`）或斷言失敗，必須返回非 0 退出碼。
  - 群組節點收到未知子命令時，必須攔截並輸出標準錯誤訊息與退出碼 `1`。
- **階段決策紀錄**：`[P03:DR-01]` 本子計畫聚焦於四大模組固化後之跨模組介面聯合驗收，不新增或修改任何公開 Python API 簽名，確保 `sub_01` ~ `sub_04` 已定型之 API 契約 100% 穩定。

---

## 3. 依賴拓撲與實作順序 (Implementation Topology)

```text
Step 1: 確認四大模組 (core, dev, server, knowledge-db) @build 狀態與版本同步 (FR-04)
  │
  ▼
Step 2: 執行靜態契約與規則聯合檢驗 (contributes check & dev check --all) (FR-01)
  │
  ▼
Step 3: 執行四大模組 42 支純化測試檔與全生態系沙盒回歸測試 (dev test --all -q) (FR-02, NFR-01, NFR-02)
  │
  ▼
Step 4: 執行常駐 Server 託管 knowledge-db-watcher 與多層子命令熱派發端到端驗證 (FR-03, EC-01, EC-03)
  │
  ▼
Step 5: 核驗 8 份已消費 Roadmap 儲備閉環與三層文檔對齊 (FR-05, EC-02)
```

