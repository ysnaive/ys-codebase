# 技術路線圖：獨立 Server 模組與常駐服務守護架構 (Roadmap)

> 主題：獨立 Server 模組與常駐服務守護架構  
> 歸檔日期：2026-09-06  
> 狀態：Proposed  

---

## 1. 問題陳述與模組定位 (Problem & Module Positioning)

### 1.1 痛點現象
在 YS-Codebase 生態系中，隨著模組能力擴展，多個領域模組相繼產生常駐背景任務需求（例如 `knowledge-db` 的熱重載檔案監聽與索引增量構建、潛在的事件總線分發、快取預熱或即時日誌轉發）。

若讓各領域模組自行實作 Daemon，將導致以下架構缺陷：
1. **進程管理與平台代碼高度重複**：每個模組都需要各自處理 PID 檔案鎖、Windows 視窗分流、POSIX setsid、超時熔斷與進程樹強殺。
2. **多重孤立進程與資源浪費**：多個模組各自拉起常駐進程，工作管理員充滿多個未命名的 Python 背景進程，難以統一監控與處決。
3. **殭屍進程與死鎖風險倍增**：缺乏統一的 Supervisor 管理各背景進程的心跳與自癒機制。

### 1.2 獨立一級模組定位 (First-Class Module Positioning)
`server` 模組定位為 **Layer 1 平台通用服務模組 (Platform Service Module)**：
- **職責單一**：專注於全生態系的常駐服務排程、Worker 進程池生命週期管理、IPC 通訊與健康檢查。
- **依賴分層純粹**：`server` 模組依賴 `core`（消費 `core.platform` 之進程原語與跨平台鎖），而 `core` 不依賴 `server`。
- **隨需啟動**：不需要常駐服務的單純 CLI 操作（如 `config`、`plan`、`dev test`）完全不啟動 `server`，保持極致輕量。

### 1.3 領域模組解耦說明
本路線圖專注於通用 `server` 模組的 Supervisor 架構、Worker 擴充協議與生命週期中樞，**暫不耦合 `knowledge-db`**。`knowledge-db` 在自身架構重構完成後，再將其既有 `HotReloadServer` 作為註冊 Worker 接入遷移。

---

## 2. 候選架構方案對比 (Candidate Solutions)

| 方案 | 運作機制 | 優點 (Pros) | 缺點 / 成本 (Cons) | 適用度評級 |
| :--- | :--- | :--- | :--- | :---: |
| **方案 1：Master-Worker 單一守護中樞<br/>(Centralized Supervisor)** | `server` 模組作為唯一宿主守護進程，各業務模組以「Worker Plugin」形式註冊掛載至進程池中。 | 1. 整個專案僅需 1 個常駐進程，資源極省。<br/>2. 集中日誌、統一命令控制 (`python yscb.py server ...`)。<br/>3. 一鍵啟動/停止所有背景服務。 | 需設計標準 Worker 生命週期介面與隔離機制。 | ⭐️⭐️⭐️⭐️⭐️ |
| **方案 2：各模組獨立 Daemon<br/>(現狀模式)** | 各模組自管自的 `daemon.py` 與 PID 檔。 | 開發初期簡單，模組各自獨立。 | 進程重複、代碼重複、跨平台除錯成本呈乘法倍增。 | ⭐️⭐️ |
| **方案 3：依賴 OS 原生服務<br/>(Systemd / Win32 Service)** | 將背景服務註冊為 Windows Service 或 Linux systemd unit。 | 系統級開機自啟與權限。 | 開發容器（Docker）相容性極差，且需要高權限 (root / admin)，破壞沙盒純粹性。 | ⭐️ |

---

## 3. 多維度綜合可行性評估 (Multi-Dimensional Feasibility)

| 評估維度 | 評估指標 | 說明 |
| :--- | :---: | :--- |
| **進程可觀測性** | 極高 | 透過 `python yscb.py server status` 一覽全生態系所有 Worker 狀態與資源佔用 |
| **系統健壯性** | 極高 | 單一 Worker 崩潰由 Supervisor 自動重啟，不影響其他 Worker 運行 |
| **跨平台維護性** | 高 | 跨平台底層完全委託 `core.platform`，`server` 模組專注排程與通訊邏輯 |
| **落地成本** | 中 | 需規劃標準 Worker 介面與 IPC（本地 Socket / HTTP / 檔案映射） |

---

## 4. 架構規格與 Worker 註冊契約 (Architecture & Worker Protocol)

### 4.1 標準 Worker 介面契約
```python
from abc import ABC, abstractmethod

class BaseServerWorker(ABC):
    @property
    @abstractmethod
    def name(self) -> str:
        """Worker 唯一名稱 (例: 'kdb-watcher')"""
        pass

    @abstractmethod
    def start(self, context: Any) -> None:
        """非阻塞啟動工作執行緒或子進程"""
        pass

    @abstractmethod
    def stop(self) -> None:
        """優雅停止"""
        pass

    @abstractmethod
    def health_check(self) -> bool:
        """健康檢查探針"""
        pass
```

### 4.2 統一 CLI 操作介面
```bash
python yscb.py server start [--console]   # 啟動守護中樞
python yscb.py server stop                # 優雅停止所有背景服務
python yscb.py server status              # 檢視 Supervisor 與所有 Worker 運行狀態
python yscb.py server restart             # 熱重啟全生態系背景服務
```

---

## 5. 實施路線圖與里程碑 (Roadmap & Stages)

### 5.1 近期策略 (Current Strategy)
作為獨立模組之中長期演進藍圖儲備，優先於 `core.platform` 完工後啟動。

### 5.2 實施步驟 (Implementation Stages)
1. **Stage 1 (Server 模組建立與骨架)**：透過 `python yscb.py dev create server` 建立標準模組目錄結構。
2. **Stage 2 (Supervisor 核心與 Worker 契約)**：實作 Master 守護進程，定義 Worker 註冊機制與 CLI 基礎命令。
3. **Stage 3 (健康檢查與自癒熔斷)**：導入定期 Heartbeat 探針與崩潰自動重啟防護。
4. **Stage 4 (業務模組對接)**：供 `knowledge-db` 等模組將獨立的 Daemon 遷移為標準 Worker。
