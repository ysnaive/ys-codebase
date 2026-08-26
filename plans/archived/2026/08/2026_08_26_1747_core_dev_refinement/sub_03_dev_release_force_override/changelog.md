# 計畫內部變更日誌 (Dev Plan Changelog)

> 功能名稱：Dev 模組發布強制覆蓋模式 (Dev Release Force Override Support)  
> 建立日期：2026-08-26  
> 所屬主計畫：[core 與 dev 核心能力演進與完善 (2026_08_26_1747_core_dev_refinement)](../umbrella_overview.md)  
> 狀態：Completed  
> 模板版本：v1.2  

---

## 1. 變更紀錄表 (Changelog Matrix)

| 日期時間 | 類型 | 摘要 |
| :--- | :---: | :--- |
| 2026-08-26 22:17 | `PHASE` | 完成 FT-3 結案審查，更新知識庫文檔 (`README.md`, `user_guide.md`)，追加專案全域 `CHANGELOG.md`，計畫狀態標記為 `Completed` |
| 2026-08-26 22:16 | `TEST` | 實機測試 100% 通過：`dev test dev` 29/29 Passed，全系統沙盒 `dev test --all` 113/113 Passed |
| 2026-08-26 22:10 | `CODE` | 完成 TASK-01~03 程式碼實作：`Releaser` 支援 force 參數與智慧感應、CLI 支援 `--force` / `-f`、單元測試擴充 |
| 2026-08-26 22:09 | `PHASE` | 產出 `fast_track_plan.md` (Draft，包含 FT-1 變更規劃、TASK-01~03 拆解與 FT/ET 測試規劃) |
| 2026-08-26 22:09 | `PHASE` | Phase 0 語意需求經開發者確認定稿，`P00_semantic_requirements.md` 狀態更新為 `Confirmed`，選定 Level 0 (Fast Track) 分流 |
| 2026-08-26 22:07 | `DECISION` | 依開發者指示追加 `dev release-git` 智慧感應已發布版本邏輯：未發布正常打包，已發布且無 force 自動略過打包直接進行 Git Commit/Tag，有 force 則強制重新打包覆蓋 ([P00:DR-03]) |
| 2026-08-26 22:05 | `PHASE` | 開立計畫目錄，伴隨初始化建立 `P00_semantic_requirements.md` (Draft) 與 `changelog.md` |
| 2026-08-26 22:05 | `DECISION` | 定義 Gate 2/Gate 3 在 `--force` 模式下的判定邏輯：允許同版本原地覆蓋更新，防禦小於歷史舊版本之回退 ([P00:DR-01]) |
| 2026-08-26 22:05 | `DECISION` | 定義 CLI 參數與傳遞鏈貫穿清單 (`release`, `release-check`, `release-git`) ([P00:DR-02]) |
