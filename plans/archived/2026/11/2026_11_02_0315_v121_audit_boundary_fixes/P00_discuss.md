# 需求討論說明書 (Semantic Requirements Discovery)

> 功能名稱：YS-Codebase v1.2.1 二輪審計 5 項邊界條件與相容性隱患修復  
> 建立日期：2026-11-02  
> 所屬主計畫：2026_11_02_0315_v121_audit_boundary_fixes  
> 狀態：Confirmed  
> 模型：Gemini 4 Argon (Low)  

> 計畫類型：Bug Fix  
> 模板版本：v1.2  

---

## 1. 使用者原始需求與意圖 (User Intent)

- **原始陳述**：依據《YS-Codebase v1.2.1 大幅優化二輪審計與 5 項邊界隱患總表》，開立 Full Track 開發計畫並透過 `/auto` 修復 5 項跨模組邊界條件與相容性隱患。
- **核心目標**：
  1. **隱患 1 (`core` / `yscb.py`)**：於 `yscb.py` 與 `ys_codebase/source/core/core/engine.py` 之 `LEGACY_PROVIDER_URLS` 補齊舊倉庫名 `https://raw.githubusercontent.com/ysnaive/agent.workflow/main/ys_codebase/release`（含尾部 `/` 變體），確保倉庫改名前初始化之下游專案（如 `uitk.net`、`GC_VEX_V5`）可無縫自動遷移至 `/releases` 分支。
  2. **隱患 2 (`knowledge-db`)**：解決 C# `partial class` 跨檔聚合之「`patch_incremental` 增量熱修補失憶」與「$N^2$ 成員重複倒排索引膨脹」雙重問題。
  3. **隱患 3 (`agents-workflow`)**：修復 `PlanScanner.build_recovery_capsule` 讀取 `P{XX}-05_auto.md` 單檔合併模板時，誤將 `§4.2 文檔衝擊表` 第一欄維度名稱（如 `**模組手冊**`）當成受影響檔案路徑提取之問題。
  4. **隱患 4 (`agents-workflow`)**：修復 `PlanVerifier` 的 `BACKPROP`（重大偏差反向回寫檢核）於 `P{XX}-05_auto.md` 單檔合併模式下因 `p02_path == p05_path` 被短路失效之問題。
  5. **隱患 5 (`agents-workflow`)**：修復 `compiler.py` 的 `_replace_in_code_span` 對展開為空字串的根路徑標籤 `` `__${project://}__` `` 產生空雙反引號 `` `` `` 之問題，穩定回退渲染為 `` `./` ``。
- **既有組件復用與查重 (Reuse Discovery)**：100% 於既有 `normalize_legacy_provider_url`、`aggregate_partial_symbols`、`InvertedIndex.patch_incremental`、`PlanScanner.build_recovery_capsule`、`PlanVerifier` 與 `compiler._replace_in_code_span` 原地擴充與修復，零重複造輪子。
- **邊界排除 (Explicitly Excluded)**：不變動各模組既有公開 CLI 指令結構或外部組態 Schema。
- **架構影響範圍**：`yscb.py`、`ys_codebase/source/core/core/engine.py`、`ys_codebase/source/knowledge-db/knowledge_db/{bundler,retrieval}.py`、`ys_codebase/source/agents-workflow/agents_workflow/{compiler.py,plans/scanner.py,plans/verifier.py}` 及對應單元測試。

---

## 2. 核心討論與決策紀錄 (Discussion & Decisions)

- **[P00:DR-01] `LEGACY_PROVIDER_URLS` 雙倉舊網址無感遷移**：
  - 於 `yscb.py` 與 `core/engine.py` 的 `LEGACY_PROVIDER_URLS` 同時收錄 `ysnaive/ys-codebase/main/ys_codebase/release(/ optional)` 與 `ysnaive/agent.workflow/main/ys_codebase/release(/ optional)` 共 4 組字串，使 `normalize_legacy_provider_url` 與 `AtomicEngine._get_config` 皆能離線自動遷移至 `DEFAULT_PROVIDER_URL` (`.../ysnaive/ys-codebase/releases`)。
- **[P00:DR-02] C# `partial class` 消除 $N^2$ 倒排索引膨脹與 `patch_incremental` 增量重聚合**：
  - **消除 $N^2$ 倒排索引膨脹**：於 `aggregate_partial_symbols` 中，在將跨分部 `merged_members` 賦予分部符號前，先將各分部檔案**自身原始定義之成員名稱/簽名集合**保存於 `metadata["own_members"] = list(orig.members)`（同時僅將 `children` 維持為 `orig.children`，或於 `InvertedIndex` 計算 `members_text` 時優先讀取 `sym.metadata.get("own_members", sym.children)`）；如此既能讓 `sym.members` 保有跨分部完整視角（相容 `TopologyLinker` 與既有 `cls_sym.members` 查詢），又能確保每個方法在 `InvertedIndex` 倒排表中**僅在定義它的分部檔被索引 1 次**，徹底消除 $N^2$ 倒排膨脹！
  - **`patch_incremental` 局部重聚合**：於 `InvertedIndex.patch_incremental` 中，當舊髒檔符號移除後，檢查被移除符號或 `new_symbols` 是否包含 C# `class/struct/interface`；若有，則找出同 `(spaces, kind, fqn)` 仍在 `self.symbols` 中的存量分部符號，將其先從倒排表移除並還原其自身 `own_members` / `own_base_types` / `own_field_types`，再與 `new_symbols` 中的同群組分部符號一併執行 `aggregate_partial_symbols` 後重新 `add_symbol` 寫入倒排表，確保任意分部檔增刪改後全部分部符號之 `base_types`、`field_types` 與 `members` 100% 即時同步。
- **[P00:DR-03] `build_recovery_capsule`、`BACKPROP` 單檔模式檢核與根路徑 `` `./` `` 渲染**：
  - `PlanScanner.build_recovery_capsule`：掃描 `P02` / `P{XX}-05_auto.md` 時，遇到 `## 3.` 或 `## 4.` 標題即停止掃描異動檔案表，並過濾不含路徑特徵（無 `/` 且無 `.`）或帶粗體 `**` 之維度標籤列。
  - `PlanVerifier` 之 `BACKPROP` 檢核：當 `p05_path` 含 `Major` / `Critical` 偏差列且處於單檔合併模式（`p02_path == p05_path`）時，檢查該偏差列之處置欄是否明確記載已回寫（如含 `§2`、`§3`、`P02`、`P03`、`已回寫`、`已同步`、`backprop` 等關鍵字）或 `changelog.md` 是否含有 `REVISION` 紀錄；若皆無則發出 `BACKPROP` Warning。
  - `compiler.py` `_replace_in_code_span`：對 `m_proj_exact` 在無 `anchor` 時改為 `return f"`{resolved or './'}`"`，防止根路徑 `` `__${project://}__` `` 渲染為空雙反引號 `` `` ``。

---

## 3. 開放議題與確認紀錄

- [x] 已確認開立 Full Track 開發計畫並透過 `/auto` 連續推進至 Phase 6。

