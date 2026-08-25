# 實作計畫與最終審查 (Implementation Plan & Review)

> 功能名稱：框架骨架最終打磨與 CLI UX 體驗優化 (Framework Final Polish & CLI UX)  
> 建立日期：2026-08-25  
> 所屬主計畫：[2026_08_23_2030_architecture_refactor](../umbrella_overview.md)  
> 依據規格/API：[P01_requirements_spec.md](./P01_requirements_spec.md), [P02_architecture_plan.md](./P02_architecture_plan.md), [P03_api_spec.md](./P03_api_spec.md)  
> 狀態：Confirmed (Phase 4 已定稿)  
> 擴充項目：none  
> 模板版本：v1.4  

---

## 1. 交叉驗證檢查清單 (Cross-Validation Checklist)

- [x] 需求規格書中的每個 FR（FR-01~FR-04），在 API 規格書中有對應介面與簽名
- [x] 需求規格書中的每個 EC（EC-01~EC-03），在 API 規格書中有對應防禦與降級處置
- [x] 風險評估已完備，全模組保持 100% Python 標準庫零第三方依賴
- [x] 測試計畫 `P06_test_plan.md` 已全面覆蓋所有 FR/EC/NFR

---

## 2. 📚 知識庫文檔衝擊與交付規劃 (Documentation Impact Plan)

依據 7 大抽象知識維度投影，本計畫將於 Phase 7 交付以下知識庫更新：

| 維度 | 目標文件路徑 | 變更類型 | 規劃更新內容說明 |
| :---: | :--- | :---: | :--- |
| **維度 3** | `docs/dev/RELEASE_PIPELINE.md` | Modify | 更新 Pre-flight Gates 章節，移除 Gate 1 (Git Dirty 檢查)，說明本地純淨發布哲學。 |
| **維度 5** | `docs/dev/DESIGN_NOTES.md` | Modify | 追加 `[DN-06]`（本地發布流水線解耦 Git 乾淨限制之架構裁決）。 |
| **專案日誌** | `CHANGELOG.md` | Modify | 於根目錄追加 `sub_14` CLI UX 排版美化與發布守門精簡之變更紀錄。 |

---

## 3. 🎯 架構審查員靈魂拷問 (Stress Test Q&A)

> **Q (架構審查員)**：若第三方模組宣告的指令名稱與 Core 核心指令衝突，或在執行 `yscb.py --help` 時該模組尚未完成初始化，宿主如何防禦？  
> **A (Agent 回應)**：
> 1. **指令命名空間隔離**：宿主採用雙層路由機制，Core 指令由宿主直接調度，模組指令則一律強制帶有模組前綴（如 `python yscb.py <module> <subcmd>`），從語意與排版上徹底隔離，絕不發生覆蓋衝突。
> 2. **極致容錯探測**：若 `yscb_root` 尚未建立或模組損壞，`_get_installed_module_commands` 以 `try...except` 捕捉所有異常並優雅回傳空字典，`--help` 輸出 100% 永不拋出未捕獲例外崩潰。

---

## 4. 實作任務排程清冊 (Implementation Tasks)

| 任務編號 | 實作檔案 | 職責與變更內容 | 預計產出 |
| :--- | :--- | :--- | :--- |
| **TASK-01** | `source/dev/dev/releaser.py` | 移除 `check_preflight_gates` 中的 Gate 1 Git Dirty 檢查。 | 敏捷本地發布流水線 |
| **TASK-02** | `source/core/core/engine.py` | 實作 `act_get_installed_commands_summary` 供宿主快速讀取模組指令清單。 | 模組指令動態聚合 API |
| **TASK-03** | `yscb.py` | 實作層次化 `_print_global_help`、`_suggest_command` (difflib) 與未知指令智慧引導。 | 全域標準化 Help 與 UX |
| **TASK-04** | `source/core/tests/test_cli_help.py` | 建立 CLI Help 排版、子指令 Help 與拼寫建議之自動化測試。 | 自動化測試驗證套件 |
