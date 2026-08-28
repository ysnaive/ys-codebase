# 需求規格說明書 (Requirements Specification)

> 功能名稱：agents-workflow 發布引擎來源 Diff 檢測與無效 File IO 優化 (agents-workflow Release Diff Optimization)  
> 建立日期：2026-08-28  
> 所屬主計畫：無（獨立計畫）  
> 狀態：Confirmed  
> 依據 P00：[P00_semantic_requirements.md](./P00_semantic_requirements.md)  
> 模板版本：v1.4  

---

## 1. 功能需求清單 (Functional Requirements)

| 需求編號 | 需求名稱 | 詳細規格描述 | 優先級 | 對應 P00 語意 |
| :--- | :--- | :--- | :---: | :--- |
| **FR-01** | 第一階：來源端資產指紋短路 | 在編譯發布前（Stage 0），計算 `assets/`（templates、standards、workflows）、`manifest.json`、`config.project.json` 及啟用 Target 之綜合特徵指紋。若指紋與 `storage://` 記錄相同且所有已發布檔案完好存在，則提前短路跳過後續編譯與寫入。 | P0 | [P00:DR-01] |
| **FR-02** | 第二階：落地端檔案內容比對 | 在 Stage 4 落地寫入時，若目標檔案已存在且實體磁碟內容與待寫入產物 100% 一致，則跳過磁碟寫入操作，計入 `skipped_count`；僅在內容不一致時執行 `open(..., "w")` 並計入 `written_count`。 | P0 | [P00:DR-01] |
| **FR-03** | AGENTS.md 軟合併 Diff 檢測 | 在執行 `_soft_merge_agents_md` 時，若合併後之完整內容與現存 `AGENTS.md` 內容完全相同，則跳過磁碟覆寫操作。 | P0 | [P00:DR-01] |
| **FR-04** | `--force` 強制全量重新發布 | `ReleasePublisher.release_all(force=False)` 支援 `force=True`；CLI `python yscb.py agents-workflow release --force` 支援 `--force` 旗標，顯式忽略所有 Diff 檢測進行全量重新編譯與強制覆寫。 | P0 | [P00:DR-02] |
| **FR-05** | 結構化結果指標與日誌透明化 | `release_all()` 回傳結果擴充提供 `written_count`、`skipped_count`、`removed_count`、`short_circuited` 等欄位；`hook.core.py` 的 `on_reload` 輸出友善統計日誌。 | P1 | [P00:DR-03] |

---

## 2. 邊界與異常情況 (Edge Cases & Failure Modes)

| 邊界編號 | 情境說明 | 預期防禦與處理行為 |
| :--- | :--- | :--- |
| **EC-01** | 目標檔案遭外部手動刪除或遺失 | 即使來源指紋未變，若 manifest 中記錄的已發布檔案任一缺失（或 `AGENTS.md` 缺失），第一階短路自動失效，平滑降級執行 Stage 1~4 修復補齊遺失檔案。 |
| **EC-02** | 發布目標清單變更 (`release_targets` 增減) | 來源指紋計算必須納入 `release_targets` 清單與各 Target 的 projections 配置；若 Target 變更，指紋不匹配，自動觸發編譯、新目標物化與舊目標孤立檔案清理。 |
| **EC-03** | 首次全新安裝或 manifest 缺失/損毀 | 若 `storage://agents-workflow/release_manifest.json` 不存在或 JSON 解析失敗，安全降級為全量發布，並於發布後持久化包含指紋之全新 manifest。 |
| **EC-04** | AGENTS.md 自定義章節異動 | 軟合併比對以注入完成之完整文字為準，既有自定義章節變更不被覆蓋，僅在標籤區塊或整體產物與磁碟不一致時才觸發磁碟寫入。 |

---

## 3. 非功能需求 (Non-Functional Requirements)

| 需求編號 | 類別 | 指標與量化約束 |
| :--- | :--- | :--- |
| **NFR-01** | 效能指標 | 在無變更的 module reload 情境下，磁碟寫入次數壓降為 0，消除無效 I/O。 |
| **NFR-02** | 極速短路 | 來源指紋比對在短路命中時耗時 $< 5\text{ms}$，顯著優於全量編譯渲染耗時。 |
| **NFR-03** | 跨平台與無相依 | 100% Python 標準庫實作，保持 Windows / Linux / macOS 路徑與 UTF-8 編碼一致性。 |
| **NFR-04** | 回歸穩定性 | `agents-workflow` 全模組測試維持 100% Passed，無既有功能回歸損壞。 |

---

## 4. 知識庫與踩坑紀錄查閱 (Known Gotchas & CAUTIONs)

- **`[!NOTE]` 知識庫參考**：查閱 `docs/agents-workflow/architecture.md` §4 (發布引擎與目標投影) 與 `docs/agents-workflow/README.md`。
- **`[!CAUTION]` 來源指紋覆蓋範疇**：來源指紋計算不可遺漏 `config.project.json` 中的 `release_targets` 與各 Target 的投影 Header 模板，若僅比對 `assets/` 檔案會導致組態修改時無法及時觸發重發布。
