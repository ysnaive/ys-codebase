# 需求討論說明書 (Semantic Requirements Discovery)

> 功能名稱：dev_toolchain_pip_adaptation_and_sandbox_integration  
> 建立日期：2026-09-05  
> 所屬主計畫：2026_09_05_1300_core_dev_toolchain_upgrade  
> 狀態：Confirmed  
> 計畫類型：Feature  
> 模板版本：v1.2  

---

## 1. 使用者原始需求與意圖 (User Intent)

- **原始陳述**：
  - 「因近期 core 模組升級了 pip 相依性支援，須同步更新 dev 工具練，core 須開放相關工具 SDK，dev 需支援建置虛擬基環境之前，對當前 build 版做 pip 適配」
  - 「授權啟動第二個子計畫」
- **核心目標**：
  1. **建置虛擬基環境前之 Build 版 Pip 相依性適配**：在 `SandboxProvisioner` 或跑測預構建流程中，建置沙盒虛擬基環境前自動掃描當前 build 版（`module.build://` 或源碼）之 `manifest.json`，透過 `core.PipManager` 解析規格並在微環境中物化安裝，使測試相依性預先就緒。
  2. **沙盒微環境高保真繼承 (Zero-Copy .venv Projection)**：在 `SandboxProvisioner.create_sandbox` 中，將宿主微環境 (`host_yscb/.venv`) 以 Windows Junction / POSIX Symlink 方式秒級對接至沙盒 `engine/.venv`，達成零拷貝、零磁碟浪費且 100% 繼承已安裝之 pip 套件。
  3. **沙盒安全銷毀防護**：加固 `SandboxProvisioner.cleanup_sandbox`，銷毀沙盒時優先斷開 `.venv` 節點，防止誤刪宿主真實現有微環境。
  4. **靜態合規性防禦 (`dev check`)**：在 `Checker._check_manifest` 中新增 `pip_dependencies` 格式檢驗，阻斷無效型態（非 dict）、非法套件名稱或無效字串宣告。
  5. **全套測試與架構文檔**：新增單元測試覆蓋 Pip 適配、沙盒 .venv 穿透與合規檢查，並更新 `docs/dev/testing_guide.md`。
- **邊界排除 (Explicitly Excluded)**：
  - 不更動 `core` 模組底層 Wheel-Only 安全原則與安裝機制。
  - 不在沙盒內部重新從網路下載編譯重複套件（一律重用並穿透宿主微環境）。

---

## 2. 核心討論與決策紀錄 (Discussion & Decisions)

- **[P00:DR-01]** 適配時機與契約：於 `SandboxProvisioner` 新增 `adapt_build_pip_dependencies(target_modules: Optional[List[str]] = None) -> List[str]`，在建置沙盒前從 `module.build://`（或源碼）解析 `pip_dependencies`，調用 `PipManager(host_yscb).install_packages(specs)` 完成宿主微環境預熱物化。
- **[P00:DR-02]** 沙盒 .venv 跨平台雙軌投影與降級兜底 (3-Tier Projection Pipeline)：Windows 優先調用 `_winapi.CreateJunction`（無需管理員權限、sub-1ms 完成），POSIX 優先調用 `os.symlink`；若底層檔案系統不支援（如 virtiofs、網路磁碟），捕獲例外自動平滑降級為建立輕量目錄並寫入 `host_venv.pth` 指向宿主 site-packages，達成 100% 跨 OS 與容器無縫通用。
- **[P00:DR-03]** 銷毀防護策略：在 `cleanup_sandbox` 中，若檢測到 `engine/.venv` 為 Junction / Symlink，優先調用 `os.unlink` / `os.rmdir` 解除綁定，絕不穿透刪除宿主微環境內容。
- **[P00:DR-04]** 靜態合規守門：`Checker` 增加 `_check_pip_dependencies` 邏輯，納入 Gate 1 檢查標準。

---

## 3. 開放議題與確認紀錄

- [x] 是否需要為每個沙盒獨立安裝全新 .venv？（已決策：否，微環境體積可達數百 MB，獨立重複安裝會導致測試耗時失控；採用零拷貝 Junction/Symlink 投影最優）。
- [x] Windows Junction / POSIX Symlink 能否在不同 OS 通用？（已決策：採雙軌抽象 + .pth 降級兜底架構，Windows 使用 Junction，POSIX 使用 Symlink，不支援時降級 .pth，100% 跨 OS 通用）。
