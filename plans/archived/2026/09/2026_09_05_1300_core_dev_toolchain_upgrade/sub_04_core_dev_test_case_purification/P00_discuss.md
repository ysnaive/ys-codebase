# 需求討論說明書 (Semantic Requirements Discovery)

> 功能名稱：core_dev_test_case_purification  
> 建立日期：2026-09-05  
> 所屬主計畫：2026_09_05_1300_core_dev_toolchain_upgrade  
> 狀態：Confirmed  
> 計畫類型：Refactor  
> 模板版本：v1.2  

---

## 1. 使用者原始需求與意圖 (User Intent)

- **原始陳述**：「開啟 sub 05， core / dev module test case 純化，經幾次迭代，須定時進行測試純化，合併類似 case，移除重複 case，高負重單次行測試併入 requirement workflow」
- **核心目標**：
  1. 對 `core` 與 `dev` 兩大基礎模組的既有測試套件進行全面性審查與純化。
  2. 消除多輪迭代所累積之重複測試、相似測試與冗餘 mock 案例，精簡維護成本。
  3. 將高耗時、多步驟、涉及沙盒反覆建立/銷毀與多行程調度之繁重測試案例，重新分類標註為 `@require(Requirement.WORKFLOW)`，將日常快速回歸（Default: LOGIC + ENV）執行耗時大幅縮減。
  4. 100% 守護契約完整性與功能覆蓋率，純化過程保證零回歸、零邏輯丟失。
- **邊界排除 (Explicitly Excluded)**：
  - 嚴禁更動 `core` 與 `dev` 的 Public API 與核心業務邏輯代碼。
  - 嚴禁刪除任何唯一的邊界條件或異常處理斷言。
  - 不更動 `knowledge-db` 或 `agents-workflow` 的測試案例（本計畫聚焦於 `core` 與 `dev` 工具鏈）。

---

## 2. 核心討論與決策紀錄 (Discussion & Decisions)

- **[P00:DR-01] 子計畫編號與分流模式確立**：
  - 經釐清確認，子計畫接續當前進度標定為 `sub_04_core_dev_test_case_purification`。
  - 鑑於涉及跨 `core` 與 `dev` 兩大核心模組、多達 30+ 測試檔案與上百測試案例之審查與重構，採標準 **Full Track** 推進，確保每一項案例異動均可追溯且具備驗證閉環。

- **[P00:DR-02] 測試純化三維策略矩陣**：
  1. **合併同質測試 (Consolidate)**：針對同一目標組件中僅有些微參數差異的測試方法，收斂整合為結構清晰之單一複合測試（例如 `test_tester_sync.py` 與 `test_tester_throttle.py` 整合至 `test_tester.py`；`test_cli_help.py` 與 `test_cli_guild.py` 合併）。
  2. **淘汰重複/過時測試 (Prune)**：清理因歷史功能演進而已被高階整合測試完全包覆之粗糙 mock 單元測試，移除無實質防護效益之重複斷言。
  3. **高負重測試轉移至 WORKFLOW (Reclassify)**：
     - 凡需要調用多次 `SandboxProvisioner.create_sandbox`、完整調度器子進程、或涉及多行程並發執行之重型測試（單一方法耗時 $> 1\text{s}$ 或產生磁碟 I/O），顯式標註 `@require(Requirement.WORKFLOW)`。
     - 日常 `dev test <mod> --quiet` 預設排除 WORKFLOW 分類，加速開發反饋循環；在 CI 或全量回歸時以 `--all-types` 或 `--workflow` 全量跑測守門。

- **[P00:DR-03] 基線比對與零回歸驗證閉環**：
  - 純化前先行統計當前 `core` (45 測) 與 `dev` (78 測) 測試清單與執行耗時基準。
  - 純化後以 `dev test <mod> --all-types` 驗證所有測試案例 100% 通過，且預設模式（LOGIC + ENV）耗時顯著下降。

---

## 3. 開放議題與確認紀錄

- [x] 子計畫編號接續使用 `sub_04`（開發者已確認）。
- [x] 執行策略採全面純化（合併類似 case + 移除重複 case + 耗時重型測試標註 WORKFLOW，開發者已確認）。
