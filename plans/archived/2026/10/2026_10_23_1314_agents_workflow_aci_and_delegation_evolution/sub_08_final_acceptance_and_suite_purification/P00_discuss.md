# 需求討論說明書 (Semantic Requirements Discovery)

> 功能名稱：全主計畫二次驗收、測試集子系統 1:1 純化、歷史目錄清理與三層文檔收官調研 (sub_08_final_acceptance_and_suite_purification)  
> 建立日期：2026-10-25  
> 所屬主計畫：2026_10_23_1314_agents_workflow_aci_and_delegation_evolution  
> 狀態：Confirmed  
> 模型：Gemini 4 Argon (High)  

> 計畫類型：Full Track  
> 模板版本：v1.2  

---

## 1. 使用者原始需求與意圖 (User Intent)

- **原始陳述**：將 `./scratch` 與 `./scripts` 納入 `sub_08` 收官清理，並正式進入收官驗收階段；暫時不直接開立 Full Track，先以調研模式（Research Plan）進行全面體檢與評估。
- **核心目標**：
  1. **存量測試集六維度體檢與子系統 1:1 歸戶規劃 (`testing-sop` 情境 B Step 1~2)**：全面掃描 `ys_codebase/source/agents-workflow/tests/` 現有 13 支測試檔（119 個測試方法），檢出 `T-01`~`T-06` 病灶（碎片檔、因廢棄標籤被 Skip 之死測試、歷史墓碑斷言、條件包覆寬容斷言、`tempfile.mkdtemp` 漏清理），產出 1:1 子系統歸戶映射表供開發者拍板。
  2. **`sub_01` ~ `sub_07` 二次驗收與 Roadmap `Consume-on-Promote` 閉環核驗**：盤點本主計畫各子計畫交付成果與已消費之 Roadmap 儲備檔案是否 100% 完成物理遷入閉環且無殘留。
  3. **工作區歷史遺留清理與三層文檔最終對齊盤點**：確認根目錄 `./scratch`（`scratch/server_test.log`）與 `./scripts`（`scripts/scan_native_io.py`）之清理方案，並排查 `docs/agents-workflow/` 與 `ys_codebase/source/agents-workflow/README.md` 是否存在未同步之過時描述。
  4. **收官實作軌道選型評估**：評估確認體檢映射表後之最佳落地執行軌道（例如升級為 Full Track 並實戰 Dogfooding 剛於 `sub_07` 落地之 `/auto` 精實模式與 `PXX_YYYY_auto.md` 雙軌工具鏈）。
- **邊界排除 (Explicitly Excluded)**：
  - 本調研階段（`P00` + `R01`）純屬唯讀體檢與方案定錨，未經開發者確認 `R01` 歸戶映射表與出口前，不提前刪除或修改測試檔與生產檔案。
- **架構影響範圍**：
  - `ys_codebase/source/agents-workflow/tests/`（13 支測試檔收斂至 6 支子系統測試檔）
  - `scratch/server_test.log`、`scripts/scan_native_io.py`（根目錄歷史遺留清理）
  - `docs/agents-workflow/FACTORY_PIPELINE.md`、`ys_codebase/source/agents-workflow/README.md`（三層文檔同步）

---

## 2. 核心討論與決策紀錄 (Discussion & Decisions)

- **[P00:DR-01] 先行採用 Research 模式完成收官全景盤點與 `testing-sop` Step 2 映射表守門**：
  - 鑑於 `sub_08` 涉及刪除多支歷史碎片測試檔、清理根目錄 Git 追蹤遺留目錄及跨 7 個子計畫之最終驗收，先以 Research 模式產出 `R01_final_acceptance_and_suite_purification_audit.md`，一次性呈現「13 $\to$ 6 測試檔歸戶映射表」、「六大測試病灶明細」、「文檔與工作區清理清單」及「後續實作軌道方案對比」，待開發者拍板後再無痛升級執行。

---

## 3. 開放議題與確認紀錄

- 見 `R01_final_acceptance_and_suite_purification_audit.md` 之候選方案與出口裁決項。

