# 修訂紀錄書 (Revision Log)

> 功能名稱：Core 2.0 內核精簡、統一運行資料流聚合與 SDK 門面設計  
> 建立日期：2026-11-21  
> 所屬主計畫：無（獨立 Full Track 重構計畫）  
> 狀態：Completed  
> 模型：Gemini 4 Neon (High)  

> 模板版本：v1.0  

---

## 1. 修訂紀錄清單 (Revision Entries)

### [REV-01] Core 2.0 全域文檔清查與活規格語意／格式統一
- **修訂類別**：Docs
- **涉及檔案**：
  - `core_v2/STATUS_FEEDBACK_2026-11-16.md`（刪除過時快照）
  - `core_v2/ARCHITECTURE_GRAPH.xml`（刪除過時快照）
  - `core_v2/ROADMAP.md`
  - `core_v2/R01_execution_orthogonal_research.md`
  - `core_v2/sub_module_design/execution/event.md`
  - `core_v2/sub_module_design/execution/lifecycle.md`
  - `core_v2/sub_module_design/execution/rpc.md`
  - `core_v2/sub_module_design/surface/sdk.md`
  - `core_v2/sub_module_design/surface/cli.md`
- **修訂摘要**：
  1. 移除留置於 `core_v2/` 根目錄且已全面過時之 `2026-11-16` 靜態反饋快照（`STATUS_FEEDBACK_2026-11-16.md` 與 `ARCHITECTURE_GRAPH.xml`，原檔已永久保留於 `archive/core-v2-maximalist` Tag）。
  2. 同步更新 `ROADMAP.md`（日期 `2026-11-21`、移除退役 `FlightCascade`、補齊 Wave 1.1 精簡成果、`core.surface.sdk` 25 符號門面與 `core_v2/tests/` 分域測試狀態），並全面清除 `event.md` 與 `lifecycle.md` 正文殘留之 `FlightCascade` 術語，統一對齊同工作區頂層 `StepFlight`。
  3. 補註 `R01_execution_orthogonal_research.md`（日期 `2026-11-21`、`RC-03` 巢狀/事件鏈降級 `SERIALIZE` 與 `RC-06` 全域單一 `QUIESCE` 邊界）與 `rpc.md`（澄清 `CONTROL_REQUEST` 僅供 `Daemon <-> Worker` 內部控制，外部 Daemon 控制面已拒收）。
  4. 將 `surface/sdk.md` 與 `surface/cli.md` 統一改寫為與其餘 7 份活規格一致之繁體中文正文與 5 欄標準標頭（完整保留 `sdk.md` 1:1 Python 契約區塊與 `cli.md` `Draft` 狀態標記）。
- **驗證結果**：`python -B -W error::ResourceWarning core_v2/verify_execution_live.py --suite gate0` 通過（8 份 Active 活規格 + `surface/cli.md` `Draft` 100% 對齊，0 失效連結、0 殘留 `FlightCascade`）；`plan verify` 100% Passed。

---

## 2. 結案與合規檢核 (Completion & Compliance Checklist)

- [x] **修訂與驗證完畢**：所有修訂項目均已實作並通過 Gate 0 活規格 1:1 與殘留詞檢核，無殘留死代碼或過時快照。
- [x] **日誌與文檔同步**：已同步更新 `core_v2/` 全域文檔與活規格，並透過 `plan verify --log` 記錄至計畫 `changelog.md`（本次屬純文檔對齊微調，免重覆更動根目錄 `CHANGELOG.md`）。
- [x] **標頭狀態更新**：本清單檢核項已全數勾選 `[x]`，頂部標頭 `> 狀態：` 已更新為 `Completed`。
- [x] **結構合規檢核（最終守門）**：實機執行 `python yscb.py agents-workflow plan verify 2026_11_20_1740_core_v2_kernel_simplification_and_sdk` 驗證 100% Passed。
