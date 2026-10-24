# Dev 模組貢獻導覽清冊 (Contributes Manifest)

> 本清冊記錄 `dev` 開發者工具箱對外貢獻之擴充能力與協議。

## 1. 外部注入清冊 (Egress Contributions)

### 1.1 `core.json`（微內核指令與 URI 擴充）
- **語意 URI**：`module.source://`（源碼根目錄）、`module.build://`（本地開發產物）、`module.release://`（正式發布產物）。
- **CLI 指令樹**：
  - `dev create`: 一鍵生成標準模組骨架與 contributes 設定。
  - `dev check`: 靜態規範、Manifest、Schema 剛性檢驗。
  - `dev build`: 開發版打包（包含 tests/）。
  - `dev bump-*`: 版本號單向遞增（major/minor/patch/revision）。
  - `dev release-check`: 3-Gate 發布就緒預檢（Gate 1: 合規; Gate 2: 不可變; Gate 3: 單調性防回退）。
  - `dev release`: 純淨生產發布打包（Kahn DAG 拓撲依賴排序）。
  - `dev release-git`: 本地安全 git tag 發布流水線（commit 錯誤攔截防護）。
  - `dev test`: 沙盒隔離端到端自動化測試（單一 Token 參數傳遞、UNKNOWN 剛性阻斷）。
- **生命週期事件 (Events)**：
  - `on_test_setup`: 沙盒測試套件啟動前觸發。
  - `on_test_teardown`: 沙盒測試套件完成後清理時觸發。

### 1.2 `agents-workflow.json`（技能匯出與路由注入）
- 匯出 `yscb-module-dev` 模組開發技能，並向 `AGENTS_SKILL_ROUTING` 錨點注入生態系模組開發與熱調試條件路由。

## 2. 內部擴充清冊 (Ingress Contributions)

### 2.1 `custom_checks`（領域專屬靜態檢查規則）
- 允許其他生態系模組向 `dev check` 靜態合規引擎動態註冊領域專屬靜態檢查規則 (`CheckRuleDef`: name, description, severity, checker_func)。

