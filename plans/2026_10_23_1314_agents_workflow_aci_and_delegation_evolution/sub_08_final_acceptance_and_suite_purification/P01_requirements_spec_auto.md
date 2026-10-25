# 功能需求規格書 (Requirements Specification)

> 功能名稱：全主計畫二次驗收、測試集子系統 1:1 純化、歷史目錄清理與三層文檔收官 (sub_08_final_acceptance_and_suite_purification)  
> 建立日期：2026-10-25  
> 所屬主計畫：2026_10_23_1314_agents_workflow_aci_and_delegation_evolution  
> 狀態：Confirmed  
> 模型：Gemini 3.8 Flash (Medium)  

---

## 1. 功能需求清單 (Functional Requirements)

| 需求 ID | 來源追溯 | 需求名稱 | 核心行為與交付目標 |
| :--- | :--- | :--- | :--- |
| **FR-01** | `P00 §1` / `R01 §3.1` | **測試集 13 檔收斂至 6 大子系統測試檔** | 將 `ys_codebase/source/agents-workflow/tests/` 現有 13 支測試檔無損整併為 6 支與生產子系統 1:1 對齊之測試檔（`test_compiler.py`, `test_publisher.py`, `test_initializer.py`, `test_targets.py`, `test_roadmap.py`, `test_plans_toolchain.py`），物理刪除 7 支碎片/殭屍檔。 |
| **FR-02** | `P00 §1` / `R01 §3.1` | **六大測試病灶 (`T-01` ~ `T-06`) 徹底純化** | 清理 1 支因廢棄標籤被靜默跳過之死測試檔（`test_auto_workflow.py`）；清除 4 處 `T-03` 墓碑斷言；重寫 5 處 `T-01` 條件放行或漏斷言；全面補齊 6 處 `T-05` `tempfile.mkdtemp()` 之 `tearDown` `shutil.rmtree`。 |
| **FR-03** | `P00 §1` / `R01 §3.3` | **根目錄歷史遺留目錄與檔案清理** | 物理刪除誤納入 Git 追蹤之 `scratch/server_test.log`（及空目錄 `scratch/`）與 `scripts/scan_native_io.py`（及空目錄 `scripts/`），使根目錄 100% 潔淨。 |
| **FR-04** | `P00 §1` / `R01 §3.3` | **三層文檔最終對齊修正** | 修正 `docs/agents-workflow/FACTORY_PIPELINE.md` 過時之 `storage://` 敘述為 `cache://`；同步 `ys_codebase/source/agents-workflow/README.md` 中 `sub_06` 雙軌 CLI、`sub_07` `_auto.md` 雙軌相容及最新有效 Roadmap 狀態。 |
| **FR-05** | `P00 §1` / `R01 §3.2` | **全主計畫二次驗收與 7 份 Roadmap 閉環核對** | 實機執行全生態系合規檢查與回歸跑測，驗證 `sub_01` ~ `sub_07` 交付物端到端協同正常，核對 7 份已消費 Roadmap 物理遷入閉環無殭屍殘留。 |

---

## 2. 邊界與異常情況 (Edge Cases & Failure Modes)

| 邊界 ID | 關聯需求 | 情境描述 | 預期防護與攔截行為 |
| :--- | :--- | :--- | :--- |
| **EC-01** | `FR-01` | 跨檔搬遷測試時命名碰撞 | 檢查搬遷進 `test_publisher.py`、`test_plans_toolchain.py`、`test_compiler.py` 的測試方法名稱，以語意清楚的 `test_` 前綴命名，嚴禁方法名碰撞覆蓋。 |
| **EC-02** | `FR-02` | `tearDown` 沙盒清理遇到未初始化變數 | 在 `tearDown` 中使用 `getattr(self, "temp_dir", None)` 或 `hasattr` 防禦判斷，確保若 `setUp` 前期崩潰時 `tearDown` 不會衍生二度例外。 |
| **EC-03** | `FR-03` | 刪除 `scratch` 與 `scripts` 後被忽略規則或工具鏈自癒復活 | 確認 `compiler.py` 與 `publisher.py` 不會在編譯發布時重新建立這兩個非目標目錄；`git rm -r` 後驗證 `git status` 乾淨。 |
| **EC-04** | `FR-05` | 測試純化後出現漏測或總測試數異常暴跌 | 嚴格比對整併前後的有效測試案例，除確認淘汰的死測試（`test_auto_workflow` 4 個）與墓碑斷言外，其餘有效業務邏輯 100% 保留無損。 |

---

## 3. 非功能需求 (Non-Functional Requirements)

| 指標 ID | 維度 | 目標值與約束條件 |
| :--- | :--- | :--- |
| **NFR-01** | **測試品質與純化率** | 測試檔由 13 支降至 6 支（收斂率 `-53.8%`），100% 符合 `testing-sop` 六大鐵律（0 碎片檔、0 歷史墓碑、0 沙盒殘留、0 寬容條件放行）。 |
| **NFR-02** | **全生態系回歸全綠** | `dev check agents-workflow` PASSED、`dev test agents-workflow -q` 100% 通過（0 Skip / 0 Fail），全生態系 5 模組端到端無損。 |
| **NFR-03** | **Git 工作區純淨度** | `scratch/` 與 `scripts/` 徹底移除，`git status --short` 零殘留。 |

---

## 4. 知識庫與踩坑紀錄查閱 (Known Gotchas & CAUTIONs)

- **[DN-AW-09] 來源換行符 LF 正規化與物化清單 cache:// 本地隔離**：更新 `FACTORY_PIPELINE.md` 時務必指明 `project_release_manifest.json` 存放於 `cache://` 空間，嚴禁寫入 `storage://` 入 Git。
- **[DN-AW-15] /auto 內聯輕量骨架與 _auto.md 命名溯源協議**：更新隨包 `README.md` 時須正確揭露 `_auto.md` 雙軌相容機制與單次 `plan verify` 規範。
- **testing-sop 鐵律 4（零歷史墓碑）**：刪除 `hasattr` 或 `assertNotIn("ensure_jit_release", ...)` 等墓碑測試時，切勿因捨不得代碼而保留。

