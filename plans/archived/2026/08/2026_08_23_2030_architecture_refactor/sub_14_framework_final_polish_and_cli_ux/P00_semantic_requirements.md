# 語意需求說明書 (Semantic Requirements Discovery)

> 功能名稱：框架骨架最終打磨與 CLI UX 體驗優化 (Framework Final Polish & CLI UX)  
> 建立日期：2026-08-25  
> 所屬主計畫：[2026_08_23_2030_architecture_refactor](../umbrella_overview.md)  
> 狀態：`Confirmed`  
> 擴充項目：無  
> 模板版本：v1.4  

---

## 1. 使用者原始需求與意圖 (User Intent)

經過端到端原生消費者測試與地毯式全局架構校驗後，框架核心微內核已高度穩固。本次子計畫 `sub_14` 作為架構重構的最終收尾打磨，聚焦於以下兩大核心議題的定案與實現：

1. **議題一：`dev release` 移除 Gate 1 (Git Dirty 限制)**
   - **定案決策**：徹底移除 Gate 1（Git Dirty 檢查）。由於 YSCB 框架為本地端產出純淨單檔 Zip 發布包至 `release/`，由開發者自行掌控何時 Push 遠端，發布流水線應保持 100% 敏捷流暢，不再強制阻斷本地打包發布。
2. **議題二：全系統 CLI `--help` 派發架構與 UX 體驗精緻化**
   - **定案決策**：確立標準 Help 格式與動態派發流：
     - 使用者調用 `python yscb.py --help` 時，宿主輸出標準 Header 與 Core 指令清單（`init` 特化自動整併於 Core 指令中）。
     - 宿主透過微內核依序動態聚合已安裝模組（如 `dev`）之指令清單與摘要，格式化輸出為層次清晰的 `MODULE COMMANDS` 區塊。
     - 支援各子指令深層 `--help`（如 `python yscb.py install --help`、`python yscb.py dev create --help`）與智慧拼寫錯誤建議（Did you mean?）。

---

## 2. 核心架構與調用流定義 (Architectural Contract)

### 2.1 `yscb.py --help` 動態派發調用流

```text
[使用者執行: yscb.py --help]
         │
         ▼
[yscb.py 宿主解析] ───► 輸出 Header (Banner, Version, General Usage)
         │
         ├──────► 輸出 [CORE COMMANDS] (init, install, update, remove, list, status, reload, rollback)
         │
         ▼
[掃描 contributes / modules]
         │
         ▼
[依序輸出 MODULE COMMANDS]
   ├── [dev] : create, check, build, test, release, op-mksb, op-test
   └── [其他第三方模組] : ...
```

### 2.2 `dev release` 守門機制精簡

- **移除**：Gate 1 (`git status --porcelain` 檢查)。
- **保留**：
  - Gate 2 (測試守門，可透過 `--no-test` 繞過)。
  - Gate 3 (版本不可變性檢查，防止覆蓋已存在的 Immutable 版本)。
  - Gate 4 (Manifest 合規靜態檢查)。

---

## 3. 開放議題與決策確認紀錄

- [x] **[P00:DR-01] 徹底移除 Gate 1 Git Dirty 限制**：本地發布庫模式下無需強綁 Git 乾淨狀態。
- [x] **[P00:DR-02] 確立 Help 動態聚合派發架構**：`yscb.py --help` 負責全域動態派發，`init` 整合至 Core 區塊，子模組指令自動掃描宣告輸出。
