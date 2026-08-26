# 實作任務清單 (Task Breakdown)

> 功能名稱：Dev 模組發布與驗證工具鏈重構 (Dev Release & Verification Toolchain Refactor)  
> 建立日期：2026-08-26  
> 所屬主計畫：[core 與 dev 模組功能打磨 (2026_08_26_1747_core_dev_refinement)](../umbrella_overview.md)  
> 狀態：Completed  
> 依據 P04：[P04_implementation_plan.md](./P04_implementation_plan.md)  
> 模板版本：v1.0  

---

## 1. 實作任務清單 (Task Breakdown)

- [x] **TASK-01**：重構 `source/dev/dev/builder.py`（預設 clean、純淨打包、3-Revision 滑動窗口保留與收斂淘汰演算法、`index.json` 實體 SSOT 同步）
- [x] **TASK-02**：升級 `source/dev/dev/tester.py`（端到端測試流水線支援自動前置 build 與 `--no-build` 旗標）
- [x] **TASK-03**：重構 `source/dev/dev/releaser.py`（自定義例外型別、`release_check` 3-Gate 校驗、`release_module`、`release_all` DAG 拓撲排序、`release_git` 4 步本地流水線）
- [x] **TASK-04**：重構 `source/dev/scripts/cli.py`（簡化 build/release、新增 `bump-*`、`release-check` 阻斷 `--all`、`release-git` 路由）
- [x] **TASK-05**：撰寫 `test/test_dev_toolchain_refactor.py` 單元與整合測試（涵蓋 FT-01~08, ET-01~07）

---

## 2. 實作偏差紀錄表 (Implementation Deviations)

| 任務編號 | 偏差等級 | 偏離描述與決策理由 | 處置方式 / 記錄 |
| :--- | :---: | :--- | :--- |
| **TASK-01** | `Minor` | 為維持 Python API 相容性，`Builder.build_module` 保留 `clean: bool = True` 預設參數，但實體一律自動清空目標資料夾 | 已實作並相容既有合約測試 |
