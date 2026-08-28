# 語意需求說明書 (Semantic Requirements Discovery)

> 功能名稱：測試框架 Session 層級共用沙盒與效能優化 (Test Session-Level Shared Sandbox Optimization)  
> 建立日期：2026-08-28  
> 所屬主計畫：無（獨立計畫）  
> 狀態：Confirmed  
> 計畫類型：Performance  
> 模板版本：v1.1  

---

## 1. 使用者原始需求與意圖 (User Intent)

- **原始陳述**：如果改成只要沒標記，就完全用同一個沙盒，會有問題嗎？/NewPlan 進行本次優化。1. 是（聚焦現有 YSCBTestCase），2. 是（維持多 Worker 獨立沙盒邊界），/Auto 連續推進。
- **核心目標**：
  1. 將測試框架（`YSCBTestCase`）的預設沙盒共用顆粒度由「類別層級 (Class-Level)」提升為「全執行期 / 模組層級 (Session/Module-Level)」，消除跨測試類別頻繁在 Windows NTFS 上重複建立與刪除實體沙盒目錄的昂貴 I/O 開銷。
  2. 盤點全代碼庫中具有檔案系統寫入、模組安裝/解除安裝或全域組態修改等破壞性行為的測試案例，精確標記 `@require(Requirement.ISOLATED_SANDBOX)`，確保狀態隔離與防呆。
  3. 徹底根除外層 `dev test` 與內層 `YSCBTestCase` 的雙層沙盒重疊建立，大幅壓縮全系統回歸測試時間（預期平均單測耗時從 ~0.08s 壓降至 0.01~0.02s）。
- **邊界排除 (Explicitly Excluded)**：
  - 不變更既有測試之斷言與驗證邏輯。
  - 不影響 `@require(Requirement.ISOLATED_SANDBOX)` 的獨立沙盒隔離保證。
  - 不變更對外的 CLI 測試命令列介面與報表結構。
  - 本次聚焦於 `YSCBTestCase` 核心生命週期優化，暫不引入全新 `PureLogicTestCase` 衍生基類。

---

## 2. 核心討論與決策紀錄 (Discussion & Decisions)

- **[P00:DR-01] 預設提升為 Session-Level 共用沙盒**：未標記 `ISOLATED_SANDBOX` 的測試方法在同一次跑測 Session 中共用同一個微型沙盒實例，並由 `TestRunner.run_suite()` 在套件執行完畢後統一釋放清理。
- **[P00:DR-02] 寫入型測試剛性標記隔離**：對動態寫入 `module://`、建立 mock package、修改 `config.project.json` 的測試方法顯式標註 `@require(Requirement.ISOLATED_SANDBOX)`，避免狀態外溢至後續測試。
- **[P00:DR-03] 多 Worker 並行沙盒邊界維持**：在 `dev test --all` 多 Worker 並行架構下，各 Worker 進程本身已是獨立沙盒實例，Worker 內部維持 Session-Level 共用沙盒，達成微秒級多核並行與零碰撞。

---

## 3. 開放議題與確認紀錄

- [x] 是否針對純算術/純字串等純邏輯模組提供進一步完全解綁磁碟沙盒的 `PureLogicTestCase`？（**結論：否，本次優先聚焦現有 `YSCBTestCase` 體系**）。
- [x] 關於多模組並行跑測（`dev test --all` 多 Worker）：各 Worker 進程本身已是獨立沙盒實例，Worker 內部採用 Session-Level 沙盒，確認維持此架構邊界。（**結論：確認維持**）。
