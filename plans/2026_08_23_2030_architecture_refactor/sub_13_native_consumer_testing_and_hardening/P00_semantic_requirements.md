# 語意需求說明書 (Semantic Requirements - Phase 0)

> 功能名稱：第三方真實使用者原生情境測試、問題排查與框架加固 (Native Consumer Testing & Hardening)  
> 建立日期：2026-08-25  
> 所屬主計畫：[2026_08_23_2030_architecture_refactor](../umbrella_overview.md)  
> 狀態：Confirmed (與開發者共同確認定稿)  
> 擴充項目：none  
> 模板版本：v1.4  

---

## 1. 任務背景與核心目標

本子計畫 (`sub_13`) 作為宏觀架構重構主計畫的**終極驗收與原生加固閘門**。
透過在獨立乾淨的 `./user/` 目錄中模擬 100% 真實下游第三方使用者的完整操作流程（從 GitHub 下載 `yscb.py` ➔ `init` ➔ 自舉 `core` ➔ 安裝模組 ➔ 執行業務），實機排查並修復任何阻礙第三方開箱即用的邊界缺陷。

---

## 2. 核心功能需求範圍 (In-Scope)

1. **預設 Provider 遠端化與零猜測 (Default Remote Provider)**：
   - `yscb.py` 預設 `DEFAULT_PROVIDER_URL` 剛性設定為官方 GitHub 遠端路徑：`https://raw.githubusercontent.com/ysnaive/agent.workflow/main/release`。
   - 本地開發端若需測試本機目錄，透過顯式 `--provider=./release` 傳入。
2. **全面 Zip 單檔打包與 Provider 同構協定 (Full Zip Packaging Standard)**：
   - **明文空間二分法**：全系統僅 `source/`（開發源碼）與 `modules/`（運行解包代碼）以明文目錄呈現。
   - **套件庫同構結構**：`release/` 與 `build/` 統一以 `<module>/index.json` + `<module>/<version>.zip` 形式存儲，不再落地展開散裝目錄。
   - **自舉與安裝管線統一**：`yscb.py init` 與 `core.installer` / `AtomicEngine` 統一一律透過獲取 `<version>.zip`（本地複製或遠端串流下載）後，經 Python 標準庫 `zipfile` 解包至 `modules/<module>/`。
3. **原生消費者端到端驗證 (End-to-End Validation)**：
   - 在全新 `./user/` 目錄中完成真實全流程原生驗收。

---

## 3. 關聯技術調研報告 (Research Reports)

- [`R01_native_consumer_e2e_testing_and_gap_analysis.md`](./R01_native_consumer_e2e_testing_and_gap_analysis.md)：第三方原生消費者端到端測試障礙與遠端自舉解包機制深度調研。
- [`R02_full_zip_packaging_architecture_analysis.md`](./R02_full_zip_packaging_architecture_analysis.md)：套件庫全面 Zip 化 (`{version}.zip`)、本地與遠端 100% 同構協定與極致乾淨檔案樹設計。
