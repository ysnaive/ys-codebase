---
target: "Installer/UpgradePipeline"
doc_type: "topic_doc"
status: "active"
source_paths:
  - "yscb_installer.py"
  - "yscb_cli.py"
related_docs:
  - "./README.md"
  - "./DESIGN_NOTES.md"
  - "../Core/SEMVER_ENGINE.md"
last_updated: "2026-08-23"
---

# 五階段事務性安全升級流水線手冊

本文件說明 `yscb_installer.py` 在執行模組安裝、升級與 Installer 自身自舉升級時的五階段防禦體系與保護協定。

---

## 1. 五階段事務流水線流程

```
┌─────────────────────────────────────────────────────────────┐
│ Stage 1: Pre-flight Check (相依約束與相容性檢查)            │
│ ➔ 遍歷 manifest.json 之 dependencies，校驗已安裝版本與約束  │
├─────────────────────────────────────────────────────────────┤
│ Stage 2: Staging & Snapshot Backup (建立舊版快照備份)       │
│ ➔ 將現存模組快照備份至 .yscb_cache/backup/{module}_{ts}/     │
├─────────────────────────────────────────────────────────────┤
│ Stage 3: Protected Merge (分級資產覆蓋與增量深層合併)       │
│ ➔ 執行 config.project.json deep_merge / local 唯讀保留      │
├─────────────────────────────────────────────────────────────┤
│ Stage 4: Migration Execution (鏈式增量遷移與回滾守門)       │
│ ➔ 調用 _migration.py，若失敗立即執行 _rollback_snapshot     │
├─────────────────────────────────────────────────────────────┤
│ Stage 5: Commit & Finalize (後置 Hook 與狀態登記)           │
│ ➔ 調用 _installed.py 並更新 yscb_config.json 登記表         │
└─────────────────────────────────────────────────────────────┘
```

---

## 2. 三大資產分級保護機制

1. **不可變代碼資產 (Core Code)**：全量覆蓋替換，杜絕歷史殘留檔案。
2. **結構化專案配置 (`config.project.json`)**：
   - 採用 `deep_merge(template_dict, user_saved_dict)` 演算法，保留開發者自訂設定，並安全注入新版新增之預設鍵值。
3. **本地環境配置 (`config.local.json`)**：
   - 100% 唯讀保留，絕對不被覆寫。
4. **專案規範文件 (`AGENTS.md`)**：
   - 透過 `<!-- YSCB_AGENTS_BEGIN -->` 與 `<!-- YSCB_AGENTS_END -->` 進行核心章節軟合併，保護開發者自訂規範無損。

---

## 3. Installer 自舉升級 (Self-Update)

針對單檔起手腳本（`yscb_installer.py` 與 `yscb_cli.py`），提供獨立自更新機制：
- **CLI 指令**：`python yscb_cli.py installer self-update [--force]`
- **Windows 原子替換**：先將新版寫入 `.tmp` 暫存檔，再以 `os.replace()` 執行原子搬移，徹底規避 Windows 執行中檔案鎖定問題。
