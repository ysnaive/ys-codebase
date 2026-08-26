# 計畫變更紀錄 (Changelog)

> 功能名稱：Dev 模組發布與驗證工具鏈重構 (Dev Release & Verification Toolchain Refactor)  
> 建立日期：2026-08-26  
> 所屬主計畫：[core 與 dev 模組功能打磨 (2026_08_26_1747_core_dev_refinement)](../umbrella_overview.md)  
> 狀態：Draft  
> 模板版本：v1.1  

---

> 按時間倒序排列。每條記錄包含日期時間、類型標籤、摘要。

## 變更紀錄

| 日期時間 | 類型 | 摘要 |
| :--- | :---: | :--- |
| 2026-08-26 21:18 | `PHASE` | 產出 `P07_walkthrough.md`，完成 4 份知識庫文檔 (README, architecture, user_guide, release_governance) 1:1 交付驗收與 `CHANGELOG.md` 追加發布摘要；Dogfooding 四步閉環流水線執行完畢，計畫正式結案 (狀態：`Completed`) |
| 2026-08-26 21:16 | `PHASE` | 開發者指示免測通過，`P06_test_plan.md` 狀態標記為 `Passed` |
| 2026-08-26 21:12 | `PHASE` | Phase 6 自動化測試 100% Passed (FT-01~08, ET-01~07 15/15 + RT-01 109/109)；日誌回填至 `P06_test_plan.md`，進入 UX Checkpoint 等待關卡 |
| 2026-08-26 21:04 | `PHASE` | 完成 Phase 5 程式碼實作 (TASK-01~05 100% 完成，狀態：`Completed`)；單元與整合測試 (15/15) 及全模組端到端沙盒測試 (109/109) 100% 通過 |
| 2026-08-26 20:59 | `PHASE` | Phase 4 實作計畫經開發者確認定稿 (狀態：`Confirmed`)；啟動 Phase 5 依序程式碼實作 (狀態：`Executing`) |
| 2026-08-26 20:51 | `PHASE` | 產出 `P04_implementation_plan.md` ([P04:DR-01~02])，完成文檔衝擊預排、架構靈魂拷問與 TASK-01~06 任務拆解；同步將 `P06_test_plan.md` 剛性定稿 (狀態：`Confirmed`) |
| 2026-08-26 20:51 | `PHASE` | Phase 3 API 規格書經開發者確認定稿 (狀態：`Confirmed`) |
| 2026-08-26 20:50 | `PHASE` | 產出 `P03_api_spec.md`，定義 Releaser/Builder/Tester 完整介面簽名、3-Gate 例外型別與 5 層實作依賴拓撲 |
| 2026-08-26 20:50 | `PHASE` | Phase 2 架構設計經開發者確認定稿 (狀態：`Confirmed`) |
| 2026-08-26 20:45 | `PHASE` | 產出 `P02_architecture_plan.md` ([P02:DR-01~04])，並依據 Test-First 原則同步初始化 `P06_test_plan.md` (Draft，映射 FT-01~08, ET-01~07, RT-01, UX-01) |
| 2026-08-26 20:44 | `PHASE` | Phase 1 需求規格經開發者確認定稿 (狀態：`Confirmed`) |
| 2026-08-26 20:38 | `PHASE` | Phase 0 需求討論經開發者確認定稿 (狀態：`Confirmed`)；啟動 Level 1 Full Track，產出 `P01_requirements_spec.md` (FR-01~08, EC-01~08, NFR-01~03) |
| 2026-08-26 20:35 | `DECISION` | 精確更正發布演算法與工具鏈：DR-02 規範同三元組時序滑動窗口至多保留 3 份 Revision、跨三元組升級舊版收斂至 1 份 Revision；DR-09 更正 release-git 依序執行 test ➔ release-check ➔ release ➔ 本地 git commit/tag ([P00:DR-02], [P00:DR-09]) |
| 2026-08-26 20:28 | `DECISION` | 確立全新 Release 工具鏈架構：新增獨立 `bump-*` 版本遞增 ([P00:DR-07])、`release-check` 發布就緒預檢 ([P00:DR-08]) 與 `release-git` 順序驗證提交流水線 (禁 push) ([P00:DR-09]) |
| 2026-08-26 20:19 | `RESEARCH` | 產出 R02 專題調研與架構設計報告：`R02_release_toolchain_support.md`，定義 3-Gate 發布守門流水線、Releaser/Builder 職責分工與多模組批次發布依賴拓撲排序 ([P00:DR-06]) |
| 2026-08-26 19:19 | `DECISION` | 確立 DR-05 發布品質守門閘門：dev release 強制校驗版本號不可回退、完整四元版本號不可與發布庫已有版本相同 ([P00:DR-05]) |
| 2026-08-26 19:16 | `RESEARCH` | 產出 R01 專題調研與重構收斂報告：`R01_dev_toolchain_refactor.md`，全量收斂需清理廢除之舊流水線代碼與三大核心重構規範 |
| 2026-08-26 19:15 | `DECISION` | 確立 DR-04 索引與匹配規範：發布索引以磁碟存在之 zip 為唯一真相來源自動排除被刪除的 revision，並源碼驗證確認三段式安裝匹配對第四段尾號不敏感 ([P00:DR-04]) |
| 2026-08-26 19:13 | `DECISION` | 深化 DR-02 發布治理規範：dev release 產物端不清空全目錄，僅移除/覆蓋同三元版本號單檔產物，禁止刪除歷史發布包並增量維護 index.json ([P00:DR-02]) |
| 2026-08-26 19:11 | `DECISION` | 確立三大指令重構決策：build 自動清理 ([P00:DR-01])、release 純粹化對標 build ([P00:DR-02])、test 流水線化前置 build 支援 --no-build ([P00:DR-03]) |
| 2026-08-26 19:02 | `PHASE` | 開立 sub_02 子計畫目錄，伴隨建立 P00 與本變更日誌，進入 Phase 0 語意需求討論 (狀態：`Discussing`) |
