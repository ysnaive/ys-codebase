# 分類型主計畫作業手冊 (Umbrella Plan)

本手冊定義分類型主計畫（`Umbrella`）的適用場景、兩大統籌模式、目錄結構與主從計畫狀態連動規則，以及極精簡回覆格式。

---

## 1. 適用場景與兩大統籌模式

- **適用場景**：大型系統重構或跨模組史詩級任務，需拆解為多個子計畫進行滾動推進。
- **兩大統籌模式**：
  - **預先規劃型 (Pre-planned Blueprint)**：立項時已能明確拆分出全部子計畫清單（`sub_01`、`sub_02`...）。
  - **增量演進型 (Incremental Evolutionary)**：探索型大任務，先立項 `sub_01`，其餘子計畫隨開發動態滾動開立與驗收。

---

## 2. 目錄結構與主從計畫狀態連動規則

- **目錄結構與產出檔案**：
  - 主目錄：`__${project://plans/}__/{plan_name}/` 下建立 [`umbrella_overview.md`](`__#{module://agents-workflow/assets/templates/umbrella_overview.md}__`) + `changelog.md`（必備）；主計畫級 `P00_discuss.md` / `R{NN}_*.md` 為選配。
  - 各子計畫目錄：`sub_01_{name}/`、`sub_02_{name}/`（各自具備獨立的開發軌道產物與 `changelog.md`）。
- **主從計畫狀態連動規則**：
  1. 首個 `sub_XX` 啟動時，主計畫標頭轉為 `In Progress`。
  2. 新建 `sub_XX` 時，登記於 `umbrella_overview.md` §2 子計畫矩陣。
  3. `sub_XX` 結案時，同步更新父目錄 `umbrella_overview.md`（§2 子計畫狀態、§3 里程碑勾選 `[x]`）與主目錄 `changelog.md`。
  4. 全部子計畫完成且無後續階段時，主計畫標頭轉為 `Completed`。
- [!] **最多兩層約束**：主計畫 -> 子計畫，**絕對禁止三層或更多層嵌套**。

---

## 3. 極精簡 Session 回覆格式

```markdown
###  Umbrella 主計畫已開立
- **產出文件**：[umbrella_overview.md](__${project://plans/}__/{plan_name}/umbrella_overview.md)
- **藍圖摘要**：[規劃子計畫計 N 個 / 執行模式 (Pre-planned/Incremental)]
- **待確認事項**：請問是否同意主計畫藍圖，並授權啟動首個子計畫？
```

