# 空間管理與雙階增量比對架構 (Space & Fingerprint Architecture)

> 本文件說明 `knowledge-db` 模組的空間管理聚合引擎、全空間聯集模型與雙階增量指紋比對機制。

---

## 1. 空間管理架構 (Space Management)

### 1.1 雙軌來源聚合 (Dual-Track Aggregation)
系統支援兩條空間來源聚合軌道：
1. **軌道 ① 模組聯動注入 (Module Contributes)**：搜集所有安裝模組之 `contributes.knowledge-db.json` 或 `manifest.json`。
2. **軌道 ② 2x2 組態矩陣宣告 (Config Matrix)**：讀取 `config.project.json` (專案層級) 與 `config.local.json` (本機層級)。

### 1.2 全空間聯集處理模型 (Union Scope Model)
`knowledge-db` 廢除單一 `default_space` 的限制，全系統以所有註冊空間之聯集作為全域處理範圍：
$$\text{Scope} = \bigcup_{i=1}^{N} \text{Space}_i$$

---

## 2. 雙階增量指紋比對引擎 (Two-Stage Fingerprint Engine)

為兼顧比對精確度與磁碟 I/O 效能，`FingerprintScanner` 採用雙階增量比對機制：

```mermaid
flowchart TD
    File([來源檔案]) --> CheckCache{舊指紋存在?}
    CheckCache -- No --> Stage2[Stage 2: 讀取內容計算 SHA1]
    Stage2 --> MarkAdded[標記為 ADDED]
    
    CheckCache -- Yes --> Stage1{Stage 1: mtime 與 size 完全一致?}
    Stage1 -- Yes --> FastUnchanged[標記為 UNCHANGED<br/><b>0 次內容讀取, 0 次 SHA1 計算</b>]
    Stage1 -- No --> Stage2Compare[Stage 2: 讀取內容計算 SHA1]
    
    Stage2Compare --> CompareSHA1{SHA1 一致?}
    CompareSHA1 -- Yes --> TouchUpdate[更新快取 mtime<br/>標記為 UNCHANGED]
    CompareSHA1 -- No --> MarkModified[標記為 MODIFIED]
```

### 2.1 強韌性與自癒機制 (Resilience & Self-Healing)
- **快取原子寫入**：指紋存儲採用 `NamedTemporaryFile` + `os.replace`，防止中斷導致 `fingerprints.json` 損毀。
- **快取損毀自癒**：當 `fingerprints.json` 發生損毀時，系統記錄 Warning 並自癒降級為全量掃描，寫入後自動修復。
- **無效路徑寬容**：個別來源路徑不存在時安全略過並記錄 Warning，不阻斷其他空間的正常處理。
