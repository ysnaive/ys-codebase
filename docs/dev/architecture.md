# Dev 模組架構規格說明書 (Architecture Specification)

> 模組名稱：`dev`  
> 模組版本：`1.0.0`  
> 核心定位：YS-Codebase 內部研發工具鏈的核心引擎，提供建置、測試、版本控制與發布治理。

---

## 1. 系統分層拓撲 (System Architecture)

```text
┌─────────────────────────────────────────────────────────────────────────────┐
│ 1. 表現層 (CLI Routing Layer) - scripts/cli.py                              │
│    • 解析 build / release / test / bump-* / release-check / release-git     │
│    • 極簡路由派發，參數防呆校驗 (例：release-check 拒絕 --all)                │
└──────────────────────────────────────┬──────────────────────────────────────┘
                                       │
        ┌──────────────────────────────┴──────────────────────────────┐
        ▼                                                             ▼
┌──────────────────────────────────────────┐  ┌───────────────────────────────┐
│ 2. 發布調度層 (Releaser Pipeline)        │  │ 2. 測試調度層 (Tester Pipeline)│
│    dev/releaser.py                       │  │    dev/tester.py              │
│    • Releaser.release_check() [3-Gate]   │  │    • Tester._run_test()       │
│    • Releaser.release_module()           │  │    • 預設前置調用 Builder.build │
│    • Releaser.release_all() [DAG 拓撲]   │  │    • 支援 --no-build 跳過     │
│    • Releaser.release_git() [4 步流水線] │  │    • 虛擬沙盒配置與跑測       │
└───────────────────┬──────────────────────┘  └───────────────┬───────────────┘
                    │                                         │
                    └──────────────────┬──────────────────────┘
                                       ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ 3. 核心建置與校驗引擎層 (Engine & Core Services Layer)                      │
│    • dev/builder.py: Builder                                                │
│      - build_module() (自動清空 .build/<mod>/，保留 tests/)                 │
│      - package_release() (純淨打包，3-Revision 滑動窗口淘汰，index.json SSOT)│
│    • dev/checker.py: Checker                                                │
│      - check_module() (靜態合規性、entry 實體存在性、依賴格式校驗)          │
│    • core/semver.py                                                         │
│      - bump_version() (版本單向遞增 major/minor/patch/revision)             │
│      - compare_semver(), match_constraint()                                 │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 2. 3-Gate 發布品質守門閘門 (The 3-Gate Release Verification Model)

在執行任何發布操作（`dev release`、`dev release-check`、`dev release-git`）時，系統均強制依序通過 3 道不可踰越之品質閘門：

```text
[待發布版本 Target Version]
       │
       ▼
 ┌───────────┐   Failed
 │  Gate 1   │ ─────────> [阻斷: 合規性錯誤清單 (Manifest/Entry/Syntax)]
 └─────┬─────┘
       │ Passed
       ▼
 ┌───────────┐   Failed
 │  Gate 2   │ ─────────> [阻斷: ReleaseVersionExistsError (四元版本在庫重複)]
 └─────┬─────┘
       │ Passed
       ▼
 ┌───────────┐   Failed
 │  Gate 3   │ ─────────> [阻斷: VersionRollbackError (版本倒退或小於等於在庫同三元組最高 revision)]
 └─────┬─────┘
       │ Passed
       ▼
 [發布放行: 調用 Builder.package_release 純淨打包]
```

1. **Gate 1 (靜態合規性檢驗)**：
   - 驗證 `manifest.json` 欄位完整性與 SemVer 語意格式。
   - 驗證 `scripts/cli.py` 實體檔案存在、具備 `main(argv)` 進入點且 Python AST 語法無解析錯誤。
2. **Gate 2 (版本不可變性檢驗 - Immutability)**：
   - 檢查 `release/<mod>/<target_version>.zip` 是否已存在。若在庫已有同名四元版本，立即拋出 `ReleaseVersionExistsError` 阻斷，嚴禁無聲覆蓋。
3. **Gate 3 (版本單調遞增檢驗 - Monotonicity)**：
   - 掃描 `release/<mod>/` 在庫同三元組 `X.Y.Z` 下的所有現存 revision，要求待發布版本號必須嚴格大於在庫最高版本（$V_{\text{target}} > V_{\text{highest\_in\_triplet}}$），拋出 `VersionRollbackError` 阻斷倒退。

---

## 3. 3-Revision 時序滑動窗口保留演算法 (Sliding Window & Convergence)

為杜絕歷史產物無限膨脹並兼顧熱修復與回退需求，`Builder._update_release_index` 實作了時序滑動窗口演算法：

- **規則 1（同三元組時序滑動窗口）**：
  - 同一個三元版本 `X.Y.Z` 下，發布庫依發布時序**最多同時保留 3 個最新 Revision**（即 `X.Y.Z.W`, `X.Y.Z.W-1`, `X.Y.Z.W-2`）。
  - 當發布第 4 個 Revision 時，系統自動物理刪除最舊的第 1 個 Revision zip 檔案。
- **規則 2（跨三元組升級舊版收斂）**：
  - 當模組發生 `patch`、`minor` 或 `major` 遞增（三元組變更為 `X.Y.Z+1` 或更高）時，所有過往舊三元組的延遲 Revision 自動物理清理，**僅保留該三元組最後最高 1 份 Revision**（`X.Y.Z.W_max`）。
- **規則 3（磁碟實體 SSOT 索引同步）**：
  - 淘汰完成後，以磁碟上真實存在的 `*.zip` 檔案為唯一事實來源，動態生成 `release/<mod>/index.json`，已被物理刪除的舊 Revision 自動自清冊排除。

---

## 4. `release-git` 4 步原子安全流水線

`release-git` 整合了測試、校驗、打包與版本控制：

1. **Step 1: E2E 跑測** ➔ 調用 `Tester._run_test(mod)`（若未 100% 通過立即中斷）。
2. **Step 2: 3-Gate 校驗** ➔ 調用 `release_check(mod)`（未通過立即中斷）。
3. **Step 3: 純淨打包** ➔ 調用 `release_module(mod)` 產出發布包並更新索引。
4. **Step 4: 本地 Git 提交與打標** ➔ 執行本地 `git add -A` ➔ `git commit -m "<msg>"` ➔ `git tag -a "<mod>/v<ver>" -m "<msg>"`。
   - 🚨 **安全邊界**：絕對禁止調用 `git push`，保證操作完全停留在本機端，提交決策權留給開發者。
