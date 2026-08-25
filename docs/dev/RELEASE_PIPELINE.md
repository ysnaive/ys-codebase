# 開發者工具模組發布流水線手冊 (Release Pipeline Manual)

> 適用模組：`dev`  
> 模組路徑：`source/dev/dev/releaser.py`, `source/dev/scripts/cli.py`  
> 知識庫維度：維度 3（中觀專題手冊 Topic Docs）  
> 最後更新：2026-08-25  

---

## 1. 核心概述

`dev release` 是 YS-Codebase 模組從源碼到正式發布庫的核心自動化工具。它串聯了版本遞進、安全守門、純淨打包、Git 提交、智慧 Tag 觸發與交易原子回滾。

---

## 2. Pre-flight 4 大守門機制 (Pre-flight Gates)

在正式發布前，流水線自動執行嚴格檢查：
1. **Gate 1: Git 工作區乾淨檢查**（`git status --porcelain` 必須無未提交變更）。
2. **Gate 2: 測試套件 100% 通過**（自動執行全黑盒測試，可透過 `--no-test` 繞過）。
3. **Gate 3: 版本唯一性與不可變性檢查**（目標版本不可與 `release/` 已存在版本完全重複）。
4. **Gate 4: Manifest 合規性靜態檢查**（Manifest 欄位與結構必須通過 `Checker` 驗證）。

---

## 3. 發布五步流水線與智慧 Tag 矩陣

```text
[Pre-flight 4 Gates] 
       │ (All Passed)
       ▼
1. Version Bump (更新 source/manifest.json)
       ▼
2. Hermetic Release Packaging (純淨打包至 release/，淘汰同 X.Y.Z 舊 Revision)
       ▼
3. Git Commit (chore(release): release <mod>@<ver>)
       ▼
4. Smart Git Tag Trigger (建立 <mod>/v<ver>)
       ▼
[發布成功] (若中途任何步驟失敗，觸發 100% 原子交易回滾)
```

### 智慧 Git Tag 觸發矩陣
- **`major`**：預設自動建立 Git Tag (`True`)。
- **`minor`**：預設自動建立 Git Tag (`True`)。
- **`patch`**：預設**不建立** Git Tag (`False`)。
- **`revision`**：預設**不建立** Git Tag (`False`)。
- **CLI 旗標覆蓋**：`--tag` 強制打 Tag，`--no-tag` 強制不打 Tag。

---

## 4. 發布安全交易防護 (Release Transaction Guard)

若發布中途發生任何異常（如打包失敗、Git 操作失敗）：
- **Manifest 回滾**：還原 `source/manifest.json` 為原版本。
- **Release 單檔 Zip 回滾**：自動清除已寫入之 `release/<mod>/<ver>.zip` 單檔。
- **Index 回滾**：還原 `release/<mod>/index.json`。
- **Git 回滾**：若已建立 Tag 則自動刪除 Tag (`git tag -d`)；若已 Commit 則軟回退 (`git reset --soft HEAD~1`)。
