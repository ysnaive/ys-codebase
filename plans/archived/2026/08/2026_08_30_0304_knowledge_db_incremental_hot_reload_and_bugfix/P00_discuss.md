# 需求討論說明書 (Semantic Requirements Discovery)

> 功能名稱：Knowledge-DB Hot Reload 缺陷修復與增量效能優化  
> 建立日期：2026-08-30  
> 所屬主計畫：無 (獨立 Level 1 計畫)  
> 狀態：Confirmed  

> 計畫類型：Bug Fix / Performance  
> 模板版本：v1.2  

---

## 1. 使用者原始需求與意圖 (User Intent)

- **原始陳述**：下游接入專案（`uitk.net`）反饋兩個關鍵問題：
  1. JIT 嗅探提前中斷（Early Return）導致殘缺快照（Truncated Map）寫入 `unified.meta.bin`，使後續查詢在未修改檔案情況下仍陷入「無限熱重載死循環」。
  2. 單檔微小變更觸發全量全庫銷毀與重構，在 150 檔規模下熱重載平均耗時高達 ~2,500ms（AST 全庫解析 60%、分詞與倒排重建 22%、Gzip Level 6 寫盤 10%、NTFS 遍歷 8%）。
- **核心目標**：
  1. 徹底根治 JIT 嗅探提前截斷問題，保證快照 100% 完整，根除無限熱重載死循環。
  2. 建立細粒度增量熱重載架構（JIT 快速嗅探 + 單檔符號快取 Per-File Cache + 倒排索引差量打補丁 Differential Inverted Index + Fast Gzip 落盤），使單檔熱重載延遲降至 $\le 100\text{ms}$（提速 25~50 倍）。
- **邊界排除 (Explicitly Excluded)**：
  - 不修改 Public 檢索查詢介面與回傳格式相容性（`KnowledgeEngine.search` 契約保持 100% 不變）。
  - 不引入第三方外部 C 擴展依賴，維持純標準庫與既有架構設計。

---

## 2. 核心討論與決策紀錄 (Discussion & Decisions)

- **[P00:DR-01]** 嗅探邏輯改為完整走訪並使用 `os.scandir` 加速，回傳完整檔案清冊與精確的差量字典 (`added`, `modified`, `deleted`)，杜絕任何提早返回截斷快照之行為。
- **[P00:DR-02]** 在 `SemanticBundler` 與 `KnowledgeEngine` 中建立單檔記憶體符號快取池 (`_file_symbols_cache`)，未異動檔案 100% 零 I/O 復用符號物件。
- **[P00:DR-03]** `InvertedIndex` 新增差量補丁方法 (`patch_incremental`)，支援以檔案路徑維度快速拔除舊 Postings 並注入新符號 Postings，動態重新計算 `field_avgdl`。
- **[P00:DR-04]** 索引持久化採用 `compresslevel=1` 快速 Gzip 寫盤，兼顧安全與毫秒級落盤。
- **[P00:DR-05]** 計畫分流確立為 **Level 1 (Full Track)** 標準開發計畫，並經開發者確認授權 `/Auto` 連續推進。

---

## 3. 開放議題與確認紀錄

- [x] 分流確認：採 Level 1 (Full Track) 標準開發計畫推進。
- [x] 快取生命週期：`_file_symbols_cache` 綁定於 `KnowledgeEngine`，於 `force=True` 時重置。
- [x] 落盤策略：持久化採用 `compresslevel=1` 快速壓縮。
