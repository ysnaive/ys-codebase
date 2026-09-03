# Zip 套件規格與同構自舉管線手冊 (Zip Packaging & Isomorphic Bootstrap Spec)

> 適用模組：`core`, `dev`, `yscb.py`  
> 建立日期：2026-08-25  
> 標準對齊：維度 3 (Topic Docs: 多物件協同/資料管線/通訊協議)

---

## 1. 核心理念：明文空間二分法與全面 Zip 單檔標準

YS-Codebase 遵循**明文空間嚴格二分法**：
- **明文展開空間（僅 2 處）**：
  1. `source/<module>/`：唯一源碼來源（SSOT，開發期編輯）。
  2. `.modules/<module>/`：唯一執行期純粹代碼空間（微內核直譯器執行）。
- **單檔 Zip 存儲空間**：
  - `.build/<module>/<version>.build.zip`：本地開發完整建置包（含 tests/）。
  - `release/<module>/<version>.zip`：發布產物純淨包（排除 tests/ 與 .yscbignore）。
  - `.mirror/<module>/<version>.zip`：離線下載鏡像快取。

---

## 2. 套件結構與排除規範

### 2.1 建置包 vs. 發布包對比

| 特性 | 本地建置包 (`.build/`) | 發布純淨包 (`release/`) |
| :--- | :--- | :--- |
| **檔案命名** | `<version>.build.zip` (例: `1.0.0.build.zip`) | `<version>.zip` (例: `1.0.0.0.zip`) |
| **測試目錄 (`tests/`)** | **包含**（供開發期沙盒回歸測試） | **排除**（節省頻寬與磁碟） |
| **忽略檔案 (`.yscbignore`)** | 排除內部忽略規則 | **排除 `.yscbignore` 本身與其規則** |
| **伴隨 Index** | `.build/<module>/index.json` | `release/<module>/index.json` |

---

## 3. 4-Stage Atomic Reload 流水線

```text
[Stage 1: 依賴校驗] 檢查 core.json 與依賴模組版本約束
[Stage 2: 解壓物化] 剛性清空 .modules/{mod}/，透過 zipfile.extractall() 物化代碼
[Stage 3: 組態治理] 掃描 .modules/ 內組態模板，軟合併部署至 config/，並物理刪除 .modules 內模板
[Stage 4: Hook廣播] 載入 on_install / on_reload，更新 manifests.merged.json
```

---

## 4. 遠端 HTTP Provider 通訊協議

```text
Provider Root (例: https://raw.githubusercontent.com/.../release)
  ├── core/
  │     ├── index.json          # {"name": "core", "versions": ["1.0.0.0"]}
  │     └── 1.0.0.0.zip        # 純淨單檔 Zip
  └── dev/
        ├── index.json
        └── 1.0.0.0.zip
```
