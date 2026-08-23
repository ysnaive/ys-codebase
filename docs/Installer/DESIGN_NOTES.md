---
target: "Core/Installer/DesignNotes"
doc_type: "design_notes"
status: "active"
source_paths:
  - "yscb_installer.py"
related_docs:
  - "./README.md"
last_updated: "2026-08-22"
---

# Installer 工程妥協與設計筆記 (Design Notes)

記錄 `yscb_installer.py` 在開發與演進過程中的非直觀設計考量、跨平台邊界條件與妥協記錄。

---

## 📌 設計考量與坑點記錄

### 1. Windows 控制台 UTF-8 編碼保護
> [!CAUTION]
> Windows 預設的 PowerShell / CMD 控制台常使用 `cp950` 或 `cp437`，在輸出繁體中文、表格邊框或特殊符號時容易引發 `UnicodeEncodeError` 導致終端崩潰。

- **解決方案**：
  在腳本最頂部強制透過 `sys.stdout.reconfigure(encoding='utf-8', errors='replace')` 重新配置編碼，即使在極端編碼環境下亦自動以替代字元安全輸出，絕不崩潰。

---

### 2. 堅持 Zero External Dependency (純標準庫)
> [!NOTE]
> 雖然使用 `click` 或 `rich` 可以輕易做出華麗的終端 UI，使用 `gitpython` 能簡化 Git 調度，但這會強迫使用者在乾淨環境下執行 `pip install`，破壞了「5秒即插即用」的核心定位。

- **妥協與實踐**：
  全部使用標準庫 `argparse` 與 `subprocess` 封裝，手刻格式化表格與說明手冊，換取 100% 免安裝環境依賴的極致相容性。

---

### 3. Windows 長路徑與 Git 權限 (Long Paths)
> [!WARNING]
> Windows 預設的 260 字元路徑限制可能導致深層目錄 checkout 失敗。

- **最佳實踐建議**：
  在 Git 交互時建議確保 `core.longpaths=true`，並於 `yscb_installer.py` 處理遞迴目錄清理時使用 `ignore_errors=True` 避免被 Windows 檔案鎖死阻斷。

---

### 4. 專案適配 SemVer 剛性映射 (DN-04)
> [!NOTE]
> 傳統語意化版本（SemVer）主要針對函式庫 API 破壞性。在工具庫生態中，我們對此進行專案特化：
> - **Major**：使用者角度不可調和之重大架構異動（通常不觸發）。
> - **Minor**：需要執行資料結構或設定檔遷移 (`_migration.py`) 的代際更新。
> - **Patch**：內部最佳化、缺陷修復或向後相容的功能擴充。

---

### 5. 五階段升級事務與快照回滾策略 (DN-05)
> [!CAUTION]
> 模組升級跨代時，若在執行 `_migration.py` 或覆寫檔案途中遭遇異常，模組目錄可能處於不一致的「半升級損毀狀態」。

- **防禦機制**：
  升級前於 Stage 2 強制建立舊版快照備份於 `.yscb_cache/backup/`。一旦後續階段（如資料遷移）拋出例外，立即自動觸發 `_rollback_snapshot()` 完整復原，達成具備事務性保證的無損升級。

---

### 6. Windows 執行中單檔起手腳本原子自更新防護 (DN-06)
> [!IMPORTANT]
> 在 Windows 作業系統中，若 Python 進程直接對自身正在執行的 `.py` 檔案進行二進位寫入覆蓋，會引發 Windows File Lock `PermissionError`。

- **解決方案**：
  在 `installer self-update` 時，新腳本一律先寫入臨時檔案 `yscb_installer.tmp`，隨後透過底層 C API 支援的 `os.replace`進行單一原子指標替換，達成 100% 穩定免重啟自舉更新。

---

### 7. 安裝期生命週期連動廣播與 build 嚴格排除鐵律 (DN-07)
> [!CAUTION]
> 在模組建置階段 (`installer build`)，產物必須維持 100% 純淨與環境無關。若在建置期調用連動 Hook，會導致本機工作區的暫態狀態被固化進發布產物中。

- **架構約束**：
  - `_broadcast_modules_changed()` 僅在 `install`、`pull`、`remove` 整批事務結尾派發一次。
  - `build` 指令嚴格排除廣播觸發，確保建置產物零連動副作用。

---

### 8. SOPSynthesizer Slot 標記剝除與零殘留防呆 (DN-08)
> [!IMPORTANT]
> 主 SOP 在 `commands/` 基準庫中包含 `<!-- YSCB_SLOT:... -->` 標記供外掛注入。若未命中的標記殘留在最終交付文檔中，將嚴重影響排版專業度與 LLM 的注意力聚焦。

- **防呆設計**：
  動態合成引擎在輸出具體化文檔（`workflows/*.md` 及 `.agents/workflows/*.md`）前，強制執行 `SOPSynthesizer.strip_slot_markers()` 正則清除所有 Slot 標記，保證對外文檔 100% 純淨無語法殘留。

---

### 9. 主執行器三位一體公理與自更新定位 (DN-09)
> [!IMPORTANT]
> [ARCH:DR-EXEC-01] 定義：`yscb_config.json`、`yscb_installer.py` 與 `yscb_cli.py` 為本專案三大核心主執行器檔案，必須共生於同一實體目錄下。

- **邊界約束**：
  - `installer self-update` / `cli` 自更新時，強制以當前正在執行的腳本實體檔案位置為主進行原子覆蓋。
  - 其餘所有受管理資產（`modules/`, `source/`, `build/`, `.yscb_cache/`）100% 依 `yscb_config.json` 宣告之 `paths.yscb_root` 運行，達成完美的執行器與資產空間解耦。

---

### 10. 遠端 Git 鏡像快取目錄空間隔離 (DN-10)
> [!CAUTION]
> [ARCH:DR-CACHE-02] 若將遠端 Git 倉庫直接 Clone 至 `.yscb_cache` 根目錄，會導致 `.yscb_cache/modules/` 與 `.yscb_cache/backup/` 被 Git 視為 Working Tree Untracked Files；在 `git pull` 失敗觸發 `sync_cache(force_refresh=True)` 時引發 `shutil.rmtree` 將所有模組快取與歷史快照備份一併抹除。

- **解決方案**：
  `GitRemoteClient.cache_dir` 強制隔離收斂至 `yscb://.yscb_cache/mirror/`，使 Git 鏡像與模組執行期快取（`cache://`）、備份快照（`backup/`）及暫存區（`temp://`）達成 100% 空間職責分離。


