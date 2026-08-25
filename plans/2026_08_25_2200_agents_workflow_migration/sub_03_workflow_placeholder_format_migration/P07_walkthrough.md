# Phase 7: 成果展示與結案報告 (Walkthrough) - workflow 佔位符格式修改

> 計畫名稱：`sub_03_workflow_placeholder_format_migration`  
> 建立日期：2026-08-26  
> 所屬主計畫：[2026_08_25_2200_agents_workflow_migration](../umbrella_overview.md)  
> 依據驗證報告：[P06_test_plan.md](./P06_test_plan.md)  
> 狀態：`Completed` (Phase 7 結案完成)  
> 擴充項目：none  
> 模板版本：v1.4  

---

## 1. 變更概述 (High-Level Summary)

本子計畫完成了 `agents-workflow` 佔位符體系的全面視覺化重構：
- **痛點根除**：淘汰原 HTML 註解格式（`<!-- __TOKEN__ -->`），解決其在 Markdown 渲染模式下被隱藏、肉眼無法直觀辨識未展開錨點的痛點。
- **全新佔位符語法**：
  1. **插入佔位符 (Token Anchor)**：`__@{token}__`（如 `__@{PHASEXX_STANDARD_HEADER}__`、`__@{DYNAMIC_CONTEXT_MAP}__`）。支援大括號內微量空白容錯，解算後自動乾淨抹除殘留標籤行。
  2. **路徑佔位符 (URI Reference)**：`__#{uri}__`（如 `__#{module.root://agents-workflow/assets/standards/DocumentationStandards.md}__`）。編譯期 100% 原樣保留，作為 Markdown 文檔的語意參照與路徑錨點。
- **全域資產 1:1 遷移**：全面升級 `assets/templates/` (P01~P07)、`DevelopmentStandards.md` 與 `ContextInit.md` 中的標籤。
- **品質守門**：單元測試 (12/12) 與全系統回歸測試 (**99/99 Passed, 100% Ready**)。

---

## 2. 檔案變更清冊 (Detailed File Changes)

| 檔案路徑 | 變更性質 | 核心說明 |
| :--- | :---: | :--- |
| `source/agents-workflow/agents_workflow/compiler.py` | 修改 | 重構佔位符正則表達式、5-Step 狀態機多輪解算、空格容錯、自指死鎖防護與殘留行抹除邏輯。 |
| `source/agents-workflow/assets/templates/P01_requirements_spec.md` | 修改 | 將標頭錨點遷移為 `__@{PHASEXX_STANDARD_HEADER}__`。 |
| `source/agents-workflow/assets/templates/P02_architecture_plan.md` | 修改 | 將標頭錨點遷移為 `__@{PHASEXX_STANDARD_HEADER}__`。 |
| `source/agents-workflow/assets/templates/P03_api_spec.md` | 修改 | 將標頭錨點遷移為 `__@{PHASEXX_STANDARD_HEADER}__`。 |
| `source/agents-workflow/assets/templates/P04_implementation_plan.md` | 修改 | 將標頭錨點遷移為 `__@{PHASEXX_STANDARD_HEADER}__`。 |
| `source/agents-workflow/assets/templates/P05_task.md` | 修改 | 將標頭錨點遷移為 `__@{PHASEXX_STANDARD_HEADER}__`。 |
| `source/agents-workflow/assets/templates/P06_test_plan.md` | 修改 | 將標頭錨點遷移為 `__@{PHASEXX_STANDARD_HEADER}__`。 |
| `source/agents-workflow/assets/templates/P07_walkthrough.md` | 修改 | 將標頭錨點遷移為 `__@{PHASEXX_STANDARD_HEADER}__`。 |
| `source/agents-workflow/assets/standards/DevelopmentStandards.md` | 修改 | 將專案特化錨點遷移為 `__@{PROJECT_SPECIFIC_STANDARDS}__`。 |
| `source/agents-workflow/assets/workflows/ContextInit.md` | 修改 | 將動態地圖錨點遷移為 `__@{DYNAMIC_CONTEXT_MAP}__`。 |
| `source/agents-workflow/tests/test_compiler.py` | 修改 | 覆蓋新佔位符語法、空格容錯、路徑佔位符語意保留與自指防死鎖測試。 |
| `docs/agents-workflow/README.md` | 修改 | 知識庫更新：新增全新佔位符語法規範說明。 |
| `docs/agents-workflow/DESIGN_NOTES.md` | 修改 | 登記 `[DN-AW-04]` 設計決策。 |
| `CHANGELOG.md` | 修改 | 追加 `sub_03` 高階版本發布日誌。 |

---

## 3. 關鍵代碼展示 (Key Code Implementation Snippets)

### 3.1 正則工廠與殘留行抹除 (`compiler.py`)
```python
TOKEN_ANCHOR_REGEX = re.compile(r"__@\{\s*([A-Za-z0-9_]+)\s*\}__")
URI_REF_REGEX = re.compile(r"__#\{\s*([^}]+)\s*\}__")

def make_token_tag_regex(token_name: str) -> re.Pattern:
    """構造匹配指定 Token 標籤之正則表達式，支援大括號內部微量空格。"""
    return re.compile(r"__@\{\s*" + re.escape(token_name) + r"\s*\}__")

def make_purge_regex(token_name: str) -> re.Pattern:
    """構造用於抹除殘留 Token 錨點行之正則表達式，自動吞噬行首縮排與行尾換行。"""
    return re.compile(r"([ \t]*__@\{\s*" + re.escape(token_name) + r"\s*\}__[ \t]*\r?\n?)")
```

---

## 4. 驗證結果與品質門禁 (Verification & Quality Gates)

```text
======================================================================
YS-Codebase Test Execution Diagnostic Report
======================================================================
[*] Module: agents-workflow                                        [PASS]
    |-- [Contract] Auto-Contract Suite ... (3/3)
    \-- [Custom]   Custom Tests ........... (12/12)
[*] Module: core                                                   [PASS]
    |-- [Contract] Auto-Contract Suite ... (3/3)
    \-- [Custom]   Custom Tests ........... (53/53)
[*] Module: dev                                                    [PASS]
    |-- [Contract] Auto-Contract Suite ... (3/3)
    \-- [Custom]   Custom Tests ........... (25/25)
----------------------------------------------------------------------
Summary : 99 Total, 99 Passed, 0 Failed, 0 Skipped (14.318s)
Status  : PASSED (100% Ready)
======================================================================
```

---

## 5. 提交建議 (Conventional Commit Suggestions)

```bash
git commit -m "feat(agents-workflow): migrate placeholder formats to visible __@{token}__ and __#{uri}__ syntax"
```
