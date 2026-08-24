# 程式碼實作與任務清單 (Implementation Tasks)

> 功能名稱：測試框架生命週期與全隔離虛擬沙盒重構 (Testing Lifecycle & Virtual Sandbox Refactor)  
> 建立日期：2026-08-25  
> 所屬主計畫：[2026_08_23_2030_architecture_refactor](../umbrella_overview.md)  
> 依據 P04：[P04_implementation_plan.md](./P04_implementation_plan.md)  
> 狀態：Completed  
> 擴充項目：none  
> 模板版本：v1.4  

---

## 1. 任務執行進度清單 (Task Execution Checklist)

- [x] **TASK-01: `Requirement` 列舉與條件標籤更新**
  - [x] 於 `source/dev/dev/testing/requirement.py` 定義 `Requirement.LOGIC`, `Requirement.HOST_CLI`, `Requirement.NETWORK`
  - [x] 更新 `@require` 裝飾器附加 `__requirement__` 屬性供篩選
- [x] **TASK-02: `SandboxContext` 與 `SandboxProvisioner` (`op-mksb`) 實作**
  - [x] 建立 `source/dev/dev/testing/sandbox.py` (SandboxContext, SandboxProvisioner)
  - [x] 重構 `source/dev/dev/testing/case.py` 對接微型虛擬環境與 `SandboxProvisioner`
  - [x] 導出至 `source/dev/dev/testing/__init__.py`
- [x] **TASK-03: `core` 模組自治測試 Hook 實作**
  - [x] 建立 `source/core/scripts/hook.dev.py`
  - [x] 實作 `on_test_setup` (配置 `project_root: "../mock_downstream_project"`)
- [x] **TASK-04: `filter_suite` 遞迴過濾器與 `TestDiscovery` 強化 (`op-test`)**
  - [x] 於 `source/dev/dev/testing/runner.py` 實作遞迴 `filter_suite(suite, pattern, test_type)`
  - [x] 更新 `TestDiscovery.build_suite_for_module` 實施跨模組 `sys.path` 隔離與遞迴過濾
- [x] **TASK-05: `dev.tester` 三階路由整合與 `dev.builder` 打包保留規則**
  - [x] 於 `source/dev/dev/tester.py` 與 `scripts/cli.py` 實作 `op-mksb`, `op-test`, `test` 三階路由
  - [x] 於 `source/dev/dev/builder.py` 確保打包時保留 `scripts/hook.dev.py`
  - [x] 於 `yscb.py` 支援 modules 找不到時回退至 source/ 支援沙盒與即改即測
- [x] **TASK-06: 持久化測試套件擴充與全量 100% 驗證**
  - [x] 建立 `source/dev/tests/test_sandbox.py` 覆蓋 FT-01 ~ FT-06、ET-01 ~ ET-03
  - [x] 執行全量測試驗證 47/47 (100% Passed) 綠燈與 RT-01 回歸守門

---

## 2. 實作偏差紀錄表 (Implementation Deviation Log)

| 偏差編號 | 偏差等級 (Critical / Major / Minor) | 影響模組 / 檔案 | 偏離內容與原因說明 | 處置方式與回報結果 |
| :--- | :---: | :--- | :--- | :--- |
| **DEV-01** | Major | `yscb.py`<br/>`dev.testing.sandbox` | 糾正 `yscb.py` 嚴禁回退至 `source/` 派發指令之微內核鐵律。`yscb.py` 僅能調度 `modules/`。 | 1. 移除 `yscb.py` 中 `source/` 回退邏輯。<br/>2. `SandboxProvisioner` 在建置沙盒時完整複製父層已安裝之 `modules/` 並繼承 `installed_modules` 配置。<br/>3. 全量 48 項測試 100% 綠燈通過。 |
