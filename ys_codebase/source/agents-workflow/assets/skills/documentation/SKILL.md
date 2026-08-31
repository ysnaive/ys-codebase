---
name: documentation
description: 專案文檔與知識庫架構規範指南。當有閱讀、搜尋、查閱、撰寫、更新或維護專案 `__${workflow.docs://}__` 知識庫文檔時觸發。
---

# 專案知識庫架構與閱讀導引 (Documentation Standards - Reader's Guide)

本指南定義專案知識庫（`__${workflow.docs://}__`）的抽象知識維度與架構導引，協助開發者與 Agent 快速定位系統各層級的客觀現狀與規範。

---

## 🎯 核心定位：兩套系統的職責劃分

| 系統 | 語意定位 | 職責與生命週期 | 內容性質 |
| :--- | :--- | :--- | :--- |
| **開發過程紀錄** | `__${workflow.plans://}__` / `__${workflow.archived://}__` | 記錄探索、爭辯、任務與決策過程；結案後永久凍結 | 過程導向、DR 決策、任務清單 |
| **系統知識庫** | `__${workflow.docs://}__` | 記錄現況事實、架構拓撲與防坑邊界；隨代碼持續演進 | 狀態導向、現狀事實、邊界合約 |

> [!IMPORTANT]
> **知識庫只陳述客觀現狀與坑點，不記錄歷史爭辯過程。** 探索、爭辯與替代方案留於 `__${workflow.plans://}__`，`__${workflow.docs://}__` 專注於回答「現在是什麼架構」與「邊界條件/不變量」。

---

## 🌐 軟體工程 7 大抽象知識維度（知識檢索地圖）

知識庫檔案按 `<Category>`（代表業務領域、架構子系統或多層命名空間，支援單層如 `core` 或多層如 `Render/Layout/FlexEngine`）進行組織：

| 維度 (Dimension) | 核心範疇 | 知識庫檔案位置 (Carrier) | 閱讀目的與用途 |
| :--- | :--- | :--- | :--- |
| **① 領域概念模型** | 領域通用語言 (Ubiquitous Language)、實體與名詞定義 | `__${workflow.docs://_project/ARCHITECTURE.md}__`<br>`__${workflow.docs://}__/<Category>/README.md` | 理解全域與子系統業務實體概念 |
| **② 靜態邊界與拓撲** | 模組/子系統職責邊界（做什麼、不做什麼）、依賴方向 | `__${workflow.docs://_project/ARCHITECTURE.md}__`<br>`__${workflow.docs://}__/<Category>/README.md` | 確認架構邊界與模組依賴方向 |
| **③ 中觀動態機制** | 跨類別協同、資料流、狀態機 (FSM)、協議與生命週期 | `__${workflow.docs://}__/<Category>/[topic].md`<br>*(獨立專題手冊)* | 深入理解複雜控制流、資料管線與狀態轉換 |
| **④ 介面合約與承諾** | 前置/後置條件、錯誤型態、輸入輸出 Schema | 程式碼 Docstrings / Public Headers | 查閱 API 參數、回傳型別與例外契約 |
| **⑤ 工程妥協與防坑** | 為效能/平台限制而採取的反直覺設計 (Non-obvious) | `__${workflow.docs://}__/<Category>/DESIGN_NOTES.md`<br>*(DN-XX + `[!CAUTION]`)* | 避免破壞有意為之的防坑或效能設計 |
| **⑥ 人因操作引導** | 快速上手、配置矩陣、典型範例 (Cookbook)、故障排查 | `__${workflow.docs://}__/<Category>/README.md`<br>`__${workflow.docs://_project/CLI_SPECIFICATION.md}__` | 查閱指令用法、配置參數與快速上手 |
| **⑦ 架構演進歷史** | 重大架構重構歷史（痛點 ➔ 改變 ➔ 參照 Plan） | `__${workflow.docs://}__/<Category>/CHANGELOG.md`<br>`__${workflow.docs://CHANGELOG.md}__` | 了解子系統或專案全局歷史重大架構轉折 |

---

## ✍️ 文檔作者指南 (Author's Guide & Checklist)

當您需要**新增、撰寫、更新文檔**或執行**三層文檔交付對齊**時，請參閱作者手冊：
- [文檔撰寫與作者指引 (references/author_guide_and_checklist.md)](./references/author_guide_and_checklist.md)：包含文檔歸屬判定決策樹、中觀專題手冊 5 大情境、三層交付閉環、超連結點擊性規範、YAML Frontmatter Schema 與作者自檢核對清單。
