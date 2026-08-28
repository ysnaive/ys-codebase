# API 與介面規格書 (API & Interface Specification)

> 功能名稱：Agents-Workflow Plan 核查工具鏈升級 (Plan Check & Verification Toolchain Upgrade)  
> 建立日期：2026-08-28  
> 所屬主計畫：`plans://2026_08_28_1754_module_toolchain_optimization/` (sub_04)  
> 狀態：Confirmed  
> 模板版本：v1.2  

---

## 1. 介面契約清單 (Interface Inventory)

| 介面 / 類別名稱 | 所屬檔案路徑 | 存取層級 | 核心職責 |
| :--- | :--- | :---: | :--- |
| `PlanSeverity` | `agents_workflow/plans/verifier.py` | Public | 嚴重度枚舉 (`PASS`, `WARN`, `FAIL`) |
| `PlanIssue` | `agents_workflow/plans/verifier.py` | Public | 單一診斷問題資料類別 |
| `PlanReport` | `agents_workflow/plans/verifier.py` | Public | 計畫檢核報告實體 (支援 Tuple 解包) |
| `PlanVerifier` | `agents_workflow/plans/verifier.py` | Public | 5 步檢核引擎實作 |
| `PlanArchiver` | `agents_workflow/plans/archiver.py` | Public | 計畫安全歸檔服務 (整合守門阻斷) |

---

## 2. 核心 API 簽名與詳細規格 (Method Signatures & Contracts)

```python
class PlanVerifier:
    def __init__(
        self,
        plans_dir: Optional[Union[str, Path]] = None,
        archive_dir: Optional[Union[str, Path]] = None,
        templates_dir: Optional[Union[str, Path]] = None,
    ):
        ...

    def verify_plan(self, plan_path_or_name: Union[str, Path]) -> PlanReport:
        """對指定計畫目錄執行 5 步檢核流水線，回傳結構化 PlanReport。"""
        ...

    def verify_all_plans(self, include_archived: bool = False) -> Dict[str, PlanReport]:
        """全量檢核所有活躍（及歷史）計畫。"""
        ...

    def get_resolved_template_headers(self, template_name: str) -> List[str]:
        """讀取已解析模板並提取 Markdown 章節標題清單。"""
        ...
```

---

## 3. 依賴拓撲與實作順序 (Implementation Topology)

```text
[Layer 1: Data Types]   PlanSeverity, PlanIssue, PlanReport in verifier.py
         │
         ▼
[Layer 2: Engine]       PlanVerifier (5-Stage Pipeline) in verifier.py
         │
         ▼
[Layer 3: Gate]         PlanArchiver (verify_plan integration) in archiver.py
         │
         ▼
[Layer 4: CLI & Test]   scripts/cli.py (Noise-Free formatter) & test_plans_toolchain.py
```
