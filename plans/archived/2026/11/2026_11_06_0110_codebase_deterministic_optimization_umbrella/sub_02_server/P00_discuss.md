# 需求討論說明書 (Semantic Requirements Discovery)

> 功能名稱：server 模組業務與測試代碼確定性優化 (server Deterministic Optimization)
> 建立日期：2026-11-06
> 所屬主計畫：2026_11_06_0110_codebase_deterministic_optimization_umbrella
> 狀態：Confirmed
> 模型：Unknown
> 計畫類型：Refactoring
> 模板版本：v1.2

---

## 1. 使用者原始需求與意圖 (User Intent)

- **原始陳述**：針對 `server` 模組之業務程式碼（`__init__.py`、`config.py`、`logger.py`、`master.py`、`service.py`、`streamer.py`、`watcher.py`、`worker.py`、`scripts/cli.py`）與測試程式碼（`tests/test_server.py`、`tests/test_server_config.py`、`tests/test_server_logging.py`）執行五步盲眼子代理閉環優化。
- **核心目標**：對外 SDK/CLI 嚴守 Mode B 相容，對內採 Mode A 消除冗餘結構與測試病灶，並將原業務設計疏失記錄於 `issue_report.md`。
- **既有組件復用與查重 (Reuse Discovery)**：復用 `server` 雙段式握手、IPC Socket 通訊與日誌輪替基礎設施。
- **邊界排除 (Explicitly Excluded)**：原業務設計疏失僅記錄於 `issue_report.md`，不於本次重構中修改外部行為。
- **架構影響範圍**：`ys_codebase/source/server/` 下之業務與測試檔案。

---

## 2. 核心討論與決策紀錄 (Discussion & Decisions)

- **[P00:DR-01] 雙目標五步盲眼閉環**：分別針對業務代碼（D1~D5, S1~S6）與測試代碼（T-01~T-06, D1~D5）執行 A->B->C->D->E 閉環，最多三輪熔斷。

---

## 3. 開放議題與確認紀錄

- 無開放議題，直接啟動 Loop 1。
