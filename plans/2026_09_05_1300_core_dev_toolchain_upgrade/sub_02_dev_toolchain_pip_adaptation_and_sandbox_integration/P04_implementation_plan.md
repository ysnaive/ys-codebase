# 實作計畫與定稿審查書 (Implementation Plan & Review)

> 功能名稱：dev_toolchain_pip_adaptation_and_sandbox_integration  
> 建立日期：2026-09-05  
> 所屬主計畫：2026_09_05_1300_core_dev_toolchain_upgrade  
> 狀態：Confirmed  
> 模板版本：v1.4  

---

## 1. 交叉驗證檢查清單 (Cross-Validation Checklist)

- [x] **需求對齊**：FR-01 ~ FR-05 在 API 規格書 (P03) 中均有對應介面與方法
- [x] **邊界防護**：EC-01 ~ EC-04 涵蓋空環境、非法型態、重複沙盒與殘留斷鏈之完整防護
- [x] **依賴純淨**：符合 NFR-01 與 NFR-02 指標約束（零拷貝、零新增依賴）

---

## 2. 知識庫文檔衝擊與交付規劃 (Documentation Impact Plan)

| 維度 | 文件路徑 | 變更類型 | 交付內容與重點 |
| :--- | :--- | :---: | :--- |
| **專題手冊** | `docs/dev/testing_guide.md` | Modify | 補充微環境雙軌投影、Junction 機制與 build 版 pip 適配架構說明 |
| **設計決策** | `docs/dev/DESIGN_NOTES.md` | Modify | 登記 DN-10 Build 版 pip 適配與沙盒微環境零拷貝投影決策 |

---

## 3. 架構靈魂拷問 (Stress Test & Resilience Review)

> ❓ **尖銳問題 1**：在 Windows 與 POSIX 環境下，沙盒銷毀時會不會誤將宿主微環境內容刪除？  
> 💡 **防護解法**：`cleanup_sandbox` 在調用 `shutil.rmtree(sandbox_dir)` 前，顯式檢查 `sandbox_engine/.venv` 是否為 Junction 或 Symlink；若是，優先以 `os.rmdir` 或 `os.unlink` 安全斷開重析點，絕對禁止遍歷刪除宿主微環境目錄。

> ❓ **尖銳問題 2**：若在 Docker 容器或 virtiofs 掛載磁碟上建立沙盒，Junction 或 Symlink 均失敗怎麼辦？  
> 💡 **防護解法**：捕獲 `OSError`，自動降級為建立輕量目錄並寫入 `host_venv.pth` 指向宿主微環境之 site-packages，確保 Python 直譯器始終能正確載入第三方套件。

---

## 4. 實作任務清單 (Task Breakdown & Topological Sequence)

- [ ] **TASK-01**：在 `source/dev/dev/checker.py` 實作 `_check_pip_dependencies` 並整合至 `_check_manifest`
- [ ] **TASK-02**：在 `source/dev/dev/testing/sandbox.py` 實作 `adapt_build_pip_dependencies` 與 `_project_venv`
- [ ] **TASK-03**：在 `create_sandbox` 與 `cleanup_sandbox` 中整合微環境投影與安全斷開防護
- [ ] **TASK-04**：在 `source/dev/tests/test_pip_adaptation.py` 撰寫單元與整合測試
- [ ] **TASK-05**：執行自動化測試驗證 (`python yscb.py dev test dev --quiet`)
- [ ] **TASK-DOC**：同步更新 `docs/dev/testing_guide.md` 與 `docs/dev/DESIGN_NOTES.md`

---

## 5. 決策定稿 (Confirmed Decision Records)

- **[P04:DR-01]** 定稿適配與投影管線：確認在沙盒建立前掃描 build 版 `pip_dependencies` 完成宿主物化，並以 Windows Junction / POSIX Symlink + `.pth` 降級實現零拷貝微環境穿透。
