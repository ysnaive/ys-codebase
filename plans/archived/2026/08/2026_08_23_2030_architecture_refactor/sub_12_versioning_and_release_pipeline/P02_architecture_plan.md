# 架構與模組設計說明書 (Architecture & Module Plan)

> 功能名稱：四段式版本號、雙軌來源庫 (Build vs Release)、三層安裝降級鏈、發布流水線與 Migration 機制重構  
> 建立日期：2026-08-25  
> 所屬主計畫：[2026_08_23_2030_architecture_refactor](../umbrella_overview.md)  
> 依據 P01：[P01_requirements_spec.md](./P01_requirements_spec.md)  
> 狀態：Draft (Phase 2 設計方案)  
> 擴充項目：none  
> 模板版本：v1.4  

---

## 1. 系統模組劃分與邊界 (Module Architecture & Boundaries)

```mermaid
graph TD
    classDef host fill:#1e1e2e,stroke:#cba6f7,stroke-width:2px,color:#cdd6f4;
    classDef core fill:#0f172a,stroke:#3b82f6,stroke-width:2px,color:#60a5fa;
    classDef dev fill:#064e3b,stroke:#10b981,stroke-width:2px,color:#34d399;

    subgraph HostEntry ["超薄宿主入口 (yscb.py)"]
        InitBootstrap["<b>init_bootstrap()</b><br/>• 官方 vs 第三方自舉判定<br/>• 產生 yscb://.gitignore"]:::host
        HostDispatch["<b>dispatch_module()</b><br/>• 動態派發至 modules/{mod}"]:::host
    end

    subgraph CoreModule ["Core 核心基礎設施模組 (source/core/core/)"]
        SemVerEngine["<b>semver.py</b><br/>• 四段式 (major.minor.patch.revision) 解析<br/>• 前三段數值比大小 / 三段式自動補齊<br/>• find_best_version / 範圍匹配"]:::core
        UriEngine["<b>uri.py</b><br/>• 註冊 release:// (預設來源)<br/>• build:// (開發來源) / storage:// (持久資料)<br/>• config://config.project.json & local.json"]:::core
        EngineSys["<b>engine.py</b><br/>• act_solve_deps (三層降級鏈)<br/>• act_snapshot / act_restore (modules+config+storage)<br/>• act_migrate (階梯式調用引擎)"]:::core
        InstallerSys["<b>installer.py</b><br/>• cmd_install / cmd_update (同 Major 鎖定)<br/>• 常態三元版本匹配"]:::core
    end

    subgraph DevModule ["Dev 開發與測試模組 (source/dev/dev/)"]
        BuilderSys["<b>builder.py</b><br/>• build_module (完整打包含 tests，版本 X.Y.Z.build)<br/>• Hermetic Clean 清理舊 build"]:::dev
        ReleaserSys["<b>releaser.py (NEW)</b><br/>• dev release (Bump + 純淨打包 + Commit + Tag)<br/>• Pre-flight 4 大守門與發布交易原子回滾<br/>• 同 X.Y.Z 單一 Revision 淘汰清理"]:::dev
        SandboxSys["<b>testing/sandbox.py</b><br/>• 建立沙盒，依三層鏈調用標準 yscb install<br/>• 徹底移除人工 source/ 拷貝"]:::dev
        TesterSys["<b>testing/tester.py</b><br/>• dev test 前自動調用 dev build<br/>• 沙盒內原地執行 dev op-test"]:::dev
    end

    InitBootstrap --> HostDispatch
    HostDispatch --> UriEngine
    UriEngine --> SemVerEngine
    InstallerSys --> EngineSys
    EngineSys --> SemVerEngine
    EngineSys --> UriEngine
    TesterSys --> BuilderSys
    TesterSys --> SandboxSys
    SandboxSys --> InstallerSys
    ReleaserSys --> BuilderSys
    ReleaserSys --> SemVerEngine
```

---

## 2. 核心運作流程與循序圖 (Lifecycle Sequence Flow)

### 2.1 `dev release` 發布五步流水線與原子交易防護 (FR-07, FR-08, FR-09)

```mermaid
sequenceDiagram
    autonumber
    actor Dev as 開發者 / CI
    participant CLI as dev.releaser (cmd_release)
    participant Gate as Pre-flight Gates
    participant Manifest as source/manifest.json
    participant Builder as dev.builder
    participant Index as release/index.json
    participant Git as Git Toolchain

    Dev->>CLI: python yscb.py dev release core minor
    activate CLI
    CLI->>Gate: 執行 4 大守門檢查 (Git Clean, Test 100%, 版本衝突/覆蓋, Manifest 合規)
    Gate-->>CLI: 守門 100% 通過
    
    Note over CLI,Index: 進入發布交易區塊 (Transaction Guard)
    CLI->>CLI: 記錄 pre-release 狀態 (old_manifest, old_index)
    CLI->>Manifest: 1. Version Bump (1.0.0.0 ➔ 1.1.0.0)
    CLI->>Builder: 2. Hermetic 純淨打包 (排除 tests/) 寫入 release/core/1.1.0.0/
    CLI->>Index: 3. 更新 release/core/index.json (同 X.Y.Z 淘汰舊 Revision)
    CLI->>Git: 4. Git Commit ("chore(release): release core@1.1.0.0")
    CLI->>Git: 5. 依層級打 Git Tag ("core/v1.1.0.0")
    
    alt 步驟 1~5 成功
        CLI-->>Dev: 發布完成，呈遞摘要報表
    else 步驟發生異常
        CLI->>Manifest: 補償還原 old_manifest
        CLI->>Index: 補償還原 old_index
        CLI->>Builder: 刪除殘留 release/core/1.1.0.0/ 目錄
        CLI->>Git: 刪除半成品 Tag (若有)
        CLI-->>Dev: 拋出例外，Working Tree 100% 保持乾淨
    end
    deactivate CLI
```

### 2.2 `dev test` 去特例化全黑盒流水線 (FR-05, FR-06)

```mermaid
sequenceDiagram
    autonumber
    actor Dev as 開發者 / CLI
    participant Tester as dev.testing.tester
    participant Builder as dev.builder
    participant SB as dev.testing.sandbox
    participant Core as core.installer (沙盒內)
    participant Runner as dev.testing.runner (沙盒內)

    Dev->>Tester: python yscb.py dev test --all
    activate Tester
    Tester->>Builder: 1. 自動打包待測模組至 build:// (含 tests/，版本 X.Y.Z.build)
    Tester->>SB: 2. 初始化純淨微型虛擬沙盒
    Tester->>Core: 3. 沙盒內依三層鏈 (build:// -> mirror:// -> provider) 標準 install
    Note over Core,SB: 4. 沙盒內 modules/ 自帶 tests/，零 source/ 拷貝特例
    Tester->>Runner: 5. 沙盒內原地執行 dev op-test
    Runner-->>Tester: 6. 收集 Contract & Custom 測試結果
    Tester-->>Dev: 7. 輸出綜合診斷報表
    deactivate Tester
```

### 2.3 模組 Migration 增量階梯調用流程 (FR-10, FR-12)

```mermaid
sequenceDiagram
    autonumber
    actor User as 使用者 / CLI
    participant Inst as core.installer
    participant Eng as core.engine
    participant Snap as Snapshot Manager
    participant Script as module://scripts/migrations/

    User->>Inst: yscb update core (1.0.0 ➔ 1.3.0)
    activate Inst
    Inst->>Eng: 檢查當前版本與目標版本 (同 Major 鎖定)
    Inst->>Snap: 1. 建立雙層快照 (modules/, config://, storage://, host config)
    Inst->>Eng: 2. 解包新版本產物至 modules/core
    
    loop 階梯式調用 (1.1.x.py, 1.2.x.py, 1.3.x.py)
        Eng->>Script: 3. 檢查遷移腳本存在性
        alt 腳本存在
            Eng->>Script: 執行 migrate(context)
            Script-->>Eng: 回傳 True (成功)
        else 腳本不存在
            Eng->>Eng: 靜默跳過 (該 minor 無 migration)
        end
    end
    
    alt 全部階梯成功
        Eng->>Eng: 4. 更新組態之版本號記錄
        Inst-->>User: 升級並遷移成功！
    else 任一階梯拋錯 / 回傳 False
        Eng->>Snap: 5. 觸發原子快照回滾
        Snap-->>Eng: 代碼、組態與 storage 100% 還原
        Inst-->>User: 拋出 MigrationError，已安全回滾！
    end
    deactivate Inst
```

---

## 3. 受影響模組與檔案矩陣 (Impacted Files Matrix)

| 檔案路徑 | 變更類型 | 核心職責與修改重點 | 對應 FR / EC |
| :--- | :---: | :--- | :--- |
| [`source/core/core/semver.py`](file:///h:/UseFolder/CodeRepo/ys_codebase/ys_codebase/source/core/core/semver.py) | Modify | 升級四段式 `(major, minor, patch, revision)` 解析；前三段數值比大小；三段式自動補齊為 `X.Y.Z.0`；同級以最新 Revision 為準。 | FR-01, FR-02<br/>EC-01 |
| [`source/core/core/uri.py`](file:///h:/UseFolder/CodeRepo/ys_codebase/ys_codebase/source/core/core/uri.py) | Modify | 註冊 `release://` 與 `release.root://`（預設來源庫）；維護 `build://`、`storage://`、`config://config.project.json` 與 `config://config.local.json`。 | FR-03, FR-11 |
| [`source/core/core/engine.py`](file:///h:/UseFolder/CodeRepo/ys_codebase/ys_codebase/source/core/core/engine.py) | Modify | 1. `act_solve_deps` 實作 `build://` ➔ `mirror://` ➔ `provider` 三層降級解析。<br/>2. `act_snapshot` / `act_restore` 擴充納入 `storage://` 與雙軌 config。<br/>3. 實作 `act_migrate` 增量階梯調用引擎。 | FR-04, FR-10, FR-12<br/>EC-05, EC-06, EC-08 |
| [`source/core/core/installer.py`](file:///h:/UseFolder/CodeRepo/ys_codebase/ys_codebase/source/core/core/installer.py) | Modify | 1. `cmd_update` 實作同 Major 鎖定防護。<br/>2. 支援常態三元版本號匹配對應唯一最新 Revision。<br/>3. `default_provider` 導向 Git 遠端索引。 | FR-02, FR-03, FR-10<br/>EC-07 |
| [`source/dev/dev/builder.py`](file:///h:/UseFolder/CodeRepo/ys_codebase/ys_codebase/source/dev/dev/builder.py) | Modify | 1. `build_module` 預設為完整打包（含 `tests/`，版本強制標記 `X.Y.Z.build`）。<br/>2. 建置前清空目標目錄，版本遞進時自動清理舊 `*.build`。<br/>3. 自動更新 `build/<mod>/index.json` 維持同構 Provider。 | FR-04, FR-05 |
| [`source/dev/dev/releaser.py`](file:///h:/UseFolder/CodeRepo/ys_codebase/ys_codebase/source/dev/dev/releaser.py) | **NEW** | 實作 `cmd_release`：Pre-flight 4 大守門、四段式 Bump、純淨打包、同 X.Y.Z 舊 Revision 淘汰清理、Git Commit/Tag 與發布交易原子回滾。 | FR-07, FR-08, FR-09<br/>EC-02, EC-03, EC-04 |
| [`source/dev/dev/testing/sandbox.py`](file:///h:/UseFolder/CodeRepo/ys_codebase/ys_codebase/source/dev/dev/testing/sandbox.py) | Modify | 重構沙盒鋪設邏輯：移除人工 `source/` 拷貝，改為於沙盒內依三層鏈調用標準 `yscb install`，原地獲取自帶 tests 的模組。 | FR-06 |
| [`source/dev/dev/testing/tester.py`](file:///h:/UseFolder/CodeRepo/ys_codebase/ys_codebase/source/dev/dev/testing/tester.py) | Modify | `cmd_test` 測試前自動調用 `dev.builder` 打包待測模組至 `build://`，沙盒內原地調用 `dev op-test`。 | FR-06 |
| [`yscb.py`](file:///h:/UseFolder/CodeRepo/ys_codebase/yscb.py) | Modify | 1. `init` 時自動於 `yscb://.gitignore` 產生專屬忽略規則。<br/>2. 依 `source/core/` 判定官方開發端 vs 第三方端自舉模式。 | FR-13 |
| [`source/core/tests/test_semver_v4.py`](file:///h:/UseFolder/CodeRepo/ys_codebase/ys_codebase/source/core/tests/test_semver_v4.py) | **NEW** | 四段式 SemVer 解析、三段式自動補齊、無比價 revision 運算與排序單元測試。 | FR-01, FR-02<br/>EC-01 |
| [`source/core/tests/test_migration_ladder.py`](file:///h:/UseFolder/CodeRepo/ys_codebase/ys_codebase/source/core/tests/test_migration_ladder.py) | **NEW** | 增量 Migration 階梯調用、缺腳本跳過、拋錯快照回滾與同 Major 鎖定測試。 | FR-10, FR-12<br/>EC-05, EC-06, EC-07 |
| [`source/dev/tests/test_release_pipeline.py`](file:///h:/UseFolder/CodeRepo/ys_codebase/ys_codebase/source/dev/tests/test_release_pipeline.py) | **NEW** | Pre-flight 4 大守門、Version Bump、純淨發布打包、同 X.Y.Z 淘汰清理、智慧 Tag 與失敗原子回滾整合測試。 | FR-07, FR-08, FR-09<br/>EC-02, EC-03, EC-04 |

---

## 4. 決策紀錄整合 (Decision Records Master List)

- `[P02:DR-01]`：升級 `core.semver` 為四段式 `(major, minor, patch, revision)`，前三段數值決定大小，`revision` 不參與大小比較；三段式輸入解析期自動補齊為 `X.Y.Z.0`。
- `[P02:DR-02]`：`release/` 發布庫對同 `X.Y.Z` 僅存單一最新 Revision，發布新修復版時自動清理舊版目錄並更新 `index.json`；外部常態三元版本宣告。
- `[P02:DR-03]`：註冊 `release://` 為系統唯一預設來源庫；`build://` 重定義為本地開發完整包來源庫；安裝依循 `build://` ➔ `mirror://` ➔ `provider` 三層降級鏈。
- `[P02:DR-04]`：`dev build` 執行 100% 完整打包（保留 `tests/`，版本標記 `X.Y.Z.build`），建置前 Hermetic 清空，版本遞進清理舊 build，更新 `build/index.json` 保持同構。
- `[P02:DR-05]`：`dev test` 測試前自動執行 `dev build`，沙盒內依三層鏈標準 `yscb install`，原地執行測試，徹底消除人工 `source/` 拷貝特化。
- `[P02:DR-06]`：建立 `dev.releaser` 模組，實作 `dev release` 5 步流水線、Pre-flight 4 大守門與發布安全交易防護（失敗 100% 原子回滾）。
- `[P02:DR-07]`：實作智慧 Git Tag 觸發矩陣：Major/Minor 預設打 Tag (`{mod}/v{ver}`)，Patch/Revision 預設不打 Tag，支援 `--tag`/`--no-tag` 覆蓋。
- `[P02:DR-08]`：模組 Migration 採 `module://scripts/migrations/{major}.{minor}.x.py` 增量階梯調用；日常 `update` 實施同 Major 鎖定；升級失敗透過包含 `storage://` 的快照原子回滾。
- `[P02:DR-09]`：`yscb init` 於 `yscb://.gitignore` 自動生成內部忽略規則，實現零專案污染；依 `source/core/` 判定官方開發端 vs 第三方端自舉。
