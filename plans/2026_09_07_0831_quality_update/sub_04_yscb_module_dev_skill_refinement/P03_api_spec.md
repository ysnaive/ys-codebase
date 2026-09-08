# API 與介面規格書 (API & Interface Specification)

> 功能名稱：yscb-module-dev 技能手冊全方位品質優化與能力補齊 (Skill Quality Refinement & Capability Completion)  
> 建立日期：2026-09-08  
> 所屬主計畫：2026_09_07_0831_quality_update (品質更新)  
> 狀態：Confirmed  
> 模板版本：v1.2  

---

## 1. 介面契約清單 (Interface Inventory)

| 介面 / 類別名稱 | 所屬檔案路徑 | 存取層級 | 核心職責 |
| :--- | :--- | :---: | :--- |
| `Checker._check_contributes_manifest` | `source/dev/dev/checker.py` | Internal | 剛性檢驗 `contributes/_manifest.md` 存在性，淘汰舊版 `contributes.format.md` |
| `Checker._check_sandbox_hooks` | `source/dev/dev/checker.py` | Internal | AST 靜態檢驗 `scripts/hook.dev.py` 語法、無副作用頂層語句與函式簽名 |
| `Checker._check_docs_pollution` | `source/dev/dev/checker.py` | Internal | 走訪掃描 `docs/` 下第三方手冊，攔截 `project://source/` 硬編碼路徑污染 |
| `Checker._check_test_classes` (擴充) | `source/dev/dev/checker.py` | Internal | AST 靜態檢驗測試方法體內是否呼叫 `self.mark_passed()` |
| `Checker._check_file_structure` (擴充) | `source/dev/dev/checker.py` | Internal | 強化 `configurable/` 子目錄檔案命名（`config.*.json`）與 JSON 語法檢核 |
| `yscb-module-dev` 技能手冊契約 | `source/dev/assets/skills/yscb-module-dev/` | Public Docs | 定義 Agent 與開發者開發模組之標準觸發時機、雙軌流水線與剛性導航指針 |

---

## 2. 核心 API 簽名與詳細規格 (Method Signatures & Contracts)

### 2.1 Checker 剛性檢核管線方法規格

```python
class Checker:
    def _check_contributes_manifest(self, name: str, real_dir: str, report: CheckReport) -> None:
        """
        檢核 contributes/ 導覽清冊存在性與現代化：
        1. 若 real_dir/contributes 存在且為目錄：
           - 必須存在 real_dir/contributes/_manifest.md，否則發布 CheckIssue(CheckSeverity.FAIL, "CONTRIBUTES", "Module defines contributes/ but lacks 'contributes/_manifest.md' declaration index.", file_path="contributes/_manifest.md")
        2. 若 real_dir/contributes.format.md 存在：
           - 發布 CheckIssue(CheckSeverity.WARN, "CONTRIBUTES", "Legacy 'contributes.format.md' detected. Please migrate to 'contributes/_manifest.md'.", file_path="contributes.format.md")
        """
        ...

    def _check_sandbox_hooks(self, name: str, real_dir: str, report: CheckReport) -> None:
        """
        AST 靜態檢核 scripts/hook.dev.py 規格：
        1. 若 scripts/hook.dev.py 存在：
           - ast.parse 語法驗證，若拋 SyntaxError 則發布 CheckSeverity.FAIL
           - 頂層陳述式白名單：僅允許 ast.Import, ast.ImportFrom, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef, 以及字串常數 ast.Expr (docstring)
           - 若存在頂層執行語句，發布 CheckIssue(CheckSeverity.FAIL, "ANTIPATTERN", "Forbidden executable statement outside func/class in 'scripts/hook.dev.py'.")
           - 函式簽名驗證：若宣告 on_test_setup 或 on_test_teardown，其 args 必須至少包含 1 個參數 (context)，否則發布 CheckSeverity.FAIL
        """
        ...

    def _check_docs_pollution(self, name: str, real_dir: str, report: CheckReport) -> None:
        """
        掃描 docs/ 第三方文檔路徑純淨度：
        1. 走訪 real_dir/docs 目錄下的所有 .md 檔案：
           - 讀取內容並檢查是否包含 "project://source/"
           - 若包含，發布 CheckIssue(CheckSeverity.WARN, "DOCUMENTATION", f"Documentation pollution: Hardcoded 'project://source/' detected in '{rel_path}'. Downstream developers have no source/ directory; use 'module://<mod>/' semantic URI instead.", file_path=rel_path, line_number=lineno)
        """
        ...

    def _check_test_classes(self, name: str, real_dir: str, report: CheckReport) -> None:
        """
        擴充現有 test class 檢核：
        1. 遍歷繼承自 YSCBTestCase 的 class 中的所有 FunctionDef (name.startswith("test_"))
        2. 檢查 function AST 是否包含對 self.mark_passed() 的調用 (ast.Call -> ast.Attribute(value=ast.Name(id="self"), attr="mark_passed"))
        3. 若無 mark_passed 調用且未標註 @require(Requirement.NONE)：
           - 發布 CheckIssue(CheckSeverity.WARN, "STRUCTURE", f"Test method '{fn.name}' in tests/{t_file}:{fn.lineno} lacks 'self.mark_passed()' call. Unhandled tests will be marked as UNKNOWN in test runner.", file_path=f"tests/{t_file}", line_number=fn.lineno)
        """
        ...
```

### 2.2 技能手冊「觸發時機」導航契約 (Skill Trigger Contract)

```markdown
| 觸發時機 (Trigger Condition) | 強制查閱之專題手冊 (Mandatory Reference) |
| :--- | :--- |
| **模組初始化 / 骨架建立 / 新增功能 / CLI 指令實作** | [cli_and_commands.md](./references/cli_and_commands.md) |
| **宣告或擴充 Contributes 擴充點 / Ingress Schema 制定 / 邊界隔離** | [contributes_guide.md](./references/contributes_guide.md) |
| **單元測試 / 沙盒測試 / 撰寫 YSCBTestCase / 測試分類 / 沙盒鉤子** | [testing_and_sandbox.md](./references/testing_and_sandbox.md) |
| **代碼靜態預檢 / 驗收四大 Gate / 四大文檔視角隔離 / AST 檢核紅線** | [acceptance_checklist.md](./references/acceptance_checklist.md) |
| **版本晉升 / 正式發布 (🚨 僅限開發者明確指示時)** | [cli_and_commands.md:軌道 B](./references/cli_and_commands.md#軌道-b版本晉升交付-release-track) |
```

---

## 3. 依賴拓撲與實作順序 (Implementation Topology)

```text
[Step 1: Checker 剛性守門增強] (source/dev/dev/checker.py)
       |
       v
[Step 2: Checker 單元測試覆蓋] (source/dev/tests/test_checker.py)
       |
       v
[Step 3: 驗收清單與四大視角精修] (acceptance_checklist.md)
       |
       v
[Step 4: CLI、腳手架與發布手冊精修] (cli_and_commands.md)
       |
       v
[Step 5: 測試與沙盒手冊精修] (testing_and_sandbox.md)
       |
       v
[Step 6: Contributes 邊界手冊精修] (contributes_guide.md)
       |
       v
[Step 7: SKILL.md 主入口精修] (SKILL.md)
```
