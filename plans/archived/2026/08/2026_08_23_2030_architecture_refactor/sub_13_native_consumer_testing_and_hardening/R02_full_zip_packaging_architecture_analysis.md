# 全面 Zip 單檔打包與 Provider 同構協定調研報告 (R02)

> 子計畫名稱：`sub_13_native_consumer_testing_and_hardening`  
> 報告編號：`R02`  
> 調研日期：2026-08-25  
> 調研主題：套件庫全面 Zip 化 (`{version}.zip`)、本地與遠端 100% 同構協定與極致乾淨檔案樹設計  
> 狀態：Confirmed (與開發者共同確認定稿)  

---

## 1. 調研動機與架構哲學

傳統套件管理體系中，若在建置庫 (`build/`) 與發布庫 (`release/`) 落地展開的散裝目錄（如 `release/core/1.0.0.0/core/...`），會導致：
1. **本地與遠端雙重邏輯分裂**：本地使用檔案系統目錄拷貝 (`shutil.copytree`)，遠端使用 HTTP 串流下載，兩者代碼路徑不同，產生隱性環境 Bug。
2. **倉庫與檔案系統污染**：發布庫充斥數百個深層散裝小檔案，Git Commit 雜亂，同 X.Y.Z 淘汰舊 Revision 時需遞迴刪除整個目錄。

為徹底解決上述問題，本計畫確立**全面 Zip 單檔打包標準 (Full Zip Packaging Standard)**。

---

## 2. 核心規範與檔案空間二分法

### 2.1 Provider 套件庫同構目錄規格
無論本地 Provider 還是遠端 Provider，目錄層級 100% 保持完全同構：

```text
<provider_root>/
  └── <module>/
        ├── index.json                  # {"name": "core", "versions": ["1.0.0.0"]}
        ├── 1.0.0.0.zip                 # 純淨發布包 (排除 tests/ 與 .yscbignore)
        └── 1.0.0.build.zip             # 開發測試包 (若在 build/，自帶 tests/)
```

### 2.2 檔案空間嚴格二分法
全系統中，**明文展開檔案空間嚴格僅存在 2 處**：
1. **`source/<module>/`**：【源碼開發空間 (SSOT)】供開發者編輯維護。
2. **`modules/<module>/`**：【運行執行空間】由 Zip 解包後的純淨 Python 代碼，供直譯器直接 import 執行。

其餘所有中間產物（`release/`, `build/`, `.mirror/`）**一律為 `{version}.zip` 單檔形式存儲**！

---

## 3. 本地與遠端統一自舉管線 (Unified Ingestion Pipeline)

```text
                  [Provider: Local or Remote URL]
                                 │
                                 ▼ (讀取 index.json 取得最新目標版本)
                   [獲取 <module>/<version>.zip]
                                 │
               ┌─────────────────┴─────────────────┐
               ▼ (本地 Provider)                   ▼ (遠端 Provider)
        檔案複製至 .mirror/               HTTP 串流下載至 .tmp.zip -> .mirror/
               └─────────────────┬─────────────────┘
                                 │ (zipfile.testzip() 完整性校驗)
                                 ▼
                     [解包至 modules/<module>/]
                                 │ (自動清理 config.*.json 模板)
                                 ▼
                     [完成 reload 載入執行]
```

---

## 4. 效益評估

1. **同構性 100%**：徹底消滅本地 copytree vs 遠端 download 雙軌邏輯，全系統單一管線。
2. **極致乾淨**：發布與建置產物不再有散裝目錄，清理舊版 Revision 僅需刪除單一檔案 `X.Y.Z.1.zip`。
3. **安全原子性**：Zip 檔案自帶 CRC32 校驗，未完整下載絕不解包，零半套殘留檔案。
4. **執行效能**：Python 在 `modules/` 運行明文檔案，執行期效能 0 折損。
