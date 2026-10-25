# 需求規格說明書 (Requirements Specification)

> 功能名稱：sub_05_ecosystem_integration_and_acceptance  
> 建立日期：2026-10-24  
> 所屬主計畫：2026_10_23_1122_ecosystem_modules_hardening_and_test_purification  
> 狀態：Confirmed  
> 模型：Gemini 4 Argon (Low)  

> 依據 P00：[P00_discuss.md](./P00_discuss.md)  
> 模板版本：v1.5  

---

## 1. 功能需求清單 (Functional Requirements)

| 需求編號 | 需求名稱 | 詳細規格與驗收條件 (Acceptance Criteria) | 優先級 | 對應 P00 語意 |
| :--- | :--- | :--- | :---: | :--- |
| **FR-01** | 全生態系靜態合規與契約聯合驗收 | `[P01:DR-01]` 執行 `python yscb.py contributes check` 與 `python yscb.py dev check --all`，涵蓋 `core`、`dev`、`server`、`knowledge-db` 四大模組及專案級 `config://<target>/contribute.json` 覆寫組態；驗收條件為退出碼 `0`、0 Error、0 Warning。 | P0 | [P00:DR-01] |
| **FR-02** | 全生態系沙盒測試聯合回歸與零污染驗收 | 執行 `python yscb.py dev test --all -q` 進行跨模組全量沙盒回歸測試；驗收條件為四大核心模組共 43 支純化後測試檔（`core`: 21、`dev`: 7、`server`: 3、`knowledge-db`: 12）與全生態系 593 項測試 100% Passed、0 Failed、0 Error、0 Unknown，且執行後 `git status` 無任何沙盒環境殘留污染。 | P0 | [P00:DR-01] |
| **FR-03** | 常駐 Server 託管與多層子命令熱派發實機驗證 | 實機啟動 `python yscb.py server start`，驗證：<br/>1. `server status` 顯示 Server 正常運行，且 `ServiceManager` 自動載入並啟動單一 `knowledge-db-watcher` Worker（狀態 `running`）。<br/>2. 連續執行多層子命令（`uri resolve`、`config get`、`contributes check`、`knowledge-db status`）透過 `_try_hot_dispatch` 熱派發均返回退出碼 `0` 且輸出正確。<br/>3. 執行 `server stop` 觸發兩階段優雅停機握手，Server 與 Worker 100% 乾淨退出無孤兒進程。 | P0 | [P00:DR-01] |
| **FR-04** | 全模組 `@build` 最終熱部署同步核驗 | 確認 `core`、`dev`、`server`、`knowledge-db` 四大模組之最新源碼均已完成 `@build` 打包與本機運行空間（`.modules/`）同步，透過 `python yscb.py list` 驗證各模組均處於最新 `*.build` 啟用狀態。 | P0 | [P00:DR-01] |
| **FR-05** | 8 份已消費 Roadmap 儲備閉環查核與三層文檔對齊 | `[P01:DR-02]` 查核本主計畫所消費之 8 份核心模組加固與測試純化 Roadmap 均已透過 `Consume-on-Promote` 閉環歸檔於 `sub_01` ~ `sub_04` 各子計畫之 `roadmap.md` 且 `plans/roadmap/` 無殘留重複項；同步核驗三層文檔（根目錄 `CHANGELOG.md`、`docs/{core,dev,server,knowledge-db}/`、各模組 `README.md`）對齊無誤，並於結案時更新主計畫 `umbrella_overview.md` 為 `Completed`。 | P0 | [P00:DR-01] |

---

## 2. 邊界與異常情況 (Edge Cases & Failure Modes)

| 邊界編號 | 情境說明 | 預期防禦與處理行為 |
| :--- | :--- | :--- |
| **EC-01** | 驗收前常駐 Server 已處於運行狀態 | 執行端到端生命週期驗證前，先透過 `server stop` 或 `server restart` 確保從乾淨狀態驗證冷啟動、Hook 預熱與 `ServiceManager` 託管掛載流程。 |
| **EC-02** | 跨模組 `@build` 重裝或測試期間觸發 `yscb.config.json` 時間戳更新或快取變動 | 區分合法部署組態變更與非預期測試殘留，確保所有臨時沙盒目錄與測試副產物 100% 清理，不留任何未追蹤垃圾檔案。 |
| **EC-03** | 多層子命令熱派發邊界（含未知子命令與說明旗標） | 於常駐 Server 啟動狀態下驗證群組節點未知子命令攔截（返回非 0 退出碼與標準錯誤提示）及 `--help` 渲染一致性，確保熱派發與冷啟動行為 100% 對齊。 |

---

## 3. 非功能需求 (Non-Functional Requirements)

| 需求編號 | 類別 | 指標與量化約束 |
| :--- | :--- | :--- |
| **NFR-01** | 測試純度與規模 | 四大模組測試檔收斂總數維持 43 檔（21 + 7 + 3 + 12），全量測試執行 0 Unknown、100% Passed（593/593）。 |
| **NFR-02** | 架構隔離與零耦合 | 全模組 100% 遵守 `.modules/` 運行時隔離（零 `source/` 路徑注入）、微內核零上層業務耦合與 `CmdBags` 精確命令契約。 |

---

## 4. 知識庫與踩坑紀錄查閱 (Known Gotchas & CAUTIONs)

- **`[!NOTE]`** `sub_01` ~ `sub_04` 已於各自開立階段透過 `roadmap promote` (Consume-on-Promote) 將 8 份對應之模組加固與測試純化 Roadmap 物理遷入各子計畫目錄下的 `roadmap.md`，因此在 `sub_05` 僅需執行閉環完整性核驗，無須重複執行 `roadmap promote` 搬移。
- **`[!CAUTION]`** 執行全生態系驗證與 `@build` 時，遵循 `yscb-cli-guide` 單行命令規範，避免使用複合 Shell 控制流。

