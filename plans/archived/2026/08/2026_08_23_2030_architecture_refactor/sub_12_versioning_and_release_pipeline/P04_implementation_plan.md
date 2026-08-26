# 實作計畫與定稿審查 (Implementation Plan & Review)

> 功能名稱：四段式版本號、雙軌來源庫 (Build vs Release)、三層安裝降級鏈、發布流水線與 Migration 機制重構  
> 建立日期：2026-08-25  
> 所屬主計畫：[2026_08_23_2030_architecture_refactor](../umbrella_overview.md)  
> 依據 P01~P03：[P01](./P01_requirements_spec.md), [P02](./P02_architecture_plan.md), [P03](./P03_api_spec.md)  
> 狀態：Confirmed  
> 擴充項目：none  
> 模板版本：v1.4  

---

## 1. 交叉審查核對清單 (Cross-Validation Checklist)

- [x] **FR 覆蓋完整性**：P01 中 FR-01 ~ FR-13 於 P03 API 規格書中皆有對應介面與簽名（`core.semver`, `core.uri`, `core.engine`, `core.installer`, `dev.builder`, `dev.releaser`, `dev.sandbox`, `dev.tester`, `yscb.py`）。
- [x] **EC 錯誤處理對齊**：P01 中 EC-01 ~ EC-08 於 P02/P03 均具備顯式防禦（三段式自動補齊、發布版本重複衝突阻斷、發布中斷自動原子回滾、Migration 缺腳本跳過、Migration 拋錯快照回滾、跨 Major 鎖定防護、三層鏈降級失敗報錯）。
- [x] **追溯鏈剛性對齊**：`P00 議題` ➔ `P01 (FR/EC)` ➔ `P02/P03 (API/DR)` ➔ `P04 (TASK)` ➔ `P06 (FT/ET/RT)` 實現 100% 雙向追溯。
- [x] **零第三方依賴**：所有新增與重構 100% 維持純 Python 3.10+ 標準庫實現。

---

## 2. 靈魂拷問 (Stress Test & Edge Case Scrutiny)

> **架構審查員提問 1**：  
> 「`dev release` 在執行發布 5 步流水線時，如果最後打 Git Tag 步驟失敗，會不會導致 Manifest 版本已經遞進但 Tag 沒打成的不一致狀態？」

**架構解析與防護回答**：
- **發布安全交易防護 (Release Transaction Guard)**：`dev.releaser` 在進入流水線前建立前置狀態備忘錄（記錄舊 Manifest 與舊 Index）。
- **全回滾補償機制**：若步驟 1~5 任一步驟失敗，`except` 區塊立即執行補償逆操作——復原 `source/manifest.json`、刪除剛產出的 `release/<mod>/<ver>/` 目錄、還原 `release/<mod>/index.json`、刪除半成品 Tag。
- **保證**：發布操作具備強原子性（All-or-Nothing），絕不留髒狀態。

---

> **架構審查員提問 2**：  
> 「`dev test` 徹底移除人工 `source/` 拷貝改走 `build://` 後，如果開發者修改了代碼但忘了 build，測試會不會吃到舊產物？」

**架構解析與防護回答**：
- **測試前自動前置 Build**：`dev.testing.tester:run_test` 在初始化沙盒前，**一律自動調用 `builder.build_module(clean=True)` 進行密封純淨打包**。
- **保證**：測試沙盒內執行的永遠是當前 `source/` 源碼 100% 即時編譯出來的最新產物，且自動包含 `tests/`，開發者完全無須手動執行 build。

---

> **架構審查員提問 3**：  
> 「模組 Migration 在跨版本升級（例如 `1.0.0` ➔ `1.3.0`）時，若模組作者在 `1.2.0` 沒有重大變更而未撰寫 `1.2.x.py`，升級流程會不會報錯中斷？」

**架構解析與防護回答**：
- **靜默容錯原則**：`core.engine:act_migrate` 在遍歷 Minor 階梯時，透過 `exists` 檢查腳本。若檔案不存在，判定為「該版本無需 Migration」並靜默跳過，順暢執行下一個階梯（`1.3.x.py`）。
- **嚴格中斷條件**：僅在遷移腳本實體存在且執行時**主動拋出例外或回傳 `False`** 時，系統才認定遷移失敗並觸發快照回滾。

---

## 3. 知識庫文檔衝擊與交付規劃 (Documentation Impact Plan)

> 依據 7 大抽象知識維度與使用者指示，預排 Phase 7 需 1:1 同步交付更新之知識庫清單：

| 知識庫文檔路徑 | 知識維度 | 預排更新內容與主題 | 對應 P03/P06 驗收錨點 |
| :--- | :---: | :--- | :--- |
| [`docs/core/ARCHITECTURE.md`](file:///h:/UseFolder/CodeRepo/ys_codebase/docs/core/ARCHITECTURE.md) | 維度 1 | 雙軌來源庫架構（`build://` 開發庫 vs `release://` 預設發布庫）與四大語意維度全景模型。 | P03 §1.2 / FT-03 |
| [`docs/core/SEMVER.md`](file:///h:/UseFolder/CodeRepo/ys_codebase/docs/core/SEMVER.md) | 維度 2 | 四段式 SemVer 運算器手冊（`major.minor.patch.revision`、同 X.Y.Z 單一 Revision 淘汰與常態三元約定）。 | P03 §1.1 / FT-01, FT-02 |
| [`docs/core/MIGRATION_SUBSYSTEM.md`](file:///h:/UseFolder/CodeRepo/ys_codebase/docs/core/MIGRATION_SUBSYSTEM.md) | 維度 3 | **[NEW]** 模組 Migration 增量階梯調用流程、腳本規範（`module://scripts/migrations/{major}.{minor}.x.py`）與安全快照回滾專題手冊。 | P03 §1.3 / FT-08 |
| [`docs/dev/RELEASE_PIPELINE.md`](file:///h:/UseFolder/CodeRepo/ys_codebase/docs/dev/RELEASE_PIPELINE.md) | 維度 3 | **[NEW]** `dev release` 發布流水線專題手冊（Pre-flight 4 大守門、Version Bump、純淨打包、智慧 Git Tag 矩陣與交易原子回滾）。 | P03 §1.4 / FT-06, FT-07 |
| [`docs/core/API_REFERENCE.md`](file:///h:/UseFolder/CodeRepo/ys_codebase/docs/core/API_REFERENCE.md) | 維度 4 | 登錄四段式 SemVer 介面、三層安裝降級鏈、`act_migrate` 與新增語意 URI 協議。 | P03 §1.1~1.4 / FT-01~08 |
| [`docs/core/DESIGN_NOTES.md`](file:///h:/UseFolder/CodeRepo/ys_codebase/docs/core/DESIGN_NOTES.md) | 維度 5 | 登記 `DN-09`（同 X.Y.Z 單一 Revision 淘汰原則）與 `DN-10`（發布交易防護與零污染 Git 邊界）。 | [P03:DR-01~09] |
| [`docs/dev/TESTING_FRAMEWORK.md`](file:///h:/UseFolder/CodeRepo/ys_codebase/docs/dev/TESTING_FRAMEWORK.md) | 維度 2 | 更新 `dev test` 去特例化全黑盒測試流水線架構（測試前自動 build，依三層鏈標準 install，零 source 拷貝）。 | P03 §1.6 / FT-05 |

---

## 4. 實作任務清單 (Implementation Task Matrix)

| 任務編號 | 實作項目 | 目標檔案 | 對應 FR / EC | 依賴前置 |
| :--- | :--- | :--- | :--- | :---: |
| **TASK-01** | `core.semver` 四段式解析、前三段比大小、三段式自動補齊與 `bump_version` 實作 | `source/core/core/semver.py` | FR-01, FR-02<br/>EC-01 | 無 |
| **TASK-02** | `core.uri` 註冊 `release://`、`build://`、`storage://` 與雙軌 config | `source/core/core/uri.py` | FR-03, FR-11 | TASK-01 |
| **TASK-03** | `dev.builder` 完整打包（含 `tests/`，版本 `X.Y.Z.build`）、Hermetic 清理與 `build/index.json` 維護 | `source/dev/dev/builder.py` | FR-04, FR-05 | TASK-01, TASK-02 |
| **TASK-04** | `core.engine` 三層降級鏈、`storage://` 雙層快照還原與 `act_migrate` 增量階梯調用 | `source/core/core/engine.py` | FR-04, FR-10, FR-12<br/>EC-05, EC-06, EC-08 | TASK-01~03 |
| **TASK-05** | `core.installer` 同 Major 鎖定防護與常態三元版本匹配 | `source/core/core/installer.py` | FR-02, FR-03, FR-10<br/>EC-07 | TASK-04 |
| **TASK-06** | `dev.releaser` 發布流水線、Pre-flight 4 大守門、同 X.Y.Z 淘汰清理、智慧 Tag 與交易原子回滾 | `source/dev/dev/releaser.py` (NEW) | FR-07, FR-08, FR-09<br/>EC-02, EC-03, EC-04 | TASK-01~05 |
| **TASK-07** | `dev.testing.sandbox` & `tester.py` 全黑盒測試流水線重構（自動 build + 標準 install） | `source/dev/dev/testing/sandbox.py`<br/>`source/dev/dev/testing/tester.py` | FR-06 | TASK-03~05 |
| **TASK-08** | `yscb.py` 官方 vs 第三方自舉判定與 `yscb://.gitignore` 零污染自動生成 | `yscb.py` | FR-13 | TASK-02 |
| **TASK-09** | 單元測試套件撰寫與全量 100% 綠燈回歸驗證 | `source/core/tests/test_semver_v4.py` (NEW)<br/>`source/core/tests/test_migration_ladder.py` (NEW)<br/>`source/dev/tests/test_release_pipeline.py` (NEW) | FT-01~FT-08<br/>ET-01~ET-06<br/>RT-01 | TASK-01~08 |

---

## 5. 決策紀錄整合 (Decision Records Master List)

- `[P04:DR-01]`：升級 `core.semver` 為四段式 `(major, minor, patch, revision)`，前三段數值決定大小，`revision` 不參與大小比較；三段式輸入自動補齊為 `X.Y.Z.0`。
- `[P04:DR-02]`：`release/` 發布庫對同 `X.Y.Z` 僅存單一最新 Revision，發布新修復版時自動清理舊版目錄並更新 `index.json`；外部常態三元版本宣告。
- `[P04:DR-03]`：註冊 `release://` 為系統唯一預設來源庫；`build://` 重定義為本地開發完整包來源庫；安裝依循 `build://` ➔ `mirror://` ➔ `provider` 三層降級鏈。
- `[P04:DR-04]`：`dev build` 執行 100% 完整打包（保留 `tests/`，版本標記 `X.Y.Z.build`），建置前 Hermetic 清空，版本遞進清理舊 build，更新 `build/index.json` 保持同構。
- `[P04:DR-05]`：`dev test` 測試前自動執行 `dev build`，沙盒內依三層鏈標準 `yscb install`，原地執行測試，徹底消除人工 `source/` 拷貝特例。
- `[P04:DR-06]`：建立 `dev.releaser` 模組，實作 `dev release` 5 步流水線、Pre-flight 4 大守門與發布安全交易防護（失敗 100% 原子回滾）。
- `[P04:DR-07]`：實作智慧 Git Tag 觸發矩陣：Major/Minor 預設打 Tag (`{mod}/v{ver}`)，Patch/Revision 預設不打 Tag，支援 `--tag`/`--no-tag` 覆蓋。
- `[P04:DR-08]`：模組 Migration 採 `module://scripts/migrations/{major}.{minor}.x.py` 增量階梯調用；日常 `update` 實施同 Major 鎖定；升級失敗透過包含 `storage://` 的快照原子回滾。
- `[P04:DR-09]`：`yscb init` 於 `yscb://.gitignore` 自動生成內部忽略規則，實現零專案污染；依 `source/core/` 判定官方開發端 vs 第三方端自舉。

---

## 6. 閉合確認 (Closing Confirmation)

- [ ] 開發者已確認：Phase 4 實作計畫定稿、靈魂拷問審查與 P06 測試計畫無誤，指示進入 Phase 5 開始實作
