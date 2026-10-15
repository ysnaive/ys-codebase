---
target: "Dev"
doc_type: "topic"
status: "active"
source_paths:
  - "yscb://source/dev/scripts/cli.py"
  - "yscb://source/dev/dev/checker.py"
  - "yscb://source/dev/dev/builder.py"
  - "yscb://source/dev/dev/tester.py"
  - "yscb://source/dev/dev/releaser.py"
  - "yscb://source/dev/contributes/_format.json"
  - "yscb://source/dev/contributes/agents-workflow.json"
related_docs:
  - "./README.md"
  - "./user_guide.md"
  - "./testing_guide.md"
  - "./topics/release_governance.md"
  - "./DESIGN_NOTES.md"
last_updated: "2026-10-15"
---

# Dev 模組架構規格說明書 (Architecture Specification)

> 模組名稱：`dev`  
> 模組版本：`1.1.0.1`（以 `module.source://dev/manifest.json` 為準）  
> 核心定位：YS-Codebase 內部研發工具鏈的核心引擎，提供建置、測試、版本控制與發布治理。

---

## 1. 系統分層拓撲 (System Architecture)

```text
┌─────────────────────────────────────────────────────────────────────────────┐
│ 1. 表現層 (CLI Routing Layer) - scripts/cli.py                              │
│    • 解析 build / release / test / bump-* / release-check / release-git     │
│    • 極簡路由派發，支援單一模組與 --all|-a 批次操作（含 release-check --all） │
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
│      - check_module() (8 步靜態合規檢核管線與 3-Tier 嚴重度分級)            │
│    • core/semver.py                                                         │
│      - bump_version() (版本單向遞增 major/minor/patch/revision)             │
│      - compare_semver(), match_constraint()                                 │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 2. Checker 8 步靜態合規檢核管線與 3-Tier 嚴重度 (`PASS` / `WARN` / `FAIL`)

`dev/checker.py` 中的 `Checker.check_module(name)` 對目標模組執行 8 步靜態合規檢核管線，並將問題歸類為三階嚴重度 (`CheckSeverity`)：
- **`PASS`**：完全合規，無任何警告與錯誤。
- **`WARN`**：存在非阻斷性建議或棄用提醒（如缺少 `contributes/core.json`、遺留暫存檔、測試方法漏寫 `self.mark_passed()`），`CheckReport.passed` 仍為 `True`。
- **`FAIL`**：違反剛性契約或架構紅線（如語法錯誤、Schema 違規、Zero-Probing 違規、直接繼承 `unittest.TestCase`），`CheckReport.passed` 為 `False` 並阻斷發布（Gate 1）。

| 步驟 | 檢核方法 | 分類標籤 (`category`) | 檢核重點與規則 |
| :---: | :--- | :--- | :--- |
| **Step 1** | `_check_manifest` | `MANIFEST` | 驗證 `manifest.json` 必填欄位 (`name`, `version`, `entry`, `dependencies`)、目錄名稱一致性、SemVer 合法性、非 `core` 模組強制依賴 `core`、`optional` 與 `onboarding` 格式，並透過 `_check_pip_dependencies` 驗證 `pip_dependencies` 字典型態與規格。 |
| **Step 2** | `_check_core_injection` | `CONTRIBUTES` | 整合 `core.validator.ContributesValidator` 走訪 `contributes/`：<br/>1. **Meta-Check**：檢核 `_format.json` 型別表達式與 Schema DSL 合法性。<br/>2. **Ingress / Egress 邊界檢核**：對所有 `<target>.json` 依據目標模組 `_format.json` 執行嚴格校驗（`strict_points=True`），未知擴充點、型別不符或跨模組越權注入一律判定 `FAIL`。 |
| **Step 3** | `_check_file_structure` | `STRUCTURE` / `CONTRIBUTES` | 檢核 `scripts/cli.py` 存在性與雙軌命令契約（`_check_cli_compliance`：禁止 `def main`、禁止 `if __name__ == "__main__":`、禁止頂層裸執行敘述）、攔截根目錄散落之 `config.*.json`（強制收斂於 `configurable/`）、檢查殘留暫存檔 (`.tmp`/`.bak`)，以及當存在 `contributes/` 時強制要求 `contributes/_manifest.md`。 |
| **Step 4** | `_check_source_files` | `SYNTAX` / `PROBING` / `ANTIPATTERN` | 遞迴解析所有 `.py` 檔案之 AST（豁免模組/類別/函式首行 Docstring 節點）：<br/>• **Zero Probing (`PROBING`)**：非 `core`/`dev` 生產代碼嚴禁存取 `module.source://`。<br/>• **Anti-Pattern (`ANTIPATTERN`)**：非 `core`/`dev` 生產代碼嚴禁直接讀寫 `config.project.json`、`config.local.json` 或 `contributes.merged.json`，強制使用 `core.config` / `core.contributes` SDK。 |
| **Step 5** | `_check_test_classes` | `STRUCTURE` / `ANTIPATTERN` | AST 掃描 `tests/test_*.py`：<br/>• 嚴禁直接繼承 `unittest.TestCase`（強制繼承 `YSCBTestCase`，否則 `FAIL`）。<br/>• 檢查 `test_*` 方法是否呼叫 `self.mark_passed()`（未標記 `@require(Requirement.NONE)` 且缺失時發出 `WARN`）。<br/>• 攔截同時標記 `LOGIC` 與 `ISOLATED_SANDBOX` 之反模式（`WARN`）。 |
| **Step 6** | `_check_sandbox_hooks` | `SYNTAX` / `STRUCTURE` / `ANTIPATTERN` | 若存在 `scripts/hook.dev.py`，以 AST 驗證無頂層裸執行語句，且 `on_test_setup` / `on_test_teardown` 必須接受至少 1 個參數 (`context`)。 |
| **Step 7** | `_check_docs_pollution` | `DOCUMENTATION` | 掃描模組內 `docs/*.md`，若發現硬編碼 `project://source/` 則發出 `WARN`，引導改用 `module://<mod>/` 語意 URI。 |
| **Step 8** | `_check_custom_rules` | 依規則定義 | 讀取 `core.contributes.get("dev", "custom_checks")` 註冊之領域自訂檢查器（透過 `importlib` 動態載入 `checker_func(name, real_dir, report)` 執行）。 |

---

## 3. 3-Gate 發布品質守門閘門 (The 3-Gate Release Verification Model)

在執行任何發布操作（`dev release`、`dev release-check`、`dev release-git`）時，系統均強制依序通過 3 道不可踰越之品質閘門：

```text
[待發布版本 Target Version]
       │
       ▼
 ┌───────────┐   Failed
 │  Gate 1   │ ─────────> [阻斷: 合規性錯誤清單 (Checker 8 步檢核 FAIL)]
 └─────┬─────┘
       │ Passed
       ▼
 ┌───────────┐   Failed
 │  Gate 2   │ ─────────> [阻斷: ReleaseVersionExistsError (四元版本在庫重複，--force 時放行)]
 └─────┬─────┘
       │ Passed
       ▼
 ┌───────────┐   Failed
 │  Gate 3   │ ─────────> [阻斷: VersionRollbackError (版本倒退或小於在庫同三元組最高 revision)]
 └─────┬─────┘
       │ Passed
       ▼
 [發布放行: 調用 Builder.package_release 純淨打包]
```

1. **Gate 1 (靜態合規性檢驗)**：
   - 完整調用 `Checker.check_module(mod)` 執行 8 步檢核管線，任何 `CheckSeverity.FAIL` 均立即阻斷發布。
2. **Gate 2 (版本不可變性檢驗 - Immutability)**：
   - 檢查 `release/<mod>/<target_version>.zip` 是否已存在。若在庫已有同名四元版本且未傳入 `--force`，立即拋出 `ReleaseVersionExistsError` 阻斷，嚴禁無聲覆蓋。
3. **Gate 3 (版本單調遞增檢驗 - Monotonicity)**：
   - 掃描 `release/<mod>/` 在庫同三元組 `X.Y.Z` 下的所有現存 revision，要求待發布版本號必須嚴格大於在庫最高版本（$V_{\text{target}} > V_{\text{highest\_in\_triplet}}$；若傳入 `--force` 則允許等於最高版本以供原地重打包，但仍嚴格阻斷小於最高版本之歷史回退），否則拋出 `VersionRollbackError`。

---

## 4. 3-Revision 時序滑動窗口保留演算法 (Sliding Window & Convergence)

為杜絕歷史產物無限膨脹並兼顧熱修復與回退需求，`Builder._update_release_index` 實作了時序滑動窗口演算法：

- **規則 1（同三元組時序滑動窗口）**：
  - 同一個三元版本 `X.Y.Z` 下，發布庫依發布時序**最多同時保留 3 個最新 Revision**（即 `X.Y.Z.W`, `X.Y.Z.W-1`, `X.Y.Z.W-2`）。
  - 當發布第 4 個 Revision 時，系統自動物理刪除最舊的第 1 個 Revision zip 檔案。
- **規則 2（跨三元組升級舊版收斂）**：
  - 當模組發生 `patch`、`minor` 或 `major` 遞增（三元組變更為 `X.Y.Z+1` 或更高）時，所有過往舊三元組的延遲 Revision 自動物理清理，**僅保留該三元組最後最高 1 份 Revision**（`X.Y.Z.W_max`）。
- **規則 3（磁碟實體 SSOT 索引同步）**：
  - 淘汰完成後，以磁碟上真實存在的 `*.zip` 檔案為唯一事實來源，動態生成 `release/<mod>/index.json`，已被物理刪除的舊 Revision 自動自清冊排除。

---

## 5. 本地純淨打包與 `release-git` 4 步原子安全流水線

### 5.1 本地打包與 Git 工作區狀態正交解耦
- **純淨打包不檢查 Git Dirty 狀態**：`dev release` 在本地產出單檔 `release/<mod>/<ver>.zip` 並維護 `index.json` 時，與 Git 工作區狀態 (`git status --porcelain`) 完全正交解耦，不因本地尚未 Commit 的變更而阻斷打包，大幅提升本地模組迭代與離線測試流暢度。
- **非 Git 環境自動降級容錯**：若執行環境並非 Git 儲存庫（或無 `.git` 目錄），流水線自動安全略過 Git Commit 與 Tag 步驟而不拋出例外。

### 5.2 `release-git` 4 步原子安全流水線
`release-git` 整合了測試、校驗、打包與版本控制：

1. **Step 1: E2E 跑測** ➔ 調用 `Tester._run_test(mod)`（若未 100% 通過立即中斷）。
2. **Step 2: 3-Gate 校驗** ➔ 調用 `release_check(mod, force=force)`（未通過立即中斷）。
3. **Step 3: 純淨打包** ➔ 若目標版本尚未發布（或帶 `--force`），調用 `release_module(mod, force=force)` 產出發布包並更新索引；若已發布且無 `--force` 則智慧略過重複打包。
4. **Step 4: 本地 Git 提交與打標** ➔ 執行本地 `git add -A` ➔ `git commit -m "<msg>"` ➔ `git tag -a "<mod>/v<ver>" -m "<msg>"`（`--force` 時附加 `-f`）。
   - 🚨 **安全邊界**：絕對禁止調用 `git push`，保證操作完全停留在本機端，提交決策權留給開發者。

---

## 6. 本機開發直裝通道 (`@build`) 與 Contributes 雙向擴充架構

### 6.1 本機建置產物直裝通道 (`install <mod>@build`)
- 當 `core.engine.PackageManager` 解析到版本約束為 `@build`（或 revision 為 `build`）時，特例直連本地端 `module.build://<mod>/` 安裝由 `dev build` 產出之 `*.build.zip`（若尚未建置則拋出明確引導提示），免除日常自引用調試 (Dogfooding) 需先執行正式 `release` 的繁瑣流程。

### 6.2 Contributes 雙向擴充契約 (Ingress & Egress)
- **Ingress（輸入擴充點 `contributes/_format.json`）**：
  - `dev` 模組開放 `custom_checks` 擴充點（型別 `$CheckRuleDef`，含 `name`, `description`, `severity`, `checker_func`），允許其他模組向 `dev check` 管線（Step 8 `_check_custom_rules`）註冊領域專屬靜態檢查規則。
- **Egress（對外能力貢獻）**：
  - `contributes/core.json`：向 `core` 註冊 `dev` 命名空間下所有 CLI 子指令、參數規格、安全分級 (`tier`) 與使用正反例 (`usage.pros` / `usage.cons`)。
  - `contributes/agents-workflow.json`：向 `agents-workflow` 匯出 (`export`) `yscb-module-dev` 專屬技能包（位於 `module://dev/assets/skills/yscb-module-dev`），並透過 `insert`（`mode: "below"`）將生態系模組開發與 Dogfooding 觸發條件動態注入至全域 `AGENTS_SKILL_ROUTING` 路由錨點。
