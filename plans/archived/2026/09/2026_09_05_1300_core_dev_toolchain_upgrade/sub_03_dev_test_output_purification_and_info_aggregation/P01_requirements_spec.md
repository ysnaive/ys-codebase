# 需求規格說明書 (Requirements Specification)

> 功能名稱：dev_test_output_purification_and_info_aggregation  
> 建立日期：2026-09-05  
> 所屬主計畫：2026_09_05_1300_core_dev_toolchain_upgrade  
> 狀態：Confirmed  
> 依據 P00：[P00_discuss.md](./P00_discuss.md)  
> 模板版本：v1.5  

---

## 1. 功能需求清單 (Functional Requirements)

| 需求編號 | 需求名稱 | 詳細規格描述 | 優先級 | 對應 P00 語意 |
| :--- | :--- | :--- | :---: | :--- |
| **FR-01** | 沙盒終端輸出完整屏蔽與高保真維護 | 恪守沙盒黑盒子原則，宿主調度器完全捕獲沙盒所有 stdout/stderr；嚴禁短路沙盒內部真實業務或 JIT 自癒發布鉤子，維護沙盒高保真真實度。 | P0 | [P00:DR-01] |
| **FR-02** | 統一 JSON IPC 測試報告架構 | 將單模組測試 (`_run_test`) 與平行測試 (`_run_parallel_test`) 全面收斂為以 `--report-json` 與 `--quiet-report` 為唯一資料傳輸協議，徹底解耦沙盒內部 stdout 與宿主渲染。 | P0 | [P00:DR-02] |
| **FR-03** | `_run_test` 子進程 stderr 洩漏防護 | 修復 `_run_test` 無條件 dump 子進程 stderr 的漏洞。在 `--quiet` 全通時嚴格保證 0 輸出；非預期 stderr 僅在測試真正失敗時附加於報表。 | P0 | [P00:DR-02] |
| **FR-04** | 雙模式信息聚合策略看板 | 實作 `--quiet` 模式極致單行全通與失敗精確清單；實作一般模式結構化前置生命週期摘要、子進程警告計數折疊與無亂碼安裝提示整併。 | P0 | [P00:DR-03] |
| **FR-05** | 根除宿主沙盒穿透之剛性守門 | 拔除 `TestRunner.run_suite` 偽造 `YSCB_TEST_SANDBOX` 標識；`case.py` 沙盒路徑解析失敗時強制拋出 `SecurityError`，嚴禁回退到 `os.getcwd()`；`dev op-test` 增加宿主直接執行阻斷。 | P0 | [P00:DR-04] |

---

## 2. 邊界與異常情況 (Edge Cases & Failure Modes)

| 邊界編號 | 情境說明 | 預期防禦與處理行為 |
| :--- | :--- | :--- |
| **EC-01** | 沙盒內部發生非預期崩潰（Crash / returncode != 0 且未生成 report JSON） | 宿主提取沙盒 stderr 尾部切片（Tail 20 行）作為錯誤診斷回報，防止無窮靜默。 |
| **EC-02** | 開發者在宿主專案根目錄直接調用 `python yscb.py dev op-test` | 系統立即攔截並拋出明確錯誤提示，引導改用 `python yscb.py dev test`，絕不在宿主落地跑測。 |
| **EC-03** | 測試期間產生大量非致命警告（如未解 URI、Python DeprecationWarning） | 一般模式下進行計數折疊收斂（`[!] Warnings: N captured (use --verbose to inspect)`），避免打碎 ASCII 診斷報表。 |

---

## 3. 非功能需求 (Non-Functional Requirements)

| 需求編號 | 類別 | 指標與量化約束 |
| :--- | :--- | :--- |
| **NFR-01** | 節流效能 | `--quiet` 模式全通時字元數 $\le 50$ Bytes（單行），日常 Token 吞吐節省 95% 以上。 |
| **NFR-02** | 相容性 | 保持 `--report-json` 結構化資料完整性，不破壞 Quick Re-run 指令與 4-Tier 測試分類。 |
| **NFR-03** | 純淨性 | 任何測試情境下嚴禁在宿主專案根目錄產生任何 mock 模組或測試 scope 殘留目錄。 |

---

## 4. 知識庫與踩坑紀錄查閱 (Known Gotchas & CAUTIONs)

- **`[!IMPORTANT]` 測試執行器不可偽造沙盒身分**：過去 `TestRunner.run_suite` 內部私設 `YSCB_TEST_SANDBOX="1"`，導致 Gate 3 安全守門失效，此漏洞必須剛性修復。
- **`[!NOTE]` 統一 JSON IPC 消除雙軌維護**：過去 `_run_test` 走 stdout 串流渲染，而 `_run_parallel_test` 走 JSON IPC，統一收斂至 JSON IPC 可徹底杜絕終端輸出交錯。
