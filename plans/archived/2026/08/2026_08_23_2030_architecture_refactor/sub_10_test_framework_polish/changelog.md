# sub_10_test_framework_polish 變更日誌 (Sub-Plan Changelog)

本檔案記錄 `sub_10_test_framework_polish` 子計畫內部之微觀進度、Phase 轉換與關鍵決策。

---

## 變更紀錄表

| 時間 (UTC+8) | 事件 Token | 變更摘要與說明 |
| :--- | :---: | :--- |
| 2026-08-25 00:56 | `SUBPLAN_INIT` | 開立 `sub_10_test_framework_polish` 子計畫目錄，雙星伴隨初始化 P00 與 changelog.md |
| 2026-08-25 00:57 | `PHASE0_RESEARCH` | 產出 R01 測試框架生命週期調用流調研報告 (`R01_testing_lifecycle_flow.md`) |
| 2026-08-25 01:50 | `P00_CONFIRMED` | 確立完全對標虛擬沙盒、hook.dev.py 自治前置、雙層套件源等 5 項決策，定稿 P00 與 R01 |
| 2026-08-25 01:51 | `P01_CREATED` | 產出 P01_requirements_spec.md，完成 FR-01~06、EC-01~05、NFR-01~03 轉譯 |
| 2026-08-25 01:54 | `P01_CONFIRMED` | 排除 dogfooding_pipeline_ext，P01 正式定稿 (Confirmed) |
| 2026-08-25 01:55 | `P02_CREATED` | 產出 P02_architecture_plan.md，完成微型虛擬環境模組架構與循序圖設計 |
| 2026-08-25 01:55 | `P06_INIT` | Test-First 初始化 P06_test_plan.md，建立 FT-01~06、ET-01~03、RT-01 測試清冊 |
| 2026-08-25 01:57 | `P02_REFINED` | 確立源碼進沙盒後依賴 __file__ 天然自定位，移除 YSCB_ROOT 侵入式修改，core.uri 保持純淨 0 修改 |
| 2026-08-25 02:03 | `P02_CONFIRMED` | 確立 op-mksb、op-test、test 三階解耦，P02 正式定稿 (Confirmed) |
| 2026-08-25 02:04 | `P03_CREATED` | 產出 P03_api_spec.md，定義 SandboxProvisioner, SandboxContext, filter_suite 與 5 步實作拓撲 |
| 2026-08-25 02:05 | `P03_CONFIRMED` | 移除 Requirement.SANDBOX，P03 正式定稿 (Confirmed) |
| 2026-08-25 02:06 | `P04_CREATED` | 產出 P04_implementation_plan.md，完成靈魂拷問、知識庫衝擊預排與 6 項 TASK 定稿 |
| 2026-08-25 02:06 | `P06_CONFIRMED` | Test-First 剛性定稿 P06_test_plan.md (FT-01~06, ET-01~03, RT-01) |
| 2026-08-25 02:10 | `P05_COMPLETED` | 完成 TASK-01~06 程式碼實作，落實 SandboxProvisioner、hook.dev.py、filter_suite 與三階 CLI |
| 2026-08-25 02:10 | `P06_AUTO_PASSED` | 實機自動化測試驗證：FT-01~06, ET-01~03, RT-01 全數 100% 通過 (47/47 綠燈) |
| 2026-08-25 02:25 | `P05_REFINED_DEV01`| 移除 yscb.py 的 source 回退邏輯，確立 yscb 僅調度 modules/；SandboxProvisioner 完整複製父層已安裝 modules/ 與配置，全量測試 48/48 綠燈 |
| 2026-08-25 02:28 | `P07_COMPLETED` | 產出 P07_walkthrough.md，完成知識庫 1:1 交付驗收、全域 CHANGELOG 更新與結案 |
