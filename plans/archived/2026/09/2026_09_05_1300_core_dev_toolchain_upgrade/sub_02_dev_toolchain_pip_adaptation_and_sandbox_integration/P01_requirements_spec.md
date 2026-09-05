# 需求規格說明書 (Requirements Specification)

> 功能名稱：dev_toolchain_pip_adaptation_and_sandbox_integration  
> 建立日期：2026-09-05  
> 所屬主計畫：2026_09_05_1300_core_dev_toolchain_upgrade  
> 狀態：Confirmed  
> 依據 P00：[P00_discuss.md](./P00_discuss.md)  
> 模板版本：v1.5  

---

## 1. 功能需求清單 (Functional Requirements)

| 需求編號 | 需求名稱 | 詳細規格描述 | 優先級 | 對應 P00 語意 |
| :--- | :--- | :--- | :---: | :--- |
| **FR-01** | Build 版 Pip 相依性自動適配 | 在 `SandboxProvisioner` 新增 `adapt_build_pip_dependencies`，掃描 build 版（或源碼）`manifest.json` 中的 `pip_dependencies`，調用 `core.PipManager` 在宿主微環境完成套件物化。 | P0 | [P00:DR-01] |
| **FR-02** | 沙盒微環境跨平台雙軌投影 | 在 `SandboxProvisioner.create_sandbox` 中，若宿主微環境存在，自動建立至沙盒 `engine/.venv` 的目錄投影；Windows 使用 NTFS Junction，POSIX 使用 Symlink。 | P0 | [P00:DR-02] |
| **FR-03** | 跨平台平滑降級防禦 | 若 Junction 或 Symlink 建立因底層檔案系統或權限拋出例外，自動平滑降級為在沙盒 `engine/.venv` 建立 site-packages 並寫入 `.pth` 路徑指標檔指向宿主 site-packages。 | P0 | [P00:DR-02] |
| **FR-04** | 沙盒安全銷毀防護 | 加固 `SandboxProvisioner.cleanup_sandbox`，若 `engine/.venv` 為 Junction 或 Symlink，在遞迴刪除沙盒前先安全斷開連結，絕不穿透刪除宿主微環境內容。 | P0 | [P00:DR-03] |
| **FR-05** | 靜態合規性檢核擴充 (`dev check`) | 在 `Checker._check_manifest` 中新增 `_check_pip_dependencies` 檢查，驗證 `pip_dependencies` 必須為字典，鍵名為非空套件名稱，約束必須為字串或 None。 | P1 | [P00:DR-04] |

---

## 2. 邊界與異常情況 (Edge Cases & Failure Modes)

| 邊界編號 | 情境說明 | 預期防禦與處理行為 |
| :--- | :--- | :--- |
| **EC-01** | 宿主環境尚無 `.venv` 目錄時建立沙盒 | 安全略過投影動作，不拋出未捕獲例外，沙盒正常建立。 |
| **EC-02** | 模組無任何 `pip_dependencies` 宣告時執行適配 | 安全回傳 `[]`，不觸發任何額外 subprocess 或 pip 安裝動作。 |
| **EC-03** | 沙盒目錄重複建立或殘留有斷鏈之 Junction/Symlink | 安全探測 `os.path.islink` / `os.path.isdir` 並移除殘留節點後重新建立。 |
| **EC-04** | `manifest.json` 中 `pip_dependencies` 格式非法（如為 list, int, bool 或鍵為空） | `dev check` 回報 `CheckIssue(severity=FAIL, category=MANIFEST)` 並阻止發布。 |

---

## 3. 非功能需求 (Non-Functional Requirements)

| 需求編號 | 類別 | 指標與量化約束 |
| :--- | :--- | :--- |
| **NFR-01** | 效能 / 資源 | 微環境投影耗時 $< 5\text{ms}$，磁碟空間增量 0MB（零拷貝）。 |
| **NFR-02** | 跨平台相容性 | 100% 相容 Windows NTFS、POSIX Linux / macOS 與 Docker 虛擬掛載環境，全套測試 100% 通過。 |

---

## 4. 知識庫與踩坑紀錄查閱 (Known Gotchas & CAUTIONs)

- **`[!NOTE]`**：Windows `_winapi.CreateJunction(src, dst)` 的參數順序為 `(src, dst)`，且 `src` 必須為絕對路徑；銷毀時若是 Junction 必須使用 `os.rmdir` 或 `os.unlink`，Python 3.8+ 的 `shutil.rmtree` 雖不穿透 Junction，但顯式斷開更加安全。
