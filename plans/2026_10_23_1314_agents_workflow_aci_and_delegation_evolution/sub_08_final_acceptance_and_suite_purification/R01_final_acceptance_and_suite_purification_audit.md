# 技術調研報告：`agents-workflow` 收官二次驗收、測試集六維度純化與工作區清理評估 (R01_final_acceptance_and_suite_purification_audit.md)

> 調研主題：`sub_08` 全主計畫二次驗收、`tests/` 13 檔六維度純化映射、歷史目錄清理與三層文檔對齊評估  
> 建立日期：2026-10-25  
> 所屬主計畫：2026_10_23_1314_agents_workflow_aci_and_delegation_evolution  
> 調研狀態：Concluded  
> 模型：Gemini 4 Argon (High)  
> 模板版本：v1.1  

---

## 1. 背景與調研目標 (Background & Objectives)

- **核心問題與痛點**：
  1. **`agents-workflow/tests/` 歷史碎片與病灶累積**：經過多個歷史主計畫與本次 `sub_01` ~ `sub_07` 快速迭代，`ys_codebase/source/agents-workflow/tests/` 累積了 **13 支測試檔（共 119 個測試方法）**，其中包含 7 支以單次計畫或局部特性命名的碎片檔（`T-02`）、1 支因廢棄 `@require(Requirement.WORKFLOW)` 標籤而長期被測試器靜默 Skip 且斷言已失效的殭屍檔 `test_auto_workflow.py`（`T-01`/`T-03`）、4 處歷史墓碑斷言（`T-03`）、5 處 `if ...:` 寬容放行或漏斷言（`T-01`），以及 6 支檔案 `tempfile.mkdtemp()` 未於 `tearDown` 清理（`T-05`）。
  2. **工作區根目錄歷史 Git 追蹤遺留**：根目錄存在 9 月初誤提交進 Git 之 `./scratch/server_test.log`（0 bytes 空檔，Commit `ee02b201`）與 `./scripts/scan_native_io.py`（一次性 AST 掃描腳本，Commit `b563f8d4`），全庫 0 引用卻殘留於版本控制中。
  3. **局部文檔滯後**：`docs/agents-workflow/FACTORY_PIPELINE.md` 與隨包 `ys_codebase/source/agents-workflow/README.md` 尚有少數段落未同步 `sub_01`~`sub_07` 最新狀態（如 `cache://` 清單路徑、`sub_06` 雙軌 CLI 自省、`todo`/`roadmap promote` 與 `--phase`/`--log` 參數）。
- **調研目標**：
  1. 完成 `testing-sop` 情境 B Step 1 & Step 2 之 **「13 檔六維度病灶體檢與子系統 1:1 歸戶映射表」**。
  2. 核對 `sub_01` ~ `sub_07` 與已消費 Roadmap 儲備之 `Consume-on-Promote` 閉環完整性。
  3. 盤點根目錄清理與三層文檔修正精確位置，並評估最佳收官實作推進模式。

---

## 2. 候選方案分析與對比 (Candidate Evaluation)

### 2.1 測試集子系統歸戶粒度方案對比

| 方案 | 運作原理與目標拓撲 | 優點 (Pros) | 缺點 / 成本 (Cons) | 適用度評級 |
| :--- | :--- | :--- | :--- | :---: |
| **方案 A（推薦）：6 大核心子系統 1:1 歸戶（13 檔 $\to$ 6 檔）** | 嚴格對齊 `agents_workflow` 6 大生產模組：<br>1. `test_compiler.py`（含內建資產編譯與契約檢核）<br>2. `test_publisher.py`（整併 `jit_release`, `manifest_placement`, `cross_platform`）<br>3. `test_initializer.py`<br>4. `test_targets.py`<br>5. `test_roadmap.py`（整併 `TodoManager` & `RoadmapManager`）<br>6. `test_plans_toolchain.py`（整併 `status`, `aci_toolchain`, `model_record`）<br>物理刪除 **7 支**碎片/殭屍檔。 | • **100% 符合 `testing-sop` 鐵律 1**：測試檔與 `agents_workflow/` 生產子系統 1:1 嚴格對應，零碎片檔。<br>• 消除 6 處重複的沙盒與暫存目錄 `setUp`/`tearDown` 樣板代碼。 | • `test_plans_toolchain.py` 與 `test_compiler.py` 單檔行數較豐富（約 800~1,100 行），可透過檔內獨立 `TestCase` 類別清晰分區。 | ⭐⭐⭐⭐⭐<br>**(強烈推薦)** |
| **方案 B：6 大生產子系統 + 1 支靜態資產 Meta-Linter（13 檔 $\to$ 7 檔）** | 同方案 A，但將原 `test_plans_model_record.py` 中檢驗內建 17 個 Skills / 16 個 Templates 標頭與文字契約的 10 個測試獨立命名為 `test_workflow_assets.py`（物理刪除 6 支碎片檔）。 | • 單檔行數較平均（每檔約 200~700 行）。 | • `assets/` 並非獨立 Python 子系統（其載入與展開本就由 `compiler.py` 與 `verifier.py` 管轄），多出一支非模組對應檔。 | ⭐⭐⭐⭐☆ |

### 2.2 `sub_08` 收官實作推進軌道對比（出口 ① 升級選項）

| 推進軌道 | 執行方式 | 優點 (Pros) | 缺點 / 成本 (Cons) | 適用度評級 |
| :--- | :--- | :--- | :--- | :---: |
| **軌道 1（推薦）：原地升級 Full Track + 實戰 `/auto` 精實模式 (`P01~P05_auto.md`)** | 拍板出口 ① 後，於 `sub_08` 直接觸發剛在 `sub_07` 完成重構的 `/auto` 精實模式，自動一次產出 `P01_*_auto.md` ~ `P05_task_auto.md`、執行 13 $\to$ 6 測試純化、根目錄 `./scratch` & `./scripts` 清理與文檔對齊，直達 `P06` Checkpoint 與 `P07` 結案。 | • **100% 符合 `> 100` 行重構之 Full Track 守門**（整併 7 支測試檔涉及數百行遷移）。<br>• **最佳實戰 Dogfooding**：直接在最後一個子計畫真實演練 `sub_07` 新落地的 `/auto` 內聯骨架、`1-Write-Per-File` 與 `P01~P05_auto.md` 雙軌驗證鏈！ | • 會於 `sub_08` 目錄生成 `P01~P05_auto.md`、`P06`、`P07` 標準檔案（但因採 `sub_07` 精實模式，Context 消耗極低）。 | ⭐⭐⭐⭐⭐<br>**(強烈推薦)** |
| **軌道 2：維持 Research + 直接於結案前修正** | 不升級 Full Track，破例於調研模式後直接修改代碼結案。 | • 少寫 `P01~P07` 規格檔。 | • **違反 SOP 分流紀律**（涉及刪除 7 支測試檔與根目錄檔案，遠超 Fast Track 100 行上限與 Research 唯讀邊界），且錯失實戰驗收 `/auto` 新機制的機會。 | ⭐⭐☆☆☆ |

---

## 3. 架構設計與驗證 (Architecture & PoC)

### 3.1 `agents-workflow/tests/` 六維度體檢與 13 $\to$ 6 子系統 1:1 歸戶映射表 (`testing-sop` Step 2 Gate)

| # | 現有測試檔 (13 支) | 現有方法數 | 檢出之 `T-01` ~ `T-06` 病灶明細 | 純化處置與遷移目標（方案 A：6 支子系統檔） |
| :-: | :--- | :---: | :--- | :--- |
| 1 | `test_compiler.py` | 20 | • **`T-01`**：`test_ft_11_on_reload_hook_triggers_release_all` (L258) 僅呼叫 `hook_mod.on_reload(None)`，漏寫 `mock_rel.assert_called_once()`。<br>• **`T-03`**：`test_sub_08_session_analysis_skill_retired` (L484-502) 為已除役技能之歷史墓碑測試。 | **【保留主檔 `test_compiler.py`】**<br>• 補齊 `mock_rel.assert_called_once()`，刪除 `session_analysis` 墓碑。<br>• 吸收 `test_plans_model_record.py` 中屬編譯/Skill 資產契約之測試（`test_ft_03`~`test_ft_12`）。 |
| 2 | `test_publisher.py` | 18 | • **`T-01`**：L68, L97, L189 以 `if uri and uri.exists(...):` 條件包覆核心斷言，缺檔時會靜默通過。<br>• **`T-03`**：`test_ft_12_manifest_clean_of_watchdog` (L364-372) 斷言 `manifest.json` 無 `watchdog` 之歷史墓碑。 | **【保留主檔 `test_publisher.py`】**<br>• 移除 `if uri.exists` 寬容保護改為剛性 `self.assertTrue`；移除 `watchdog` 墓碑。<br>• 吸收下方 `#3`, `#4`, `#5` 三支發布器碎片測試檔。 |
| 3 | `test_jit_release.py` | 5 | • **`T-02`**：局部功能碎片檔。<br>• **`T-03`**：`test_agents_workflow_cli_adhoc_removal` (L61-67) 靜態讀 `cli.py` 斷言無 `ensure_jit_release()` 墓碑。 | **【物理刪除 (`git rm`)】**<br>• 刪除 `T-03` 墓碑後，將其餘 4 個 JIT 雜湊變更偵測測試無損併入 **`test_publisher.py`**。 |
| 4 | `test_manifest_placement.py` | 5 | • **`T-02`**：局部功能碎片檔。<br>• **`T-05`**：修改 `ReleaseTargetManager.save_tier_targets` 未於 `tearDown` 復原。 | **【物理刪除 (`git rm`)】**<br>• 5 個清單路徑隔離測試無損併入 **`test_publisher.py`** 並補齊 `tearDown` 狀態復原。 |
| 5 | `test_publisher_cross_platform.py` | 4 | • **`T-02`**：單次修復計畫碎片檔。<br>• **`T-05`**：L47 `tempfile.mkdtemp()` 未實作 `tearDown` 刪除。 | **【物理刪除 (`git rm`)】**<br>• 4 個 LF 正規化與 `cache://` 隔離測試無損併入 **`test_publisher.py`** 並統一清理暫存目錄。 |
| 6 | `test_initializer.py` | 7 | • **`T-01`**：L78 `if os.path.isfile(tpl_path):` 寬容條件分支，且漏檢 `paths.roadmap` 為 `"!undefined"`。 | **【保留主檔 `test_initializer.py`】**<br>• 移除 `if` 寬容條件改為剛性斷言，補齊 `paths.roadmap` `"!undefined"` 檢核。 |
| 7 | `test_targets.py` | 7 | • 無病灶（僅兩個不同類別內方法同名 `test_ft_05_*`）。 | **【保留主檔 `test_targets.py`】**<br>• 微調方法名使其語意更清晰。 |
| 8 | `test_roadmap.py` | 5 | • **`T-02`**：與 `test_plans_toolchain.py` (L554-756) 之 5 個 `TodoManager`/`RoadmapManager` 測試跨檔分裂。<br>• **`T-05`**：L33 `tempfile.mkdtemp()` 未於 `tearDown` 清理。 | **【保留主檔 `test_roadmap.py`】**<br>• 補齊 `tearDown` `shutil.rmtree`。<br>• 吸收 `test_plans_toolchain.py` 中 5 個 `TodoManager`/`RoadmapManager` 測試（合流為完整儲備工具鏈測試集）。 |
| 9 | `test_plans_toolchain.py` | 19 | • **`T-02`**：混入 5 個 `roadmap/todo` 測試，且與 `#10`, `#11`, `#12` 分裂。 | **【保留主檔 `test_plans_toolchain.py`】**<br>• 移出 5 個 `roadmap/todo` 測試至 `test_roadmap.py`。<br>• 吸收下方 `#10`, `#11` 及 `#12` 之 Plans 工具鏈測試，並統一 `tearDown` 沙盒清理。 |
| 10 | `test_plans_status.py` | 9 | • **`T-02`**：子組件碎片檔。<br>• **`T-03`**：`test_ft_09_verifier_deadcode_clean` (L371-381) 斷言 `not hasattr(PlanVerifier, "VALID_CHANGELOG_TYPES")` 歷史墓碑。<br>• **`T-05`**：L37 `tempfile.mkdtemp()` 未於 `tearDown` 清理。 | **【物理刪除 (`git rm`)】**<br>• 刪除 `T-03` 墓碑後，其餘 8 個狀態推導與時序測試無損併入 **`test_plans_toolchain.py`**。 |
| 11 | `test_plans_aci_toolchain.py` | 14 | • **`T-02`**：`sub_01` 計畫名碎片檔。<br>• **`T-05`**：L31 `tempfile.mkdtemp()` 未於 `tearDown` 清理。 | **【物理刪除 (`git rm`)】**<br>• 14 個 `--resume`、`--phase`、追溯差集與 `--log` 測試無損併入 **`test_plans_toolchain.py`**。 |
| 12 | `test_plans_model_record.py` | 13 | • **`T-02`**：歷史計畫名碎片檔。<br>• **`T-03`**：L251-256 重複斷言 `session-analysis` 已移除。<br>• **`T-05`**：L35 `tempfile.mkdtemp()` 未於 `tearDown` 清理。 | **【物理刪除 (`git rm`)】**<br>• `test_ft_01`, `test_ft_02`, `test_ft_13_sub07`（Plans 驗證器與 `_auto.md` 雙軌解析）併入 **`test_plans_toolchain.py`**。<br>• 其餘內建 Skills/Templates/Tokens 合規測試併入 **`test_compiler.py`**（移除 `session-analysis` 墓碑斷言）。 |
| 13 | `test_auto_workflow.py` | 4 | • **`T-01` & `T-03`**：標註已廢棄之 `@require(Requirement.WORKFLOW)` 導致長期被靜默 Skip，且內部斷言早已廢除之 `WORKFLOW_AUTO` Token（現行 `/auto` 已由 `test_ft_13_sub07` 完整驗證）。 | **【物理刪除 (`git rm`)】**<br>• 直接淘汰刪除此殭屍測試檔。 |

---

### 3.2 `sub_01` ~ `sub_07` 二次驗收與 Roadmap 儲備閉環核對表

| 子計畫 | 狀態 | 消費之 Roadmap 儲備檔 (`Consume-on-Promote` 物理遷入驗證) | 實機驗收狀態 |
| :--- | :---: | :--- | :---: |
| **`sub_01_python_aci_toolchain`** | `Completed` | [sub_01/roadmap.md](../sub_01_python_aci_toolchain/roadmap.md) *(原 `agents_workflow_python_aci_toolchain_roadmap.md`)* | ✅ 已遷入結案 |
| **`sub_02_roadmap_and_todo_refactoring`** | `Completed` | [sub_02/roadmap.md](../sub_02_roadmap_and_todo_refactoring/roadmap.md) *(原 `roadmap_and_todo_dual_tier_refactoring_roadmap.md`)* | ✅ 已遷入結案 |
| **`sub_03_testing_sop_and_subagent_isolation`** | `Completed` | [sub_03/roadmap.md](../sub_03_testing_sop_and_subagent_isolation/roadmap.md) *(2 份合流：`testing_sop_and_phase06_hardening` + `subagent_task_isolation_evaluation`)* | ✅ 已遷入結案 |
| **`sub_04_onboarding_and_config_coaching`** | `Completed` | [sub_04/roadmap.md](../sub_04_onboarding_and_config_coaching/roadmap.md) *(2 份合流：`project_role_and_how_to_config_yscb` + `how_to_yscb_interactive_coaching`)* | ✅ 已遷入結案 |
| **`sub_05_skill_creator_extension_workflow`** | `Completed` | [sub_05/roadmap.md](../sub_05_skill_creator_extension_workflow/roadmap.md) *(原 `skill_creator_layer2_extension_roadmap.md`)* | ✅ 已遷入結案 |
| **`sub_06_cli_guide_purification`** | `Completed` | 無（衍生敏捷優化：`yscb-cli-guide` 拔除動態指令大表 + `-h` 按需自省） | ✅ 已驗證結案 |
| **`sub_07_auto_context_lean_optimization`** | `Completed` | 無（衍生敏捷優化：`/auto` 內聯骨架免讀 11 檔 + `1-Write-Per-File` + `_auto.md` 雙軌相容） | ✅ 已驗證結案 |

> **儲備庫純淨度核驗**：`plans/roadmap/` 下原屬本主計畫範疇之 **7 份**路線圖已 100% 透過 `Consume-on-Promote` 物理遷入 `sub_01` ~ `sub_05`；目前 `plans/roadmap/` 僅存 3 份未啟動之遠期獨立儲備（`multi_platform_release_targets_expansion_roadmap.md`、`release_binary_storage_optimization.md`、`skill_release_prefix_isolation.md`），零殭屍殘留。

---

### 3.3 工作區歷史遺留清理與三層文檔修正清單

1. **工作區根目錄歷史遺留物理刪除 (`git rm -r`)**：
   - `scratch/server_test.log`（及空目錄 `scratch/`）：2026-09-12 Commit `ee02b201` 誤提交之 0-byte 臨時空檔。
   - `scripts/scan_native_io.py`（及空目錄 `scripts/`）：2026-09-06 Commit `b563f8d4` 一次性 AST 盤點腳本，全庫 0 引用。
2. **三層文檔最終對齊修正點**：
   - **`docs/agents-workflow/FACTORY_PIPELINE.md`（Lines 90-91, 105）**：將過時之「`storage://agents-workflow/release_manifest.json`（受 Git 追蹤）」更新為現行 `cache://agents-workflow/project_release_manifest.json`（本地快取隔離、不入 Git 追蹤，對齊 `[DN-AW-09]` 與 `README.md`），並更新 `last_updated: "2026-10-25"`。
   - **`ys_codebase/source/agents-workflow/README.md`（Lines 126, 138-140, 154-160）**：
     - Line 126：同步 `sub_06` 之「技能內建指令免查直跑 (`Skill-Vetted Fast Pass`) + 非常規指令 `-h` 按需自省 (`JIT -h Inspection`)」雙軌機制。
     - Lines 138-140：補齊 `plan status --resume`、`plan verify --phase <P0X> --log "<摘要>" --model "<ModelName>"` 與 `_auto.md` 雙軌相容說明，移除不存在之 `plan check` 範例。
     - Lines 154-160：將過時之 `--status=Candidate` 修正為 `--status=Ready`（對齊 `[Backlog|Proposed|Ready|Deferred]`），並補齊 `roadmap promote` 與 `todo add/list/promote` 速查指令。

---

## 4. 調研結論與落地建議 (Conclusion & Recommendation)

- **推薦落地策略**：
  1. **採納「方案 A（13 檔 $\to$ 6 支子系統測試檔 1:1 歸戶）」**：物理刪除 7 支碎片與殭屍測試檔（`test_auto_workflow.py`、`test_jit_release.py`、`test_manifest_placement.py`、`test_publisher_cross_platform.py`、`test_plans_status.py`、`test_plans_aci_toolchain.py`、`test_plans_model_record.py`），徹底消除 `T-01`、`T-02`、`T-03`、`T-05` 病灶。
  2. **採納「出口 ① + 軌道 1（原地升級 Full Track 並以 `/auto` 精實模式推進）」**：確認本報告與上方 13 $\to$ 6 測試歸戶映射表後，將 `R01` 標記為 `Concluded`，並直接以 `/auto` 連續推進 `sub_08`（實戰驗證 `P01~P05_auto.md` 生成、測試純化、根目錄 `./scratch` & `./scripts` 清理、文檔同步與全生態系 5 大模組 `dev check --all` / `dev test --all -q` 終極驗收）。
- **後續行動與 P00 銜接**：等待開發者確認 `3.1` 測試集歸戶映射表與流轉出口。

