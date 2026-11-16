# Core 2.0 現狀反饋報告 (Status Feedback Report)

> **報告日期**：2026-11-16
> **評估範圍**：`./core_v2/`（`ROADMAP.md`、`R01_execution_orthogonal_research.md`、`sub_module_design/**`、`source/core/core/**`、`verify_execution_live.py`）
> **評估方式**：5 路唯讀功能域稽核 + 匯入依賴圖抽取 + HIGH 等級問題源碼抽驗
> **結構化圖譜**：[`ARCHITECTURE_GRAPH.xml`](./ARCHITECTURE_GRAPH.xml)（本報告之完整證據與行號來源）
> **注意**：本次評估為靜態分析，**未執行** `verify_execution_live.py`。

---

## 1. 一句話結論

已實作的內核（Domain 1、Domain 2.fs、Domain 5）**靜態結構自洽、工程品質高**；但整體系統**僅部分自洽**——文件嚴重落後於代碼、與未建置功能域的介面存在分層矛盾，且有數項執行期行為與設計承諾不符。建議在擴建 Domain 2～4、6 前先處理第 5 節的決策點。

## 2. 進度快照

| 功能域 | 規格 | 代碼 | 狀態 |
| :--- | :---: | :---: | :--- |
| D1 `foundation`（primitives / errors / codec / observability / proc） | 無 | 5 / 5 | 已實作，但 ROADMAP 所列約 20 個元件缺席或改名 |
| D2 `filesystem`（fs / vfs / space / storage） | 無 | 1 / 4 | 僅 `fs`；`vfs`、`space`、`storage` 未開始 |
| D3 `metadata`（config / contributes） | 無 | 0 / 2 | 未開始 |
| D4 `packaging`（env / installer） | 無 | 0 / 2 | 未開始 |
| D5 `execution`（event / lifecycle / rpc / runtime / daemon） | 5 份 | 5 / 5 | 已實作，與規格高度一致 |
| D6 `surface`（sdk / cli） | 無 | 0 / 2 | 未開始；組裝根目前寄居於測試檔 |
| `core_v2/yscb.py`、`source/dev`、`config/` | — | 無 | 未開始 |

- **規模**：內核約 27,600 行；實機驗證套件 23,381 行（Gate 0 + RC-01～RC-08 + 243 組領域測試）。
- **Wave 1 完成度**：以 19 個子模組計約 **11 / 19（58%）**；以規格計 **5 / 19（26%）**。

## 3. 自洽性評分

| 維度 | 評級 | 依據 |
| :--- | :--- | :--- |
| 靜態匯入 DAG | ✅ 自洽 | 52 組內核匯入邊 0 違規 |
| 靜態任務不變量 | ✅ 自洽 | `contracts.py:225-250` + `gates.py:234-402` |
| execution 規格 ↔ 代碼 | 🟡 大致自洽 | R01 13 項修補：11 完成、2 部分完成 |
| ROADMAP ↔ 代碼 | ❌ 不自洽 | 約 25 個元件名稱不存在或改名 |
| 跨功能域介面 | ❌ 不自洽 | `ModuleProviderPort` 回傳 execution 擁有之型別 |
| 執行期行為 ↔ 設計承諾 | 🟡 部分自洽 | 3 項 HIGH + 約 20 項 MEDIUM |
| 推進流程 ↔ ROADMAP 計畫 | ❌ 不自洽 | 「先規格、由下而上」vs 實際 execution 優先 |

問題總數：**HIGH 5 / MEDIUM 27 / LOW 40+**。

---

## 4. 主要問題

### 4.1 HIGH（5 項）

| 編號 | 類別 | 問題 | 證據 |
| :--- | :--- | :--- | :--- |
| **F-01** | 死鎖 | 跨進程 SERIALIZE 重入：進程 A 持鎖並巢狀呼叫 Daemon，其合法後代可能被排在「正等待 A 鎖」的無關持有者之後，形成循環等待且無破解機制 | `coordinator.py:1590, 2055-2073, 2390-2417` |
| **F-02** | 介面設計 | `ModuleProviderPort` 回傳 `ModuleDescriptor` / `TaskRouteSpec` 等 execution 擁有之型別；未來提供者 packaging / metadata 被 DAG 禁止匯入 execution，照現設計無法實作 | `contracts.py:752-822`；ROADMAP §3 規則 2、3.1 |
| **F-03** | 跨平台 | `spawn_detached` 非真正脫離：從受管進程樹內啟動的 Daemon 在 Linux / Windows 會被連帶清除，macOS 則存活 | `proc.py:286-312, 552-576, 138-160` |
| **F-04** | 文件 | `sub_module_design/runtime.md` 為過時 v0 規格（L0-L5 分層、禁止匯入 rpc/lifecycle），與現行規格及代碼直接衝突，且不在 Gate 0 檢查範圍 | `sub_module_design/runtime.md:1-21` |
| **F-05** | 流程 | Wave 1 要求「全部規格 + 盲審 → 由下而上實作 → 逐域拔除測試」，實況為 D5 先行、D1/D2 無規格、D3/D4/D6 空白、僅有單體實機套件 | `ROADMAP.md:126` |

> F-02、F-03、F-04 已直接對照源碼確認；F-01 來自稽核子代理分析，尚未以實機重現。

### 4.2 MEDIUM 重點（節錄，完整 27 項見 XML）

- **P3 不重跑承諾僅客戶端視角成立**（F-RPC-01）：伺服端已開始執行但客戶端未收到受理訊號時會透明重試，非冪等任務可能執行兩次。
- **RPC 信任邊界未定義**（F-RPC-02、F-RT-01）：握手非雙向驗證；Daemon 直接信任客戶端送來的 `approval_scope`，持有 token 即可宣稱 GATED 授權。
- **檔案鎖錯誤語意**（F-FS-06/07/08）：鎖升級逾時拋出致命碼 `ILLEGAL_LOCK_REENTRANCY`，正常競爭會中止整個 Turn；雙共享持有者同時升級會死鎖。
- **Tier 0 工作無法強殺**（F-RT-05）：熱路徑資源鎖會被卡住直到執行緒自然結束。
- **狀態雙真理來源**（F-LC-08）：容器狀態同時存於 lifecycle 與 daemon。
- **背景錯誤被靜默吞掉、無預設 Idle TTL**（F-DM-01/02）。
- **全域狀態**（F-RT-09）：模組載入器修補行程全域的 `importlib.import_module`，違反 DR-05「零全域單例」。
- **驗證可追溯性**（F-VER-01/02）：Gate 0 為黑名單式且不稽核下游模組；約 15 個測試以 orphan/backup/failover 命名，但內核並無此概念。

## 5. 待決策事項

| # | 決策 | 影響 | 建議 |
| :---: | :--- | :--- | :--- |
| D-1 | 模組描述型別（`ModuleDescriptor` 等）歸屬 | 決定 D3/D4 規格能否落地 | 下沉至 foundation / metadata，或明定 execution/surface 轉接層 |
| D-2 | RPC 信任模型 | 非冪等任務安全性、GATED 授權意義 | 明定「先 ack 再產生副作用」規則；明定 `approval_scope` 是 UX 閘門或安全邊界 |
| D-3 | ROADMAP Wave 1 修訂 | 後續推進節奏 | 將 execution 標記為暫定實作，待其餘規格完成後重審 Port 介面 |
| D-4 | 過時 `runtime.md` 處置 | 文件可信度 | 封存或刪除，並讓 Gate 0 對孤兒規格檔報錯 |

## 6. 建議推進順序

1. **文件止血**：處置 F-04、修訂 ROADMAP 命名對照與 Wave 1 計畫（F-05）。
2. **介面決策**：完成 D-1、D-2，再撰寫 D2.vfs/space、D3、D4、D6 規格。
3. **內核修正**：鎖層（F-01、F-FS-06/07/08）→ `spawn_detached`（F-03）→ 狀態單一真理與背景診斷（F-LC-08、F-DM-01/02）。
4. **規格補完**：釐清 CONDITIONAL 收緊、逾時範圍、事件排序語意（F-RT-02/03/06、F-EV-03/04）。
5. **工具鏈**：Gate 0 改白名單、加入下游模組稽核與逐域拔除測試，測試命名對齊內核用語（F-VER-01/02）。
6. **實機回歸**：完成上述修正後執行 `verify_execution_live.py` 全套驗收。
