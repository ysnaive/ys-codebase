# 需求討論說明書 (Semantic Requirements Discovery)

> 功能名稱：dev test 輸出格式優化與節流模式 (Throttle Output)  
> 建立日期：2026-09-03  
> 所屬主計畫：2026_09_03_1227_agents_workflow_plan_filter_and_session_analysis  
> 狀態：Confirmed  
> 計畫類型：Feature  
> 模板版本：v1.2  

---

## 1. 使用者原始需求與意圖 (User Intent)

- **原始陳述**：
  > 建立衍生子計畫， dev test 輸出格式優化，因平常就有很多更動後回歸測試的需求，每次完整回報皆產生大量 IO token 浪費，規劃加入節流模式，該模式僅輸出 "Pass: {n}({percent:.1f}), Fail: {n}, Skip: {n}" 和 Fail 之測試詳情，最大化壓縮 token io
- **核心目標**：
  1. **節流模式開關**：於 `python yscb.py dev test` 新增 `--quiet` 與 `-q` 參數。
  2. **深度靜默前置日誌**：在節流模式下，徹底抑制前置沙盒建置、沙盒建立與清理訊息（如 `[dev:test] Pre-building...`、`Create sandbox...`、`Cleaned up sandbox...`）。
  3. **極致壓縮成果輸出**：
     - 若全數通過，僅輸出單行：`Pass: {passed}({percent:.1f}%), Fail: {failed}, Skip: {skipped}`（最大化節省 Token I/O）。
     - 若有測試失敗，輸出該單行統計並附加 `FAILED / ERROR TEST CASES LIST:` 詳情（含錯誤訊息、位置與 Quick Re-run 提示）。
  4. **全場景支援**：同時支援單模組測試（`python yscb.py dev test <mod> -q`）與全生態系多模組平行測試（`python yscb.py dev test --all -q`）。
- **邊界排除 (Explicitly Excluded)**：
  - 預設行為維持既有完整 ASCII 診斷報告，未顯式傳入 `-q` 或 `--quiet` 時保持原樣。
  - 不改動測試框架本身之斷言邏輯、沙盒隔離機制與單元測試發現規則。

---

## 2. 核心討論與決策紀錄 (Discussion & Decisions)

- **[P00:DR-01] 子計畫掛載位置**：掛載於 `plans/2026_09_03_1227_agents_workflow_plan_filter_and_session_analysis/` 下作為衍生子計畫 `sub_01_dev_test_throttle_output`。
- **[P00:DR-02] CLI 介面契約**：提供 `--quiet` 與 `-q` 作為節流開關，預設未帶參數時維持既有行為。
- **[P00:DR-03] 深度靜默策略**：節流模式下徹底抑制前置 build、沙盒進度日誌；僅輸出最終統計與失敗細節。
- **[P00:DR-04] 格式契約定義**：
  - 全數通過：`Pass: {passed}({pass_pct:.1f}%), Fail: 0, Skip: {skipped}`
  - 存在失敗：先輸出統計行，接續輸出 `FAILED / ERROR TEST CASES LIST:` 區塊。
- **[P00:DR-05] 開發模式分流**：本任務涉及 CLI 參數解析、報告格式化器擴充與雙場景回歸，採標準 Full Track 子計畫推進。

---

## 3. 開放議題與確認紀錄

- [x] **子計畫歸屬**：已確認掛載於 `plans/2026_09_03_1227_agents_workflow_plan_filter_and_session_analysis`。
- [x] **CLI 參數偏好**：已確認提供 `--quiet` / `-q` 參數。
- [x] **前置日誌處置**：已確認採深度靜默策略。
