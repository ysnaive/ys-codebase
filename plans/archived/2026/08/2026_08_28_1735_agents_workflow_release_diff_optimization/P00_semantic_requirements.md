# 語意需求說明書 (Semantic Requirements Discovery)

> 功能名稱：agents-workflow 發布引擎來源 Diff 檢測與無效 File IO 優化 (agents-workflow Release Diff Optimization)  
> 建立日期：2026-08-28  
> 所屬主計畫：無（獨立計畫）  
> 狀態：Confirmed  
> 計畫類型：Performance  
> 模板版本：v1.1  

---

## 1. 使用者原始需求與意圖 (User Intent)

- **原始陳述**：agents-workflow release 功能優化，現 agents-workflow 會在 module reload 階段自動對已註冊目標 release，但沒做來源 diif 檢測機制，導致容易產生大量無效 File IO。
- **核心目標**：
  1. **雙階防護 Diff 檢測 (方案 C)**：
     - **第一階（來源端指紋短路）**：在編譯前檢查來源資源（`assets/`、`manifest.json`、設定檔與目標配置等）之變更指紋。若來源全無異動且發布目標未變更，則提前短路跳過後續編譯與發布流程。
     - **第二階（落地端內容比對）**：若發生部分來源變更或配置調整，在 Stage 4 落地寫入時比對目標檔案現存內容（包含 `AGENTS.md` 軟合併區塊），內容無變化者跳過實體磁碟 I/O 寫入。
  2. **支援強制覆寫 (--force)**：
     - 在 CLI 指令（`release` / `dev release` 等）或呼叫參數中支援 `--force` / `force=True` 旗標，允許開發者/流程在需要時強制忽略所有 Diff 檢測進行全量重新編譯與覆寫。
  3. **細緻結構化統計與日誌回報**：
     - `ReleasePublisher.release_all()` 回傳結構與 `hook.core.py` 觸發日誌需包含 `written_count`、`skipped_count`（無變更）、`removed_count` 等詳細統計。
  4. **零破壞相容性保證**：
     - 保證在各類變更情境（新增 workflow、修改 template、變更 release target、更新 header 模板等）下，產物能 100% 正確同步與清理。
- **邊界排除 (Explicitly Excluded)**：
  - 不變更既有工作流模板與標準規範的實質內容。
  - 不變更 `contributes.agents-workflow` 的規格架構。
  - 不影響微核心 `on_reload` 事件的調度機制本體。

---

## 2. 核心討論與決策紀錄 (Discussion & Decisions)

- **[P00:DR-01] 採用雙階 Diff 防護機制 (方案 C)**：
  - Stage 0 來源指紋比對：若來源資產與發布組態指紋完全一致且目標檔案全數存在，提前返回略過編譯與寫入。
  - Stage 4 落地內容比對：解算渲染完成後，比對目標檔案實體內容，僅在內容實質發生變更時調用 `open(..., "w")` 與 `os.makedirs`。
- **[P00:DR-02] 支援 `--force` 強制發布**：
  - CLI `release` 指令支援 `--force` 參數，`ReleasePublisher.release_all(force=True)` 支援顯式跳過來源指紋短路與落地略過，強制進行全量覆寫。
- **[P00:DR-03] 結構化指標與日誌透明化**：
  - 發布回傳資料結構升級，提供 `written_count`、`skipped_count`、`removed_count`、`short_circuited`（是否提前短路）等指標，Hook 輸出友善之統計摘要。

---

## 3. 開放議題與確認紀錄

- [x] **Diff 檢測層級與策略**：確認採用方案 C（雙階防護：來源指紋提前短路 + 落地內容比對）。
- [x] **強制發布旗標 (Force Release Option)**：確認支援 `--force` 參數強制全量覆寫。
- [x] **執行日誌與指標回報**：確認支援結構化指標與詳細寫入/略過統計回報。
