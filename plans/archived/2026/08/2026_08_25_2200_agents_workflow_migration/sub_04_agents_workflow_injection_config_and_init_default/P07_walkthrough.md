# Phase 7: 成果展示與結案報告 (Walkthrough) - agents-workflow 配置治理與一鍵初始化

> 計畫名稱：`sub_04_agents_workflow_injection_config_and_init_default`  
> 建立日期：2026-08-26  
> 所屬主計畫：[2026_08_25_2200_agents_workflow_migration](../umbrella_overview.md)  
> 依據驗證報告：[P06_test_plan.md](./P06_test_plan.md)  
> 狀態：`Completed` (Phase 7 結案完成)  
> 擴充項目：none  
> 模板版本：v1.4  

---

## 1. 變更概述 (High-Level Summary)

本子計畫完成了 `agents-workflow` 的專案級組態治理與 `--init-default` 一鍵初始化協議綁定及目錄建立指令：
- **4 大 Workflow URI 協議貢獻**：在 `manifest.json` 中註冊 `workflow.plans://`, `workflow.archived://`, `workflow.ext://`, `workflow.docs://`，由 Core URI 模組統一解析。
- **組態模板與 `!undefined` 剛性解耦**：提供 `config.project.json` 模板，所有專案路徑預設剛性為 `"!undefined"`，貫徹微內核零臆測鐵律；同時宣告 `ide: []`, `enable_agents_md: true`, `enable_project_changelog: true` 3 大保留欄位。
- **`--init-default` 互動式一鍵初始化引導**：
  - 封裝推薦預設路徑：`project://.agent_workflow/{plans,plans/archived,extensions}` 與 `project://docs`。
  - 實體路徑存在性探測：條列清單，若目錄已存在則輸出 `[提示] 目錄 <path> 已存在，確認要自動綁定在該路徑嗎?` 提醒。
  - 互動確認 `[-y / -n]`：確認後自動調用 `os.makedirs` 建立缺失目錄，並原子寫回 `config.project.json`。
- **`--path-*` 變種參數覆蓋支援**：支援 `--path-plans`, `--path-archived`, `--path-ext`, `--path-docs` 與 `-y` / `--yes` 自動確認模式。
- **品質守門**：單元測試 (17/17) 與全系統回歸測試 (**104/104 Passed, 100% Ready**)。

---

## 2. 檔案變更清冊 (Detailed File Changes)

| 檔案路徑 | 變更性質 | 核心說明 |
| :--- | :---: | :--- |
| `source/agents-workflow/manifest.json` | 修改 | 在 `contributes.core.uri_schemes` 註冊 4 大 `workflow.*` 協議。 |
| `source/agents-workflow/config.project.json` | 新增 | 專案級組態模板，`paths` 全為 `"!undefined"`，包含 `ide: []` 等保留欄位。 |
| `source/agents-workflow/agents_workflow/initializer.py` | 新增 | 封裝 `WorkflowInitializer`，實作推薦路徑、存在性探測、目錄建立與組態原子寫入。 |
| `source/agents-workflow/scripts/cli.py` | 修改 | 新增 `--init-default` 與 `--path-*` 參數解析調度。 |
| `source/agents-workflow/tests/test_initializer.py` | 新增 | 覆蓋協議註冊、模板驗證、自動初始化、已存在路徑提醒、參數覆蓋與取消操作測試。 |
| `docs/agents-workflow/README.md` | 修改 | 知識庫更新：新增 `--init-default` 指令說明與 4 大協議清冊。 |
| `docs/agents-workflow/DESIGN_NOTES.md` | 修改 | 登記 `[DN-AW-05]` 設計決策。 |
| `CHANGELOG.md` | 修改 | 追加 `sub_04` 高階版本發布日誌。 |

---

## 3. 關鍵代碼展示 (Key Code Implementation Snippets)

### 3.1 4 大 Workflow 協議宣告 (`manifest.json`)
```json
"contributes": {
  "core": {
    "uri_schemes": [
      { "token": "workflow.plans", "type": "config", "value": "paths.plans", "description": "指向 agents-workflow 活躍開發計畫目錄" },
      { "token": "workflow.archived", "type": "config", "value": "paths.archived", "description": "指向 agents-workflow 歷史封存計畫目錄" },
      { "token": "workflow.ext", "type": "config", "value": "paths.ext", "description": "指向 agents-workflow 專案擴充清單目錄" },
      { "token": "workflow.docs", "type": "config", "value": "paths.docs", "description": "指向 agents-workflow 專案知識庫文檔目錄" }
    ]
  }
}
```

### 3.2 推薦路徑與初始化引導 (`WorkflowInitializer`)
```python
DEFAULT_RECOMMENDED_PATHS = {
    "plans": "project://.agent_workflow/plans",
    "archived": "project://.agent_workflow/plans/archived",
    "ext": "project://.agent_workflow/extensions",
    "docs": "project://docs"
}
```

---

## 4. 驗證結果與品質門禁 (Verification & Quality Gates)

```text
======================================================================
YS-Codebase Test Execution Diagnostic Report
======================================================================
[*] Module: agents-workflow                                        [PASS]
    |-- [Contract] Auto-Contract Suite ... (3/3)
    \-- [Custom]   Custom Tests ........... (17/17)
[*] Module: core                                                   [PASS]
    |-- [Contract] Auto-Contract Suite ... (3/3)
    \-- [Custom]   Custom Tests ........... (53/53)
[*] Module: dev                                                    [PASS]
    |-- [Contract] Auto-Contract Suite ... (3/3)
    \-- [Custom]   Custom Tests ........... (25/25)
----------------------------------------------------------------------
Summary : 104 Total, 104 Passed, 0 Failed, 0 Skipped (33.094s)
Status  : PASSED (100% Ready)
======================================================================
```

---

## 5. 提交建議 (Conventional Commit Suggestions)

```bash
git commit -m "feat(agents-workflow): add config.project.json template, 4 workflow URI schemes, and --init-default command"
```
