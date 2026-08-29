# 語意需求說明書 (Semantic Requirements Discovery)

> 功能名稱：knowledge_db_parser_and_search_optimization  
> 建立日期：2026-08-29  
> 所屬主計畫：2026_08_29_1049_knowledge_db_algorithm_optimization  
> 狀態：Confirmed  
> 計畫類型：Refactor / Performance (Sub-Plan)  
> 模板版本：v1.1  

---

## 1. 使用者原始需求與意圖 (User Intent)

- **原始陳述**：
  1. `/NewPlan 開啟子計畫 03，解析器 & 搜索機制優化`
  2. `先討論解析器的部分，先建立 R01 紀錄當前架構和後續討論內容`
  3. `目前想法先從顆粒度討論，草案如下: 單檔案、單章節、單段落`
  4. `token 池皆以 item 物化為主，當多個 item 可以向上組合語意時，進行組合`
  5. `1. 語法風格偏好 目前傾向只支援可以過濾副檔名 (來源過濾，例如只想找程式碼就 --ftype=c|cpp|h|hpp，文檔就 --ftype=md)，因為現在聚合是由解譯器提供，我們無從得知所有註冊解譯器的 token 定義`
  6. `2. 優化現有搜尋方式: a. 執行搜尋產出結果排序 b. 取前 N 個結果顯示 c. 當取出之結果有可聚合之內容，將其聚合、積分合併 d. 若排序池還有可取出之內容且 (c.) 觸發導致取出數量不及 N，回到 (b.)`
  7. `3. 顯示方式: 原有 item 顯示方式不變，當產生聚合時以 file: |- item 1 |- item 2 \- item 3 最多顯示聚合後內部排名前三之 item。另外實作上改為依然維持原本的 item 拆分，但從同一個檔案產出的 item 可進行聚合`

- **核心目標**：
  1. **解析器 Item 化與行號邊界完善**：各解析器專注提取原子 `BaseItem`，包含精確 `(start_line, end_line)`，維持單一物化 Token 池。
  2. **來源副檔名過濾 (`--ftype`)**：支援 `--ftype=c|cpp|h|hpp` 或 `--ftype=md` 等來源過濾，核心引擎與解析器私有欄位完全解耦。
  3. **Top-N 動態聚合與回填管線 (Dynamic Refill Pipeline)**：同檔案 Items 進行積分累加聚合；若聚合折疊導致頂層結果數不足 $N$，自動向後回填湊滿 $N$ 筆（或池空）。
  4. **樹狀階層顯示排版**：獨立 Item 維持原樣；聚合檔案節點以 ASCII 樹狀分支呈現內部 Top-3 關鍵 Items。

- **邊界排除 (Explicitly Excluded)**：
  - 核心檢索引擎不硬編碼特定語言解析器的私有 token 欄位或複雜布林語法，維持純淨解耦。
  - 聚合節點內部嚴格最多展示 Top 3 Items，不無限展開子項目。

---

## 2. 核心討論與決策紀錄 (Discussion & Decisions)

- **[P00:DR-01]** 於 Umbrella 主計畫 `2026_08_29_1049_knowledge_db_algorithm_optimization` 之下開立 `sub_03_parser_and_search_optimization` 子計畫推進。
- **[P00:DR-02]** 採行 **「原子 Item 唯一物化 + 同檔案動態聚合 + Top-N 回填閉環 (Top-N Refill)」** 核心演算法，倒排索引保持純淨，消滅重複索引膨脹。
- **[P00:DR-03]** 新增 `--ftype` 檔案類型/副檔名過濾參數，支援多副檔名或/且過濾（如 `c|cpp|h|hpp`, `md`）。
- **[P00:DR-04]** 搜尋結果輸出層支援樹狀聚合渲染（`file:` + `|- item` + `\- item`），單一聚合節點內部上限 Top 3。
- **[P00:DR-05]** 聚合積分合併採用**最大值 + 衰減和 (Max + α·ΣRest)**：`Score(File) = max(Sᵢ) + α * Σ(其餘 Sⱼ)`，其中 `α ∈ [0.1, 0.3]`，獎勵語意密集度高的命中檔案。
- **[P00:DR-06]** 解析器深度優化納入本計畫範疇，針對下游專案實際使用需求進行：
  - **必封 (Type 1 — 與 Item 化強耦合)**：各解析器完善 `end_line` 物理邊界座標。
  - **選封 (Type 2 — C++ 深度強化)**：跨行函式簽名狀態機、Namespace 作用域堆疊追蹤、Class 成員作用域關聯。

---

## 3. 開放議題與確認紀錄

- [x] **解析器 Item 化與組合模式**：已確認採原子 Item 物化，組合邏輯內聚於解析器與檔案維度。
- [x] **搜尋過濾語法**：已確認採 `--ftype` 副檔名來源過濾。
- [x] **聚合與回填演算法**：已確立 Top-N 動態聚合回填管線與積分合併規則。
- [x] **終端輸出排版**：已確立樹狀分支排版與 Top-3 Cap 上限。
- [x] **積分合併公式**：已確認採 Max + α·ΣRest（方案 B），α 值於 Phase 1 定稿。
- [x] **解析器深度優化範疇**：確認納入本計畫範疇。Type 1（end_line 必封）+ Type 2（C++ 跨行簽名/Namespace 堆疊/Class 成員關聯）一併推進。

