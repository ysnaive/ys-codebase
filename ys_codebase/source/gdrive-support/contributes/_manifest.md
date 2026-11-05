# `gdrive-support` 模組擴充貢獻宣告清單 (Contributes Manifest)

本文件為 `gdrive-support` 模組之雙向擴充契約總表，定義本模組對外開放之擴充點（Ingress）與向其他模組注入之貢獻項目（Egress）。

---

## 1. 對外開放之擴充點 (Ingress Schema — `_format.json`)

其他生態系模組可於其 `contributes/gdrive-support.json`（或宿主專案於 `ys_codebase/config/gdrive-support/contribute.json`）中，依據 `_format.json` 規範向 `gdrive-support` 註冊同步空間與選填路徑映射：

- **`sync_spaces`** (`list[SyncSpaceDef]`)：定義欲納入 Google Drive `repo_sync`（`<root_folder_id>/<repo_sync_root>/<branch>/`，預設 `repo_sync_root = "repo"`）同步之 `file-space` 名稱 (`space`) 與選填之本地至雲端路徑重映射清單 (`mapping: [{local, remote}]`)。僅於 `repo_sync.enable: true` 時生效。

---

## 2. 向其他模組注入之貢獻 (Egress Contributes)

| 目標模組 | 宣告檔案 | 貢獻內容摘要 |
| :--- | :--- | :--- |
| **`core`** | `contributes/core.json` | 註冊 `gdrive-support`（短別名 `gdrive`）CLI 命令群（原子指令：`status`, `auth`, `ls`, `get`, `put`, `rm`, `mkdir`, `shortcut`；`repo_sync` 指令：`init`, `branch`, `checkout`, `pull`, `push`, `sync`）與預設 `gitignore` 憑證保護規則。 |
| **`server`** | `contributes/server.json` | 註冊 `gdrive-sync` (`GDriveSyncServiceWorker`) 背景服務（受 `repo_sync.enable: false` 與 `repo_sync.auto_sync: false` 雙重預設待機守門）。 |
| **`agents-workflow`** | `contributes/agents-workflow.json` | 匯出本地專用的 `gdrive-local-ops` 技能（`module://gdrive-support/assets/skills/gdrive-local-ops`），並向 `AGENTS_SKILL_ROUTING`、`HOW_TO_CONFIG_MODULES` 與 `HOW_TO_YSCB_MODULES` 注入使用與組態導引（註：給外部雲端 AI 的隨包資產 `assets/external_skill/gdrive-external-ops/SKILL.md` 與 `assets/external_skill/gemini-drive-guide/GEMINI_BOOTSTRAP_GUIDE.md` 僅隨包封存，不注入本地 `agents-workflow`）。 |
