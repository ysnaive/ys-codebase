### 📦 Dev 開發者工具箱 (`dev` — 模組骨架建立、靜態合規檢查與沙盒熱調試)

- **① 模組定位與適用時機**：
  - 專為開發與擴充 YSCB 生態系模組設計，提供模組骨架建立、靜態合規檢查、隔離沙盒測試與 `@build` 本機熱部署閉環。
  - 當你需要新增 YSCB 模組、修改 `source/<mod>` 源碼並跑沙盒測試或準備打包發布時使用（隨包導出 [`yscb-module-dev`](`__#{module://dev/assets/skills/yscb-module-dev/SKILL.md}__`) 技能）。
- **② 標準用法速查 (Golden Recipes)**：
  - **靜態合規預檢 (`🟢 [SAFE]`)**：`python __${yscb.host://yscb.py}__ dev check <module>`（或 `--all` 檢查全模組）
  - **沙盒單測與熱部署 (`🟢 [SAFE]` / `🟡 [CONDITIONAL]`)**：`python __${yscb.host://yscb.py}__ dev test <module> -k <pattern>`（微調加 `--no-build`；全過後加 `--sync` 熱部署 `@build`）
  - **建立新模組與發布預檢**：`python __${yscb.host://yscb.py}__ dev create <module>` / `python __${yscb.host://yscb.py}__ dev release-check <module>`
  - *(注意：`dev bump-*`、`dev release`、`dev release-git` 與 `/bump-revision` 屬 `🔴 [GATED]` 發布操作，須獲明確授權)*
- **③ 隨包手冊語意連結**：
  - 深入探索沙盒隔離機制與 Dogfooding 閉環請按需唯讀查閱 [`dev 隨包手冊`](`__#{module://dev/README.md}__`)。
