# 最終實作計畫書 (Implementation Plan)

> 功能名稱：超薄宿主單檔實現 (Ultra-Thin Host Bootstrapper)  
> 建立日期：2026-08-24  
> 所屬主計畫：[2026_08_23_2030_architecture_refactor](../umbrella_overview.md)  
> 狀態：Draft  
> 擴充項目：none  
> 模板版本：v1.4  

---

## 1. 交叉驗證與架構檢核 (Cross-Verification Checklist)

- [x] **FR 對齊**：P01 4 大功能需求 (`FR-01` init, `FR-02` self-update, `FR-03` Core 轉發, `FR-04` CLI 派發) 在 P03 均有對應函式簽名 (`cmd_init`, `cmd_self_update`, `dispatch_module`, `main`)
- [x] **EC 防護**：P01 5 大 Edge Cases (`EC-01` ~ `EC-05`) 在 P03 與實作邏輯中均有明確阻斷、語法校驗與回滾防護策略
- [x] **架構一致**：P02 變更清單（新增單檔 `yscb.py`）與 P03 模組簽名 100% 一致，階梯式路由順序已驗證
- [x] **規範約束**：100% 純 Python 3.8+ 標準庫（零外部相依），代碼行數嚴格控制於 150 行以內，嚴守路徑封裝鐵律
- [x] **Test-First 剛性定稿**：`P06_test_plan.md` 測試矩陣已同步定稿為 `Confirmed`

---

## 2. 靈魂拷問 (Stress Test)

### Q1: `yscb.py` 在執行 `init` 自舉時，若因網路中斷或 Provider URL 無效導致 `core` 下載失敗，如何確保不留下半成品的損壞目錄並支援乾淨重試？
**架構設計回答**：
1. **原子下載暫存**：`cmd_init` 先將發布包下載至系統暫存檔（例如 `yscb://.temp/core_bootstrap.tmp`），完成哈希/解壓校驗後，才物化寫入 `modules/core/` 與 `mirror://core/`；
2. **失敗自動清理**：若中途發生任何網路異常或 I/O 錯誤，`try...except` 區塊立即自動清除已建立的暫存檔與未完成之目錄，且**不寫入 `yscb.config.json`**；
3. **無損重試**：目錄保持未初始化狀態，使用者排查網路後可直接重新執行 `python yscb.py init`。

---

## 3. 實作順序 (按依賴拓撲排序)

| 順序 | 實作項目 | 變更檔案與目標 | 品質驗證方式 |
| :---: | :--- | :--- | :--- |
| **1** | **常數與組態工具** | `yscb.py` (`CONFIG_FILENAME`, `CORE_COMMANDS`, `load_config`, `save_config`) | 單元檢查組態檔正確讀寫與錯誤處理 |
| **2** | **宿主自我更新引擎** | `yscb.py` (`cmd_self_update`) | 驗證 `ast.parse` 語法預校驗與 `.bak` 備份覆蓋機制 |
| **3** | **泛用 CLI 派發器** | `yscb.py` (`dispatch_module`) | 驗證未初始化阻斷、模組探測、`subprocess.run` 參數透傳與 Exit Code 傳遞 |
| **4** | **原生自舉初始化引擎** | `yscb.py` (`cmd_init`) | 驗證已初始化防呆、根目錄建立、組態寫入與自舉流程 |
| **5** | **4 層階梯式路由進入點** | `yscb.py` (`main`) | 驗證 `init` ➔ `self-update` ➔ `CORE_COMMANDS` 免前綴 ➔ 泛用派發完整路由 |

---

## 4. 📚 知識庫文檔衝擊與交付規劃 (Documentation Impact Plan)

| 判定依據 (P03/P05/P06 錨點) | 知識維度 | 預計更新/新建的文檔路徑 | 具體涵蓋內容 |
| :--- | :--- | :--- | :--- |
| `P03: yscb.py API` | 維度 2 (邊界與使用) | `docs/Host/README.md` (於 `sub_07` 建立) | 記載宿主單檔起手架構、`init`、`self-update` 與階梯式路由規則 |
| `P05: 路由與 Core 指令智能轉發` | 維度 3 (中觀動態機制) | `docs/Host/cli_routing.md` (於 `sub_07` 建立) | 繪製 4 層階梯路由 Mermaid 圖與參數透傳契約 |
| `P05: 自更新與語法防護` | 維度 5 (工程妥協) | `docs/Host/DESIGN_NOTES.md` (於 `sub_07` 建立) | 登記 `ast.parse` 預驗證與 `.bak` 備份替換防呆模式 |

---

## 5. 關鍵決策速查 (Decision Records Reference)

- **[P01:DR-01]** 宿主原生指令集收斂為 `init` 與 `self-update`，其餘全數模組化。
- **[P01:DR-02]** CLI 派發嚴守路徑封裝，不向業務模組暴露底層實體路徑。
- **[P01:DR-03]** Core 7 大套件管理指令（`install`, `update` 等）免前綴直呼智能轉發。
- **[P02:DR-01]** CLI 派發採用 `subprocess.run` 獨立子進程模式，確保生命週期隔離與 Exit Code 透傳。
- **[P03:DR-01]** 單檔採用純函式型扁平架構，維持 150 行以內極致輕量。
