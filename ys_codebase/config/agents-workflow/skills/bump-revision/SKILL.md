---
name: bump-revision
description: 將處於 @build 狀態之開發模組批次執行版本號遞增、正式打包與本機安裝切換。僅於顯式輸入 /bump-revision 時觸發，嚴禁主動觸發。
---

# 專案版本晉升與發布工作流 (BumpRevision)

> [!CAUTION]
> **授權守門（B-Strict）：嚴禁 Agent 自主觸發，僅限開發者顯式輸入 `/bump-revision` 時執行。日常開發一律維持 `@build` 直裝。**

本工作流為專案特化工作流，用於掃描 [yscb.config.json](`__#{project://yscb.config.json}__`) 中的已安裝模組清單 (`installed_modules`)，自動篩選所有處於 `@build` 本機開發狀態的模組，並依序執行版本晉升 (Version Bump)、正式打包 (Release) 與自部署更新 (Update)。

```markdown
/bump-revision 四步執行檢核表：
- [ ] 步驟 1：掃描 yscb.config.json，篩選版本含 .build 或 @build 之目標模組
- [ ] 步驟 2：判定各模組晉升等級（開發者指定等級或預設 revision）
- [ ] 步驟 3：依模組依賴拓撲順序執行 bump-<level> -> release -> install --force -y
- [ ] 步驟 4：呈遞版本晉升與發布完成報告卡
```

---

## 核心原則與適用情境 (Scope & Axioms)

1. **專案特化發布自動化 (Automated Track B Pipeline)**：
   - 快速收斂日常 `@build` 模組，完成版本遞增、產出發布包並更新環境。
2. **靈活版本升級策略 (Flexible Bump Hierarchy)**：
   - 預設升級等級為 `revision` (`python __${yscb.host://yscb.py}__ dev bump-revision <module>`)。
   - 支援開發者於指令中顯式指定特定模組之升級等級（如 `/bump-revision core:patch knowledge-db:minor`）。
3. **安全發布與免測部署 (No Redundant Post-Install Tests)**：
   - 打包發布後直接調用 `python __${yscb.host://yscb.py}__ install <module> --force -y` 進行正式版物化切換（因 `update` 指令對 `@build` 開發版設有防降級略過保護），無需且嚴禁重複調用測試。

---

## 執行步驟 (4-Step Execution Pipeline)

```mermaid
flowchart TD
    Start["觸發 /bump-revision [模組:等級 (可選)]"] --> Scan["步驟 1: 掃描 yscb.config.json"]
    Scan --> Filter{"篩選 installed_modules\n版本包含 .build 或 @build"}
    Filter -- 無 build 模組 --> NoOp["提示所有模組皆已為正式發布版，結束"]
    Filter -- 有 build 模組 --> Decide["步驟 2: 判定各模組 Bump 等級\n(開發者指定等級 | 預設 revision)"]
    Decide --> Pipeline["步驟 3: 依序執行軌道 B 發布流水線"]
    subgraph TrackB ["軌道 B 閉環流水線 (針對每個目標模組)"]
        B1["python yscb.py dev bump-[level] <mod>"] --> B2["python yscb.py dev release <mod>"]
        B2 --> B3["python yscb.py install <mod> --force -y"]
    end
    Pipeline --> TrackB
    TrackB --> Report["步驟 4: 呈遞版本晉升與發布摘要卡"]
```

### 步驟 1：掃描 `yscb.config.json` 與篩選目標模組 (Scan & Filter)

1. 檢視專案根目錄之 [yscb.config.json](`__#{project://yscb.config.json}__`)。
2. 檢查 `installed_modules` 物件中的各模組 `version` 欄位。
3. 篩選所有版本包含 `.build` 或 `@build` 的模組清單（例：`"core": { "version": "1.0.2.build" }`）。
4. 若無任何 `@build` 模組，向開發者呈報：「目前所有模組皆已為正式發布版本，無需執行版本晉升」，並結束流程。

---

### 步驟 2：判定各模組 Bump 等級 (Bump Level Decision)

1. 檢查開發者調用 `/bump-revision` 時所提供的參數。
2. 比對是否有指定特定模組之升級等級：
   - 支援等級：`revision`、`patch`、`minor`、`major`。
   - 格式範例：`/bump-revision core:patch knowledge-db:minor`
3. 規則：
   - 若開發者有指定特定模組等級 ➔ 採用指定等級。
   - 未指定之模組 ➔ 預設採用 `revision` (`dev bump-revision <mod>`)。

---

### 步驟 3：依序執行版本晉升、發布與更新 (Bump, Release & Install)

依模組依賴拓撲順序（`core` ➔ `server` ➔ `knowledge-db` ➔ `agents-workflow` ➔ `dev`）依序對每一個目標模組執行以下指令：

1. **版本遞增**：
   ```bash
   python __${yscb.host://yscb.py}__ dev bump-[revision|patch|minor|major] <module>
   ```
2. **正式打包發布**：
   ```bash
   python __${yscb.host://yscb.py}__ dev release <module>
   ```
3. **本機正式版切換安裝**：
   ```bash
   python __${yscb.host://yscb.py}__ install <module> --force -y
   ```

---

### 步驟 4：呈遞版本晉升成果摘要卡 (Summary & Output)

向開發者呈遞結構化更新摘要表：

```markdown
# 🚀 模組版本晉升與發布完成報告 (Bump & Release Summary)

| 模組名稱 | 升級前版本 (@build) | 晉升等級 | 發布後正式版本 | 更新狀態 |
| :--- | :---: | :---: | :---: | :---: |
| `[module_1]` | `[old_version]` | `[revision|patch|...]` | `[new_version]` | `✅ 已發布並更新` |
| `[module_2]` | `[old_version]` | `[revision|patch|...]` | `[new_version]` | `✅ 已發布並更新` |

- **發布通道**：正式發布通道 (`__${project://release/}__`)
- **環境狀態**：已同步更新至 [yscb.config.json](`__#{project://yscb.config.json}__`)
```

---

## 常見踩坑指南 (Gotchas)

- **切勿使用 `yscb.py update` 切換 `@build` 模組**：`update` 對本地 `@build` 開發版設有防覆蓋略過保護，完成 `dev release` 後必須使用 `install <module> --force -y` 才能切換為正式版。
- **涉及 `agents-workflow` 或 Contributed 資產變更時記得同步工作流投影**：當 `agents-workflow`、`dev` 或 `knowledge-db` 切換為正式安裝版後，若涉及工作流資產變更，可補跑 `agents-workflow compile` 與 `release --force` 確保第二層空間與正式版對齊。

