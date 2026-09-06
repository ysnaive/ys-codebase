# 計畫變更紀錄 (Changelog)

> 功能名稱：knowledge-db 守護進程啟動死鎖、即時日誌與索引延遲修復  
> 建立日期：2026-09-06  
> 所屬主計畫：無  
> 狀態：Completed  

> 模板版本：v1.1  

---

> 按時間倒序排列。每條記錄包含日期時間、類型標籤、摘要。

## 變更紀錄

| 日期時間 | 類型 | 摘要 |
| :--- | :---: | :--- |
| 2026-09-06 16:06 | `PHASE` | FT-2 實作與驗證 100% 通過（159/159 單元測試 Passed，實機單例複用與 JIT 跳過驗證完成），進入 FT-3 結案審查 (狀態：`Completed`) |
| 2026-09-06 16:00 | `DECISION` | [FT-1:DR-02] 針對 Windows Job Object Breakaway 限制，於 ensure_running 引進 WMI (Win32_Process.Create) 作為首選進程委託機制，並以 --daemon-process 命令列參數作為跨進程環境解耦防呆雙保險 |
| 2026-09-06 15:55 | `PHASE` | 開立 Fast Track 計畫目錄，初始化 fast_track_plan.md 與 changelog.md (狀態：`Confirmed`) |
| 2026-09-06 15:52 | `DECISION` | [FT-1:DR-01] 確立三軸修復架構：1) hook 排除 daemon 子命令與環境變數防止遞迴死鎖；2) ensure_running 改採 0.05s 高頻短輪詢非阻塞健康嗅探，廢除 8 秒誤殺；3) _setup_logger 支援 stdout 串流與 knowledge_db 全局日誌攔截 |
