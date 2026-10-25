# API 與介面規格書 (API & Interface Specification)

> 功能名稱：新世代全量複檢收尾與發布前最終打磨 (Global Step 1~13 Pre-Release Polish)  
> 建立日期：2026-10-25  
> 所屬主計畫：N/A (Root Plan)  
> 狀態：Confirmed  
> 模型：Unknown  

> 模板版本：v1.2  

---

## 1. 介面契約清單 (Interface Inventory)

| 介面 / 類別名稱 | 所屬檔案路徑 | 存取層級 | 核心職責 |
| :--- | :--- | :---: | :--- |
| `SandboxProvisioner.prune_sandboxes` | `ys_codebase/source/dev/dev/testing/sandbox.py` | Public | 執行緒安全地清理超過 `max_keep` (預設 8) 之舊沙盒（子沙盒環境內自動跳過） |
| `PlanVerifier._is_header_match` | `ys_codebase/source/agents-workflow/agents_workflow/plans/verifier.py` | Internal | 判斷模板預期章節與文件實際章節是否匹配（防範否定詞前綴誤配） |
| `KnowledgePipeline.act_callers / act_callees / act_impact` | `ys_codebase/source/knowledge-db/knowledge_db/pipeline.py` | Public | 查詢符號調用鏈與影響半徑，完整透傳 `ftypes` 過濾條件至 `find_target_symbol` |

---

## 2. 核心 API 簽名與詳細規格 (Method Signatures & Contracts)

```python
class SandboxProvisioner:
    _SANDBOX_LOCK: threading.RLock

    @staticmethod
    def prune_sandboxes(
        max_keep: int = 8,
        sandbox_parent_dir: Optional[str] = None,
        exclude: Optional[List[str]] = None,
    ) -> int: ...

class PlanVerifier:
    @staticmethod
    def _is_header_match(exp_norm: str, doc_norm: str) -> bool: ...
```

- **錯誤與例外契約 (Error & Exception Contracts)**：
  - `SandboxProvisioner.create_sandbox()`：於 `os.environ.get("YSCB_TEST_SANDBOX") == "1"` 時不呼叫 `prune_sandboxes()`；`_project_venv()` 自動以 `os.path.realpath(host_venv_dir)` 解析真實 `.venv` 目錄。
  - `PlanVerifier._is_header_match(exp_norm, doc_norm)`：若兩字串相等回傳 `True`；若短字串為長字串子字串，但長字串在短字串出現位置之前緊鄰 `非`、`不`、`無`、`未`，則回傳 `False`。
- **階段決策紀錄**：`[P03:DR-01]` 維持所有公開 CLI 與 Python 方法簽名向下相容，僅修正預設保留數量（`max_keep: int = 8`）與補齊 `contributes/core.json` 宣告契約。

---

## 3. 依賴拓撲與實作順序 (Implementation Topology)

```text
1. TASK-01: dev (sandbox.py, tester.py) -> 修復平行沙盒互刪與巢狀 venv 投影
2. TASK-02: agents-workflow (verifier.py) -> 修復章節否定詞子字串誤判
3. TASK-03: knowledge-db (pipeline.py, config.py, contributes/core.json, test_graph_and_impact.py) -> 補齊 K-04/K-06/K-07/K-08
4. TASK-04: server (test_server.py, test_server_logging.py) -> 完成 ST-01~ST-03 測項純化
5. TASK-05: docs/ & CHANGELOG.md -> 同步更新 5 處知識庫文檔與日誌
```

