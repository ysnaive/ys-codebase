---
target: "Core"
doc_type: "topic"
status: "active"
source_paths:
  - "yscb://source/core/core/engine.py"
  - "yscb://source/core/core/installer.py"
  - "yscb.host://yscb.py"
related_docs:
  - "./README.md"
  - "./DESIGN_NOTES.md"
  - "../_project/STANDARDS.md"
last_updated: "2026-10-15"
---

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

## 3. 4-Stage Atomic Reload 流水線與安裝產物驗證

```text
[Stage 1: 依賴與產物校驗] 檢查依賴約束、拉取單檔 Zip 至 module.mirror:// 並執行完整性驗證
[Stage 2: 安全解壓物化]   剛性清空 module://{mod}/，執行 Zip Slip 路徑防逃逸檢查後解壓物化
[Stage 3: 遞迴組態治理]   掃描模組組態模板，遞迴原地增量補齊至 config://，並物理剝除模組內模板
[Stage 4: 注入與事件廣播] 執行 Contributes 拓撲聚合並廣播 on_reload 事件
```

### 3.1 下載與解壓產物安全驗證 (`act_download` & `act_reload`)
- **Zip 完整性雙重校驗**：從遠端或本地 Provider 拉取套件至 `module.mirror://{mod}/{ver}.zip` 時，強制執行 `zipfile.is_zipfile()` 與 `zf.testzip()` CRC 校驗，損毀檔案立即清除並阻斷安裝。
- **Zip Slip 路徑穿越防護**：解壓至 `module://{mod}/` 前，逐一校驗壓縮包內所有成員路徑 `target_path.startswith(real_dst_abs + os.sep)`，嚴防惡意 `../` 逃逸覆寫外部檔案。

### 3.2 模組組態遞迴原地增量補齊 (`_deep_infill_dict`)
- **無損增量補齊**：當模組於新版本 `configurable/`（或預設組態模板）新增欄位時，`act_deploy_configs_from_modules` 會對 `config://{mod}/config.project.json` 與 `config.local.json` 執行遞迴比對，**僅自動補齊缺失鍵值，使用者既有已調整之設定值 100% 保持不變**。
- **跨層優先級感知**：在補齊 `config.local.json` 時，若對應鍵已存在於 `config.project.json`，則跳過重複寫入，維持組態矩陣乾淨正交。
- **運行端模板物理剝除**：組態補齊完成後，無條件從 `module://{mod}/` 實體刪除 `configurable/` 目錄與 `config.*.json` 模板，確保運行空間 100% 純程式碼化。

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
