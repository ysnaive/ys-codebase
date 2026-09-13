# 實作計畫與定稿審查書 (Implementation Plan & Review)

> 功能名稱：sub_02_host_and_core_distribution_lifecycle  
> 建立日期：2026-09-13  
> 所屬主計畫：2026_09_13_1648_downstream_feedback_remediation  
> 狀態：Confirmed  
> 模板版本：v1.4  

---

## 1. 交叉驗證檢查清單 (Cross-Validation Checklist)

- [x] **需求對齊**：FR-01 ~ FR-05 在 API 規格書中均有精確簽名與實作契約
- [x] **邊界防護**：EC-01 ~ EC-05 均有對應防禦（離線降級、ast.parse 語法驗證、備份防護與原子替換）
- [x] **依賴純淨**：符合 NFR-01（100% Python 標準函式庫，零額外依賴）
- [x] **追溯鏈剛性**：P00 語意 ➔ FR/EC ➔ DR ➔ API 簽名 ➔ 任務拓撲 100% 閉環

---

## 2. 知識庫文檔衝擊與交付規劃 (Documentation Impact Plan)

| 維度 | 文件路徑 | 變更類型 | 交付內容與重點 |
| :--- | :--- | :---: | :--- |
| **模組手冊** | `source/core/README.md` | Modify | 補充 `init --fix` 自癒修復操作範例與 `self-update` 指令說明 |
| **發布日誌** | `CHANGELOG.md` | Modify | 記錄本子計畫修復摘要 (發布前追加) |

---

## 3. 架構靈魂拷問 (Stress Test & Resilience Review)

> ❓ **尖銳問題 1**：當使用者在一個完全沒有網路且沒有本地 mirror 的環境下執行 `init --fix` 時，系統是否會意外清空或毀損使用者的舊設定？  
> 💡 **防護解法**：自癒修復在確認下載或複製成功新 core 壓縮包前，絕不觸碰現有磁碟上的設定檔或檔案；下載失敗立即中斷並保留所有原始檔案與狀態。

> ❓ **尖銳問題 2**：`self-update` 升級自身如果中途被強制中斷（如使用者 Ctrl+C），會不會導致 `yscb.py` 遺失成為 0 位元組空檔？  
> 💡 **防護解法**：遵循「下載寫入 `.tmp` ➔ 原檔複製為 `.bak` ➔ `os.replace` 原子替換」三段式防禦；`os.replace` 為 OS 原生 POSIX / Windows 原子操作，絕不會產生空檔。

---

## 4. 實作任務清單 (Task Breakdown & Topological Sequence)

- [ ] **TASK-01**：修改 `yscb.py`，更新 `DEFAULT_PROVIDER_URL`，實作 `_resolve_self_update_target_url` 與 `cmd_self_update`，恢復 `main()` 派發
- [ ] **TASK-02**：修改 `yscb.py`，實作自包含版本探測 `_discover_latest_core`，重構 `cmd_init` 支援預設 `".yscb"`、`--fix` 自癒修復與連鎖自動觸發 `core reload`
- [ ] **TASK-03**：同步修改 `yscb.py` 與 `source/core/core/installer.py`，將 `yscb.py.bak` 與 `*.bak` 納入 `INTERNAL_IGNORE_PATTERNS`
- [ ] **TASK-04**：修改 `source/core/core/update_checker.py` 實作 `invalidate_cache`，並於 `installer.py` 中的 `cmd_install` 與 `cmd_update` 成功後調用
- [ ] **TASK-05**：編寫單元測試套件 `source/core/tests/test_distribution_lifecycle.py`，完整覆蓋 FT-01 ~ FT-08
- [ ] **TASK-DOC**：更新 `source/core/README.md` 說明 `init --fix` 與 `self-update`

---

## 5. 決策定稿 (Confirmed Decision Records)

- **[P04:DR-01] 零第三方依賴自舉定稿**：確認 `yscb.py` 內部之版本探測與 self-update 均以 Python 標準庫實作，保證在未安裝任何模組的乾淨環境下也能 100% 成功執行。
- **[P04:DR-02] 自癒連鎖 Reload 剛性定稿**：確認 `init --fix` 執行成功時，以 `return dispatch_module("core", ["reload"])` 剛性連鎖刷新，確保環境即刻就緒。
