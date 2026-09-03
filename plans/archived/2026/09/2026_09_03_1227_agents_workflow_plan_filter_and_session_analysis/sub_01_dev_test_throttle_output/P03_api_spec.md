# API 與介面規格書 (API & Interface Specification)

> 功能名稱：dev test 輸出格式優化與節流模式 (Throttle Output)  
> 建立日期：2026-09-03  
> 所屬主計畫：2026_09_03_1227_agents_workflow_plan_filter_and_session_analysis  
> 狀態：Confirmed  
> 模板版本：v1.2  

---

## 1. 介面契約清單 (Interface Inventory)

| 介面 / 類別名稱 | 所屬檔案路徑 | 存取層級 | 核心職責 |
| :--- | :--- | :---: | :--- |
| `ASCIIReportFormatter.format_throttled` | `source/dev/dev/testing/runner.py` | Public | 依節流規範格式化測試成果為單行統計與必要之失敗清單。 |
| `Tester._run_test` | `source/dev/dev/tester.py` | Public | 解析 CLI `-q / --quiet` 旗標，掌管外部沙盒深度靜默與節流報告輸出。 |
| `Tester._run_op_test` | `source/dev/dev/tester.py` | Internal | 解析沙盒內 `-q / --quiet` 與環境變數，掌管模組測試進度靜默與單模組節流輸出。 |

---

## 2. 核心 API 簽名與詳細規格 (Method Signatures & Contracts)

### 2.1 節流格式化器契約

```python
class ASCIIReportFormatter:
    @staticmethod
    def format_throttled(report_data: Dict[str, Any]) -> str:
        """
        將測試報告數據轉換為最大化節省 Token 的節流格式。

        Args:
            report_data: 包含 total, passed, failed, skipped, failures_list 之統計字典。

        Returns:
            str:
              - 若 failed == 0:
                "Pass: {passed}({pct:.1f}%), Fail: 0, Skip: {skipped}"
                其中 pct = (passed / total * 100.0) if total > 0 else 0.0
              - 若 failed > 0:
                "Pass: {passed}({pct:.1f}%), Fail: {failed}, Skip: {skipped}\n\nFAILED / ERROR TEST CASES LIST:\n{failure_items}"
        """
```

### 2.2 CLI 參數與環境變數穿透契約

```text
CLI 呼叫範例：
  $ python yscb.py dev test --quiet
  $ python yscb.py dev test agents-workflow -q
  $ python yscb.py dev test --all -q

環境變數穿透：
  YSCB_TEST_QUIET="1" (當 --quiet 或 -q 傳入時由 Tester 自動注入子進程)
```

---

## 3. 依賴拓撲與實作順序 (Implementation Topology)

```text
[Step 1: 格式化器擴充]
  source/dev/dev/testing/runner.py (實作 ASCIIReportFormatter.format_throttled)
         |
         v
[Step 2: CLI 參數解析與深度靜默]
  source/dev/dev/tester.py (支援 -q / --quiet，靜默 pre-build、sandbox 日誌，串接 format_throttled)
         |
         v
[Step 3: 單元測試編寫與回歸]
  source/dev/tests/test_tester_throttle.py (驗證 FT-01~05, ET-01~02)
         |
         v
[Step 4: AI 調用手冊與工作流對齊]
  source/dev/assets/skills/yscb-module-dev/SKILL.md
  source/agents-workflow/assets/workflows/Auto.md
  source/agents-workflow/assets/workflows/Review.md
  source/agents-workflow/assets/skills/development-sop/references/phase_06_test.md
  source/agents-workflow/assets/skills/development-sop/references/plan_modes.md
```
