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
  - `dev release-check`: 3-Gate 發布就緒預檢。
  - `dev release`: 純淨生產發布打包。
  - `dev release-git`: 本地安全 git tag 發布流水線。
  - `dev test`: 沙盒隔離端到端自動化測試。

### 1.2 `agents-workflow.json`（規範注入）
- 向 `AGENTS_STANDARDS` Token 錨點注入開發者專屬工程規範與 Dogfooding 守則。
