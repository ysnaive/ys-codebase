# 需求規格說明書 (Requirements Specification)

> 功能名稱：終端編碼防護、舊版殘留清理、特殊字元徹底捨棄與測試狀態閉環 (sub_05)  
> 建立日期：2026-09-12  
> 所屬主計畫：2026_09_07_0831_quality_update  
> 狀態：Confirmed  
> 依據 P00：[P00_discuss.md](./P00_discuss.md)  
> 模板版本：v1.5  

---

## 1. 功能需求清單 (Functional Requirements)

| 需求編號 | 需求名稱 | 詳細規格描述 | 優先級 | 對應 P00 語意 |
| :--- | :--- | :--- | :---: | :--- |
| **FR-01** | 全生態系特殊字元與 Emoji 徹底捨棄 | 全面移除 `core.commands.help`、CLI 進入點、`dev.checker`、測試日誌輸出中所有 Emoji 與特殊符號（如 `🟢`、`🟡`、`🔴`、`🚨`、`🛡️`、`✨`、`📦` 等），全數統一改採標準方括號 ASCII / Plain Text 標記（如 `[SAFE]`、`[CONDITIONAL]`、`[GATED]`、`[PASS]`、`[WARN]`、`[ERROR]`、`[INFO]`），徹底消除終端 Code Page 轉換風險。 | P0 | [P00:DR-01] |
| **FR-02** | Windows 終端 UTF-8 編碼主動重組與容錯 | 在 `yscb.py` 進入點頂層與 `core.commands.dispatcher` 派發前，若偵測為 Windows 平台，主動呼叫 `sys.stdout.reconfigure(encoding='utf-8', errors='replace')` 與 `sys.stderr.reconfigure(encoding='utf-8', errors='replace')`，保證終端永遠不因輸出字元崩潰。 | P0 | [P00:DR-02] |
| **FR-03** | 舊版 `contributes.format.md` 殘留徹底清理 | 刪除 `source/core/contributes.format.md`、`source/server/contributes.format.md` 與 `source/knowledge-db/contributes.format.md`，統一生態系 Ingress/Egress 為 `_format.json` 與 `_manifest.md`。 | P0 | [P00:DR-03] |
| **FR-04** | `knowledge-db/configurable/` 檔案命名標準化 | 將 `source/knowledge-db/configurable/contribute.json` 重新命名為 `config.project.json`（或符合 `config.*.json` 約定），消除 `dev check` 非標準模板告警。 | P0 | [P00:DR-03] |
| **FR-05** | 歷史測試 `self.mark_passed()` 狀態全面閉環 | 為 `agents-workflow` (44 個測試) 與 `core` (17 個測試) 補齊 `self.mark_passed()` 顯式調用，使全生態系 511 個測試在報告中 100% 呈現 Passed（0 Unknown / 0 Failed）。 | P0 | [P00:DR-03] |

---

## 2. 邊界與異常情況 (Edge Cases & Failure Modes)

| 邊界編號 | 情境說明 | 預期防禦與處理行為 |
| :--- | :--- | :--- |
| **EC-01** | Python 3.10 以下或舊終端不支援 `reconfigure` | `yscb.py` 以 `hasattr(sys.stdout, 'reconfigure')` 與 `try...except` 安全防護，不拋出任何異常。 |
| **EC-02** | 特殊 Unicode 字符於未知 locale 輸出 | `errors='replace'` 自動以 `?` 取代不可編碼字元，絕不拋出 `UnicodeEncodeError` 阻斷進程。 |
| **EC-03** | 測試在 Windows 高並發平行沙盒環境執行 | 效能量測門檻合理寬放至容忍 CPU 瞬時波動（如 5ms），確保在沙盒測試 100% 穩定綠燈。 |

---

## 3. 非功能需求 (Non-Functional Requirements)

| 需求編號 | 類別 | 指標與量化約束 |
| :--- | :--- | :--- |
| **NFR-01** | 跨平台相容性 | 100% 相容 Windows（CP950、CP437、UTF-8）、Linux (UTF-8) 與 macOS 終端。 |
| **NFR-02** | 依賴約束 | 0 第三方依賴，100% 純 Python 標準庫。 |
| **NFR-03** | 靜態合規與測試指標 | `dev check --all` 達成 0 Failed / 0 Warning；`dev test --all` 達成 511/511 100% Passed (0 Unknown / 0 Failed)。 |

---

## 4. 知識庫與踩坑紀錄查閱 (Known Gotchas & CAUTIONs)

- **`[!NOTE]`**：Windows 終端在預設 `chcp 950`（繁體中文大五碼）時，若直接向 `sys.stdout` 寫入 4-byte UTF-8 Emoji（如 `🟢` \U0001f7e2），Python 解譯器會嘗試調用 msvcrt 進行編碼轉換並拋出 `UnicodeEncodeError`。徹底移除 Emoji 並結合 `reconfigure` 是最乾淨的工業級解法。
