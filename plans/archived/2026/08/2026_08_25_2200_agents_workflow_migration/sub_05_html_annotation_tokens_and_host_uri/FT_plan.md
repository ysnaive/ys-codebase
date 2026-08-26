# Fast Track 計畫說明書 (FT Plan) - HTML 註解 Token 註解與 yscb.host 協議

> 計畫名稱：`sub_05_html_annotation_tokens_and_host_uri`  
> 建立日期：2026-08-26  
> 所屬主計畫：[2026_08_25_2200_agents_workflow_migration](../umbrella_overview.md)  
> 分流層級：Level 0 (Fast Track)  
> 當前狀態：`Completed` (FT-3 結案審查完成)  
> 擴充項目：none  
> 模板版本：v1.4  

---

## 1. 需求與背景 (Context & Requirements)

### 1.1 核心需求
1. **`agents-workflow` 添加 HTML 註解 Token 與 Replace 解算**：
   - 註冊 Token：`"BEGIN_HTML_ANNOTATION"` 與 `"END_HTML_ANNOTATION"`。
   - 註冊 Insert：在 `manifest.json` 中配置 replace 模式解算，分別替換為字面值 `<!--` 與 `-->`。
2. **`core` 添加 `yscb.host://` 語意協議**：
   - 協議名稱：`yscb.host://`。
   - 類型：`const`。
   - 行為：強制指向起手腳本 `yscb.py` 與 `yscb.config.json` 所在之宿主根目錄。

### 1.2 驗收準則 (Acceptance Criteria)
- **AC-01**：`agents-workflow` 的 `manifest.json` 正確宣告 2 個 Token 與對應的 `insert` replace 宣告。
- **AC-02**：`compiler.resolve_single_artifact()` 能正確將 `__@{BEGIN_HTML_ANNOTATION}__` 與 `__@{END_HTML_ANNOTATION}__` 物化為 `<!--` 與 `-->`。
- **AC-03**：`core` 的 `manifest.json` 與 `uri.py` 正確註冊並解析 `yscb.host://` 指向宿主目錄。
- **AC-04**：單元測試與全系統回歸測試 100% Passed。

---

## 2. 架構設計與變更清冊 (Architecture & Changes)

### 2.1 `agents-workflow/manifest.json` 變更
- 註冊 `BEGIN_HTML_ANNOTATION` 與 `END_HTML_ANNOTATION` Token 與 `insert` (replace 為 `<!--` 與 `-->`)。

### 2.2 `core/manifest.json` & `core/core/uri.py` 變更
- `manifest.json`：註冊 `yscb.host` 協議（`type: "const"`, `value: "{yscb_host}"`）。
- `uri.py`：支援 `yscb.host://` fast-path 與 `{yscb_host}` 變數展開。

---

## 3. 測試驗證紀錄 (Test Execution Log)

| 測試項目 | 驗證目標 | 實機測試結果 | 狀態 |
| :--- | :--- | :--- | :---: |
| **FT-01** | Token 宣告自省 | `python yscb.py agents-workflow tokens` 成功展示 5 個 Token（含 2 個 HTML 註解 Token） | `Passed` |
| **FT-02** | Token 展開物化 | `test_ft_07_html_annotation_tokens_resolution` 驗證物化為 `<!-- slide -->` | `Passed` |
| **FT-03** | `yscb.host://` 協議自省 | `python yscb.py uri list` 成功展示 `yscb.host://` -> `H:\UseFolder\CodeRepo\ys_codebase` | `Passed` |
| **FT-04** | `yscb.host://` 單元測試 | `source/core/tests/test_uri.py` 解析通過 | `Passed` |
| **RT-01** | 全模組回歸驗證 | `python yscb.py dev test --all`：**104 Total, 104 Passed, 0 Failed, 0 Skipped** | `Passed` |

---

## 4. 結案審查狀態

- **當前狀態**：`Completed` (FT-3 結案完成)
