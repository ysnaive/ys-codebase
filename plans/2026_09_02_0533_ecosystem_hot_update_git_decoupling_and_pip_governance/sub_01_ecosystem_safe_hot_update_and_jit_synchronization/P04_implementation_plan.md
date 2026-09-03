# 實作計畫與定稿審查書 (Implementation Plan & Review)

> 功能名稱：ecosystem_safe_hot_update_and_jit_synchronization  
> 建立日期：2026-09-03  
> 所屬主計畫：2026_09_02_0533_ecosystem_hot_update_git_decoupling_and_pip_governance  
> 狀態：Confirmed  
> 模板版本：v1.4  

---

## 1. 交叉驗證檢查清單 (Cross-Validation Checklist)

- [x] **需求對齊**：FR-01 ~ FR-04 在 API 規格書中均有對應介面與簽名契約。
- [x] **邊界防護**：EC-01 ~ EC-05 均定義明確之例外防禦策略（原子替換、靜默降級、跳過損毀 Donor）。
- [x] **依賴純淨**：100% 採用純 Python 標準庫，Clean 狀態比對耗時 $\le 2\text{ms}$，符合 NFR 指標約束。

---

## 2. 知識庫文檔衝擊與交付規劃 (Documentation Impact Plan)

| 維度 | 文件路徑 | 變更類型 | 交付內容與重點 |
| :--- | :--- | :---: | :--- |
| **模組手冊** | `docs/core/README.md` | Modify | 補充 `core.contributes` JIT 自愈機制與 `UpdateChecker` 組態說明 |
| **模組手冊** | `docs/agents-workflow/README.md` | Modify | 補充 JIT Release Target 投影自動同步行為 |
| **模組手冊** | `docs/dev/README.md` | Modify | 補充 `dev test --sync` 快捷直裝閉環用法 |
| **設計決策** | `docs/core/DESIGN_NOTES.md` | Modify | 登記 JIT 快照與 12hr 來源節流探測工程防禦決策 |

---

## 3. 架構靈魂拷問 (Stress Test & Resilience Review)

> ❓ **尖銳問題 1**：當多個進程同時調用 `core.contributes.get()` 且剛好遇到檔案變更時，如何避免重入死鎖或檔案競爭寫入？  
> 💡 **防護解法**：`scan_and_inject()` 物化寫入與 `contributes.meta.json` 更新採用嚴格的原子寫入策略（先寫入 `.tmp` 檔案，再調用 `os.replace`），即使有並發進程同時寫入，讀取端也永遠只會讀到完整的原子快照版本。

> ❓ **尖銳問題 2**：若使用者的 Provider 伺服器掛掉或處於無網路的離線開發環境，UpdateChecker 是否會導致 CLI 卡頓？  
> 💡 **防護解法**：設置 2.0 秒超短逾時，且所有網路異常（`URLError`, `TimeoutError`, `socket.timeout`）皆被 `try...except` 靜默捕獲，失敗時自動將 `last_checked_at` 更新為當前時間，確保接下來的 12 小時內零重試、零阻塞。

> ❓ **尖銳問題 3**：`agents-workflow` JIT 物化是否會在大專案中造成檔案不斷被覆寫而觸發外部 IDE/watchers 的狂暴重新索引？  
> 💡 **防護解法**：`ReleasePublisher` 實作了 Stage 0 來源指紋短路檢查（SHA-256）與 Stage 4 內容二進位比對，僅在來源實質發生變更且內容有差異時才執行檔案寫入，Clean 狀態下跳過任何磁碟 I/O。

---

## 4. 實作任務清單 (Task Breakdown & Topological Sequence)

- [ ] **TASK-01**：在 `source/core/core/contributes.py` 實作 JIT 嗅探閘門與快照自愈邏輯
- [ ] **TASK-02**：在 `source/core/core/update_checker.py` 實作 12 小時節流探測器與提示 API
- [ ] **TASK-03**：在 `source/agents-workflow/agents_workflow/scripts/cli.py` 整合 JIT release 前置管線
- [ ] **TASK-04**：在 `source/dev/dev/tester.py` 整合 `--sync` 旗標與提示
- [ ] **TASK-05**：編寫單元測試（`test_contributes_jit.py`、`test_update_checker.py`、`test_jit_release.py`、`test_tester_sync.py`）
- [ ] **TASK-DOC**：交付 Docstrings 與相關 docs 文檔

---

## 5. 決策定稿 (Confirmed Decision Records)

- **[P04:DR-01]** 採用 JIT 輕量快照嗅探 + 12 小時節流來源版本探測，零背景常駐進程，100% 純標準庫。
- **[P04:DR-02]** 快照與更新快取均採用 `.tmp` 搭配 `os.replace` 原子替換，保障並發安全。
- **[P04:DR-03]** Dogfooding 四步閉環加固：`dev test --sync` 在單元與整合測試 100% 通過時自動安裝 `@build`。
