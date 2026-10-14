# API 與介面規格書 (API & Interface Specification)

> 功能名稱：2026_10_14_1650_agents_workflow_audit_and_consolidation  
> 建立日期：2026-10-14  
> 所屬主計畫：N/A (獨立計畫)  
> 狀態：Confirmed  
> 模型：Gemini 3.8 Flash  

> 模板版本：v1.2  

---

## 1. 介面契約清單 (Interface Inventory)

| 介面 / 類別名稱 | 所屬檔案路徑 | 存取層級 | 核心職責 |
| :--- | :--- | :---: | :--- |
| `_resolve_uri_path` | `agents_workflow/plans/__init__.py` | Package Internal | 抽取共用之語意 URI 轉實體 `Path` 邏輯，供 verifier/scanner/archiver/searcher 統一調用 |
| `PlanVerifier` | `agents_workflow/plans/verifier.py` | Public | 檢核計畫標頭 `model` 屬性、佔位符攔截、P07 結案未勾選 Checkbox 阻斷，並限定僅檢查活躍計畫 |
| `ArtifactCompiler` | `agents_workflow/compiler.py` | Public | Token 佔位符解析引擎，精簡未使用的碎片 Token，修復雙斜線路徑疊加缺陷 |
| `header.md` & Templates | `assets/templates/` | Static Asset | 統一提供 `> 模型：[模型名稱]` 標頭與純淨無 HTML 註解之標準模板 |
| `CLI Handlers` | `scripts/cli.py` | CLI Entry | 修復 `plan_search` 之 `get_option` 為 `get_option_value`，優雅傳遞數值與字串參數 |

---

## 2. 核心 API 簽名與詳細規格 (Method Signatures & Contracts)

### 2.1 共用 URI 解析函式 (`agents_workflow.plans._resolve_uri_path`)
```python
def _resolve_uri_path(uri_str: str, default_fallback: Optional[str] = None) -> Optional[Path]:
    """
    將語意 URI 解析為 pathlib.Path 物件。
    若 uri 模組可用則透過 uri.resolve 解析；若失敗或 uri 未就緒，則回退至 default_fallback 相對於當前專案根目錄之路徑。
    """
```

### 2.2 標頭解析與佔位符正則 (`agents_workflow.plans.verifier`)
```python
# PLACEHOLDER_PATTERNS 擴充：
PLACEHOLDER_PATTERNS = [
    (r"\[功能名稱\]", "功能名稱未填寫"),
    (r"\[YYYY-MM-DD\]", "建立日期未填寫"),
    (r"\[所屬主計畫\]", "所屬主計畫未填寫"),
    (r"\[模型名稱\]", "模型名稱未填寫"),
    (r"\[Model(?:\s+Name)?\]", "模型名稱未填寫"),
    (r"\[計畫名稱\]", "計畫名稱未填寫"),
    (r"\[調研主題(?:/所屬功能)?\]", "調研主題未填寫"),
    (r"\[主題名稱\]", "主題名稱未填寫"),
]

# _verify_markdown_file 中對 Header 必填之檢核：
has_model = any(k in headers for k in ["model", "模型", "使用模型", "執行模型", "ai_model"])
if not has_model:
    report.add_issue(
        PlanIssue(
            severity=PlanSeverity.FAIL,
            category=PlanIssueCategory.HEADER,
            message="缺少必填 Header: 模型 (或 Model)",
            file_name=rel_path,
        )
    )

# _verify_markdown_file 中對 Completed 狀態下未勾選 Checkbox 之剛性檢核：
if is_p07_or_ft and status_value == "completed":
    for line_idx, line in enumerate(lines, 1):
        if re.search(r"^\s*-\s*\[\s*\]\s+", line):
            report.add_issue(
                PlanIssue(
                    severity=PlanSeverity.FAIL,
                    category=PlanIssueCategory.CONTENT,
                    message=f"已標記為 Completed，但仍有未完成之審查 Checkbox: {line.strip()}",
                    file_name=rel_path,
                    line_number=line_idx,
                )
            )
```

### 2.3 活躍計畫全量檢核邊界 (`PlanVerifier.verify_all_plans`)
```python
def verify_all_plans(self) -> Dict[str, PlanReport]:
    """
    全量檢核所有活躍計畫 (僅掃描 self.plans_dir，不掃描已歸檔之 self.archive_dir)。
    封存計畫代表不可變歷史紀錄，不應亦無必要受新版規範回溯檢查。
    """
    results: Dict[str, PlanReport] = {}
    if self.plans_dir.exists():
        for item in sorted(self.plans_dir.iterdir(), key=lambda x: x.name):
            if item.is_dir() and not item.name.startswith(".") and re.match(r"^\d{4}_\d{2}_\d{2}", item.name):
                results[item.name] = self.verify_plan(item)
    return results
```

---

## 3. 依賴拓撲與實作順序 (Implementation Topology)

```text
Step 1: 基礎設施與共用模組 (plans/__init__.py, contributes/_manifest.md, contributes/agents-workflow.json, 刪除 providers.py)
   │
   ▼
Step 2: 標頭模板與資產純淨化 (header.md, 15 個 templates, new-plan 輕量化, 刪除 review_gate.md)
   │
   ▼
Step 3: 流程規範手冊與 Skills 重構 (phase_07_walkthrough.md 內化審查, phase_06, auto, continue, pause, discuss)
   │
   ▼
Step 4: 核心驗證器與工具鏈程式碼 (verifier.py, scanner.py, archiver.py, searcher.py, compiler.py, cli.py)
   │
   ▼
Step 5: 單元測試更新與覆蓋 (test_plans_toolchain.py, test_compiler.py)
   │
   ▼
Step 6: 編譯發布與全生態系驗證 (compile, dev check --all, dev test --all)
```

