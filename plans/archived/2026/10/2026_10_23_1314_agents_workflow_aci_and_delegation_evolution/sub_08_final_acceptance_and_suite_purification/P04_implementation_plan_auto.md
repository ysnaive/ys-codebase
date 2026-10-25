# 實作計畫與交叉驗證書 (Implementation Plan)

> 功能名稱：全主計畫二次驗收、測試集子系統 1:1 純化、歷史目錄清理與三層文檔收官 (sub_08_final_acceptance_and_suite_purification)  
> 建立日期：2026-10-25  
> 所屬主計畫：2026_10_23_1314_agents_workflow_aci_and_delegation_evolution  
> 狀態：Confirmed  
> 模型：Gemini 3.8 Flash (Medium)  

---

## 1. 交叉驗證檢查清單 (Cross-Validation Checklist)

- [x] `P01` 需求清單（`FR-01` ~ `FR-05`）與邊界（`EC-01` ~ `EC-04`）已 100% 映射至 `P02 §3` 檔案變更清單與 `P04 §4` 實作任務。
- [x] `P02 §3` 為全計畫變更清單唯一 SSOT，`P03` 僅宣告測試類別契約，未重複冗餘條目。
- [x] `P03 §2` 嚴格落實 `Signature-Only`，未預先貼入函式內部實作程式碼。
- [x] 測試純化方案遵循 `testing-sop` 六大鐵律（1:1 歸戶、零歷史墓碑、100% 沙盒清理、零虛假斷言）。

---

## 2. 知識庫文檔衝擊與交付規劃 (Documentation Impact Plan)

| 知識維度 | 目標文件路徑 | 衝擊摘要與交付規劃 |
| :--- | :--- | :--- |
| **③ 中觀機制** | `docs/agents-workflow/FACTORY_PIPELINE.md` | 修正釋出清單為 `cache://` 空間，更新最後修改日期。 |
| **⑥ 操作引導** | `ys_codebase/source/agents-workflow/README.md` | 同步雙軌 CLI 指令自省速查、`_auto.md` 雙軌相容說明與 Roadmap 最新狀態。 |
| **⑤ 防坑邊界** | `docs/agents-workflow/DESIGN_NOTES.md` | 已於先前登錄 `[DN-AW-15]`，本次核驗索引一致性。 |
| **④ 介面註解** | 原始碼 Docstrings | 6 大子系統測試類別與核心測試方法補齊清楚之 Docstring。 |
| **⑦ 演進歷史** | `CHANGELOG.md` & `plans/.../changelog.md` | 追加全主計畫結案與收官純化之詳細里程碑紀錄。 |

---

## 3. 架構靈魂拷問 (Stress Test & Resilience Review)

1. **問：物理刪除 7 支測試檔會不會導致過去辛苦建立的測試覆蓋率下降？**  
   **答**：不會。本次整併遵循「無損遷移原則」，除了徹底廢棄的殭屍檔 `test_auto_workflow.py`（斷言已移除的 `WORKFLOW_AUTO`）與 4 處墓碑斷言外，其餘 47 個有效測試方法全數 1:1 搬遷至對應子系統測試檔中，並補齊 `tearDown` 沙盒清理。
2. **問：根目錄清理 `scratch` 與 `scripts` 會不會影響日常執行？**  
   **答**：不會。已排查兩檔為 9 月初誤提交進 Git 的 0 引用孤兒檔，現行全生態系中無任何模組呼叫它們，清理後工作區更加標準純淨。

---

## 4. 實作任務清單 (Task Breakdown & Topological Sequence)

1. **TASK-01**：工作區根目錄歷史遺留清理：執行 `git rm -r scratch scripts`，物理刪除 `scratch/server_test.log` 與 `scripts/scan_native_io.py`。
2. **TASK-02**：純化並擴充 `test_publisher.py`：吸收 `test_jit_release.py`、`test_manifest_placement.py`、`test_publisher_cross_platform.py` 中全部有效測試案例；移除 `watchdog` 與 `ensure_jit_release` 墓碑斷言；消除 `if uri.exists` 寬容包覆；補齊 `tearDown` `shutil.rmtree`。
3. **TASK-03**：純化並擴充 `test_roadmap.py`：吸收 `test_plans_toolchain.py` 中 5 個 `TodoManager` 與 `RoadmapManager` 測試案例，補齊 `tearDown` `shutil.rmtree`。
4. **TASK-04**：純化並擴充 `test_plans_toolchain.py`：移出 todo 測試；吸收 `test_plans_status.py`（移除 `VALID_CHANGELOG_TYPES` 墓碑）、`test_plans_aci_toolchain.py` 與 `test_plans_model_record.py` 中之 Plans 驗證器/狀態機測試；補齊 `tearDown` 沙盒清理。
5. **TASK-05**：純化並擴充 `test_compiler.py`、`test_initializer.py` 與 `test_targets.py`：於 `test_compiler.py` 吸收資產 Meta-Linter、移除 `session-analysis` 墓碑並補齊 `mock_rel.assert_called_once()`；於 `test_initializer.py` 剛性斷言 `paths.roadmap == "!undefined"`；優化 `test_targets.py` 方法命名。
6. **TASK-06**：物理刪除 7 支碎片/殭屍測試檔：執行 `git rm` 刪除 `test_auto_workflow.py`、`test_jit_release.py`、`test_manifest_placement.py`、`test_publisher_cross_platform.py`、`test_plans_status.py`、`test_plans_aci_toolchain.py`、`test_plans_model_record.py`。
7. **TASK-07**：三層文檔最終對齊：更新 `docs/agents-workflow/FACTORY_PIPELINE.md` 與 `ys_codebase/source/agents-workflow/README.md`。
8. **TASK-08**：全模組與全生態系二次驗收：執行 `dev check agents-workflow` 與 `dev test agents-workflow -q`，確認 6 支子系統測試檔 100% 通過（0 Skip, 0 Fail, 0 殘留）。

---

## 5. 決策定稿 (Confirmed Decision Records)

- **[P04:DR-01] 確立 6 支純化測試檔為唯一 SSOT**：全模組測試套件嚴格鎖定為 `test_compiler.py`、`test_publisher.py`、`test_initializer.py`、`test_targets.py`、`test_roadmap.py`、`test_plans_toolchain.py`，嚴禁日後任何新計畫另建臨時或計畫名測試檔。

