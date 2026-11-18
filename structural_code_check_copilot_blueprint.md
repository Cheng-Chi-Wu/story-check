# Project Blueprint: Structural Code-Check & 3D Visualization Copilot (ASCE 7-22)

## 1. 核心概念與產品定位 (Core Concept)

### 1.1 解決什麼問題？
在美國結構工程實務中（特別是加州等高地震區），結構工程師使用 ETABS 或 SAP2000 跑完結構分析（Analysis）後，必須向政府審圖單位（Plan Check）繳交**建築規範合規檢核報告**。
目前商業軟體雖能計算基本構件內力，但針對 **ASCE 7-22 的整體建築耐震與不規則性檢核**，仍存在三大斷層：
1. **Excel 手動對表容易出錯**：工程師需匯出數萬列 CSV，用祖傳 Excel 巨集計算扭轉不規則與軟弱層，一旦改圖重跑分析，公式極易斷鏈。
2. **缺乏直觀空間定位**：報表只顯示 `Story 4` 或 `Joint #412` 違規，工程師需切回 3D 模型反覆比對位置。
3. **送審計算書排版耗時**：審圖單位要求白紙黑字的公式代入過程與規範條文依據，人工整理 Word/PDF 極度浪費高薪工程師時間。

### 1.2 我們的解決方案
打造一個**「結構分析軟體與送審報告之間的自動化後處理與 3D 視覺化外掛」**：
* **Zero-Friction Input**：直接拖曳上傳 ETABS/SAP2000 匯出的分析結果 CSV/Excel。
* **Deterministic Code Engine**：100% 依據美國規範公式（ASCE 7-22 Chapter 12）進行確定性判定，杜絕 AI 幻覺。
* **Interactive 3D Audit**：瀏覽器直接渲染 3D 大樓模型，違規樓層以紅/黃/綠三色高亮顯示並支援變形動畫。
* **One-Click Plan Check Report**：一鍵匯出排版專業、附帶計算公式與規範條文的 Word (`.docx`) 計算書。

---

## 2. 實際應用場景 (Applications)

MVP 第一階段聚焦於**美國結構設計規範 ASCE 7-22 Chapter 12（建築物耐震設計與結構不規則性檢核）**，具體包含三大核心檢核項目：

1. **水平扭轉不規則檢核（Horizontal Torsional Irregularity - Table 12.3-1 Type 1，§12.3.2.1.1）**
   * ASCE 7-22 只有一種扭轉不規則（7-16 的極端扭轉 Type 1b 已刪除；依 Trimble/Tekla 7-22 更新說明，未對照正式文本）。
   * TIR（Torsional Irregularity Ratio）= 各樓層「結構兩端」最大層間變位 / 兩端平均層間變位，逐層、逐方向、逐工況計算，分析須含偶發扭矩且 $A_x = 1.0$。僅適用於剛性或半剛性樓板。
   * 不規則條件：TIR $> 1.2$，**或**樓板下方超過 75% 的側向強度位於質心一側（工程師輸入）。
   * 後果（列為 `actions`）：SDC C–F 依 §12.8.4.3 放大偶發扭矩 $A_x$；SDC D–F 樓板連接與集力構件設計力加大 25%（§12.3.3.5）、確認 Table 12.6-1 分析方法；TIR $> 1.4$ 時 SDC D–F 取 $\rho = 1.3$（§12.3.4.2，單向或雙向待確認）；SDC C–F 提示確認 §12.5 正交方向組合是否適用。扭轉不規則**不會**判為禁止。
   * 狀態燈號：規則 = `PASS`；不規則但允許 = `WARNING`；規範禁止 = `FAIL`；不適用或無法計算 = `N/A`。
2. **垂直軟弱層檢核（Vertical Soft Story Irregularity - Table 12.3-2）**
   * 比較各樓層側向勁度 $K_i$ 與上方樓層。
   * Type 1a（軟弱層）：$K_i < 0.70\,K_{i+1}$ **或** $K_i < 0.80 \times$ 上方三層平均勁度。
   * Type 1b（極端軟弱層）：$K_i < 0.60\,K_{i+1}$ **或** $K_i < 0.70 \times$ 上方三層平均勁度。
   * 後果：Type 1b 在 **SDC E、F 禁止**（§12.3.3.1）。頂層無上方樓層，不檢核；上方不足三層時只檢核相鄰樓層條件。
   * §12.3.2.2 例外條款（已實作，可用 `apply_soft_story_exception: false` 關閉）：
     * 例外 1：該方向所有樓層的變位角皆不大於上一層之 130% 時，Type 1a/1b 不適用。不計扭轉（取平均變位），最頂兩層之間的關係不檢核。
     * 例外 2：單層建築，以及 SDC B、C、D 的兩層建築，不需檢核。
     * 豁免時該檢核為 `PASS`，公式字串仍列出勁度比並註明引用的例外條款。
3. **容許層間變位角檢核（Allowable Story Drift - §12.12.1、Table 12.12-1）**
   * 設計層間變位須放大：$\Delta = C_d\,\Delta_e / I_e$（§12.8.6）。ETABS 匯出的通常是彈性變位 $\Delta_e$，因此輸入必須提供 $C_d$、$I_e$，或明確標示變位已放大。
   * 取用位置：一般取質心處變位；SDC C–F 且具扭轉不規則時，取樓層邊緣之最大變位（§12.8.6）。
   * 容許值 $\Delta_a / h_{sx}$（Table 12.12-1）：

     | 結構類型 | Risk Cat. I/II | III | IV |
     | :--- | :--- | :--- | :--- |
     | 4 層以下、非砌體剪力牆、且內外牆與天花板可容納變位 | 0.025 | 0.020 | 0.015 |
     | 砌體懸臂剪力牆結構 | 0.010 | 0.010 | 0.010 |
     | 其他砌體剪力牆結構 | 0.007 | 0.007 | 0.007 |
     | 其他所有結構 | 0.020 | 0.015 | 0.010 |

   * SDC D–F 之抗彎矩構架：容許值須再除以贅餘度因子 $\rho$（§12.12.1.1）。
   * $\text{D/C Ratio} = \Delta / \Delta_a$，$> 1.0$ 為 `FAIL`。

### 2.1 規範假設與限制（必讀）
* 本工具為**輔助檢核**，不取代執業結構工程師（PE/SE）之專業判斷；所有公式與限值上線前須由持照工程師對照 ASCE 7-22 正式文本逐條驗證。
* 以「兩端平均變位」近似質心變位；若 ETABS 可匯出質心變位，後續應改用實際值。
* 未計入樓板變形項 $\delta_{di}$（假設剛性樓板）、未計算 $A_x$ 數值（需各層位移而非層間變位）、未檢核 Table 12.3-1/12.3-2 其他類型之不規則。

---

## 3. 系統技術架構 (Tech Stack)

* **前端介面與 3D 渲染**：Next.js (React) + Tailwind CSS + Three.js (`@react-three/fiber`)
* **後端 API 框架**：Python FastAPI + Uvicorn
* **數據清洗與計算核心**：Pandas + NumPy + Pytest
* **送審報告自動生成**：`python-docx`
* **部署架構**：Vercel（前端）+ Render / Railway（後端）

---

## 4. 四大 AI Agent 精準分工 (4-Agent Parallel Workflow)

為實現高效率並行開發且避免檔案衝突，專案依據統一數據契約拆分為四個獨立模組，分別指派給最適合的 AI 模型：

| Agent 角色 | 指派模型 | 負責目錄 / 核心檔案 | 核心職責與交付標準 |
| :--- | :--- | :--- | :--- |
| **Agent 1：數據管線與測試生成器** | **Muse** (Muse Code) | `/backend/parser.py`<br>`/backend/mock_data_gen.py`<br>`/data/*.csv` | 1. 編寫 Pandas 解析器，清洗 ETABS/SAP2000 匯出的 `Story Drifts` 與 `Story Stiffness` CSV，統一單位（in, kips）並輸出標準輸入 JSON。<br>2. 生成 3 組模擬大樓測試 CSV（5層、15層、30層），**刻意埋入扭轉超標與軟弱層違規數據**供全系統測試。 |
| **Agent 2：美國規範計算引擎** | **Claude** | `/backend/code_checker.py`<br>`/tests/test_checker.py` | 1. 實作 ASCE 7-22 Table 12.3-1、12.3-2、12.12-1 確定性檢核邏輯。<br>2. 輸出每層的 D/C Ratio、狀態燈號（`PASS` / `WARNING` / `FAIL`）、規範條文編號及**人類可讀的計算過程算式字串**。<br>3. 撰寫完整 `pytest` 單元測試驗證公式零誤差。 |
| **Agent 3：總架構師與 3D 前端工程師** | **Gemini** | `PROJECT_BLUEPRINT.md`<br>`/frontend/*` (Next.js + Three.js) | 1. 維護全局系統架構與 `schema.json` 數據契約。<br>2. 開發專業工程儀表板：包含 CSV 拖曳上傳、KPI 摘要卡片、**Three.js 3D 建築骨架與樓板渲染**（支援變形放大滑桿、紅黃綠違規高亮、點擊樓層查看右側規範公式詳情）。 |
| **Agent 4：後端 API 與計算書生成器** | **GPT** | `/backend/main.py`<br>`/backend/report_builder.py` | 1. 建立 FastAPI 路由：`POST /api/analyze`（串接 Parser 與 Checker）與 `POST /api/export-report`。<br>2. 使用 `python-docx` 生成美式結構工程送審計算書（封面、違規項目紅字摘要表、各樓層詳細公式代入計算過程）。 |

---

## 5. 統一數據契約 (Unified JSON Data Contract)

**所有 Agent 必須嚴格遵守以下 JSON 結構進行模組間資料交換，不得擅自更改欄位名稱：**

### 5.1 Parser 輸出 / Code Checker 輸入格式 (`BuildingAnalysisInput`)
```json
{
  "project_info": {
    "building_name": "Los Angeles Commercial Tower",
    "risk_category": "II",
    "seismic_design_category": "D",
    "structure_type": "other",
    "diaphragm": "rigid",
    "cd": 5.5,
    "ie": 1.0,
    "drift_is_amplified": false,
    "moment_frame_rho": null,
    "drift_limit_ratio": null,
    "units": {
      "length": "in",
      "force": "kips"
    }
  },
  "stories": [
    {
      "story_name": "Story 1",
      "elevation_in": 180.0,
      "height_in": 180.0,
      "max_drift_x_in": 0.40,
      "avg_drift_x_in": 0.27,
      "max_drift_y_in": 0.33,
      "avg_drift_y_in": 0.30,
      "stiffness_x_kip_in": 450.0,
      "stiffness_y_kip_in": 480.0
    }
  ]
}
```

`project_info` 欄位說明（`risk_category` 以外皆為選填，括號內為預設值）：
* `seismic_design_category`（`"D"`）：`"A"`–`"F"`，決定不規則性是否被禁止。
* `structure_type`（`"other"`）：`"other"` / `"four_story_or_less_drift_tolerant"` / `"masonry_cantilever_shear_wall"` / `"other_masonry_shear_wall"`，對應 Table 12.12-1 四列。
* `diaphragm`（`"rigid"`）：`"rigid"` / `"semirigid"` / `"flexible"`；`flexible` 時不做扭轉檢核。
* `drift_is_amplified`（`false`）：`false` 表示 `stories` 內的變位是彈性值，Checker 會乘上 `cd / ie`，此時 `cd` 必填。
* `ie`：未提供時依風險類別取 1.0 / 1.0 / 1.25 / 1.5（Table 1.5-2）。
* `moment_frame_rho`（`null`）：SDC D–F 純抗彎矩構架填入 $\rho$（只接受 1.0 或 1.3），容許變位角會除以它。
* `torsion_strength_irregular`（`null`）：§12.3.2.1.1 強度條件；`true` 直接判扭轉不規則，`null` 表示未評估。
* `structure_type` 選 `four_story_or_less_drift_tolerant` 時，超過 4 層會被拒絕。
* `drift_limit_ratio`（`null`）：填入數值時覆寫 Table 12.12-1 查表結果。
* `stories` 內 `max_drift_*` = 樓層兩端之最大層間變位，`avg_drift_*` = 兩端平均層間變位（含偶發扭矩、$A_x = 1.0$）。

### 5.2 Code Checker 輸出 / Frontend & Report 接收格式 (`CodeCheckResult`)
完整範例見 `data/sample_output/15_story_tower_result.json`（引擎實際輸出），欄位說明見 `PROJECT_REVIEW.md` 6.3 節。重點：

* `summary`：`overall_status`、`total_violations`（FAIL 數）、`total_warnings`、`total_not_applicable`、`max_dc_ratio`（**只取變位檢核**的 D/C）、`action_items`（`{action, stories}` 清單）。
* `basis`：實際採用的參數（含預設值，例如由風險類別推得的 I_e）。
* 每項檢核：`check_type`、`code_reference`、`demand_value`、`capacity_limit`、`dc_ratio`、`status`（PASS / WARNING / FAIL / N/A）、`formula_breakdown`、`output_case`、`actions`。N/A 檢核的數值欄位可能為 null。

---

### 5.3 後端 API（已實作）

啟動：`uvicorn backend.main:app --reload`（預設允許 `http://localhost:3000`，正式環境用環境變數 `CORS_ORIGINS` 設定，逗號分隔）。

| 路由 | 輸入 | 輸出 |
| :--- | :--- | :--- |
| `POST /api/analyze` | `multipart/form-data`：`files`（重複欄位，三張表，CSV 或 XLSX，順序與檔名不限）、`project_info`（5.1 的 `project_info` JSON 字串）、選填 `length_unit`（`in`/`ft`/`mm`/`cm`/`m`）、`force_unit`（`kip`/`lb`/`kN`/`N`）、`case_x`、`case_y` | 5.2 的 `CodeCheckResult`，另附頂層 `project_info`（實際使用的參數） |
| `POST /api/export-report` | JSON：`/api/analyze` 的完整回應 | `.docx` 檔案下載 |
| `GET /api/health` | — | `{"status": "ok"}` |

錯誤一律回 `422`，`detail` 為可直接顯示給使用者的訊息。

三張表以欄位自動辨識（對應 ETABS 表格名稱）：
* **Story Definitions**：`Story`、`Height`、`Elevation`（選填，缺少時由高度累加）
* **Story Max Over Avg Drifts**：`Story`、`Output Case`、`Direction`、`Max Drift`、`Avg Drift`
* **Story Stiffness**：`Story`、`Output Case`、`Stiff X`、`Stiff Y`（有 `Shear X/Y` 時取該方向剪力最大的工況）

未指定 `case_x` / `case_y` 時，每層每方向取最大變位的工況。欄位名稱是依 ETABS 表格慣例推定，**尚未用真實匯出檔驗證**，Phase 3 取得真實檔案後在 `parser.py` 的 `ALIASES` 補別名即可。

模擬資料：`python -m backend.mock_data_gen` 產生 `data/` 下三棟大樓（5、15、30 層），各含三張 CSV 與 `project.json`。

---

## 6. 實施步驟與開發路線圖 (Execution Roadmap)

### Phase 1：平行獨立開發（Day 1 - Day 2）
1. **初始化倉庫**：建立 GitHub Repo，將本文件存為根目錄 `PROJECT_BLUEPRINT.md`，並建立 `/backend`、`/frontend`、`/data`、`/tests` 資料夾。
2. **同時分派指令**：
   * 將本文件與 Agent 1 指令貼給 **Muse**，產出 `mock_data_gen.py` 與 `parser.py`。
   * 將本文件與 Agent 2 指令貼給 **Claude**，產出 `code_checker.py` 與 `test_checker.py`。
   * 將本文件與 Agent 4 指令貼給 **GPT**，產出 `main.py` 與 `report_builder.py`。
   * 由 **Gemini** 依據 Section 5.2 的 JSON 格式生成完整的 Next.js + Three.js 前端應用程式。

### Phase 2：端到端整合與測試（Day 3）
1. 使用 Muse 生成的模擬違規大樓 CSV 檔案，透過 Postman 或前端介面打通 `POST /api/analyze`。
2. 驗證 Three.js 3D 模型是否正確將違規樓層標示為紅色，且變形動畫與點擊公式側邊欄運作正常。
3. 點擊「匯出送審計算書」按鈕，檢查 GPT 生成的 `.docx` 報告排版與公式數據是否與前端一致。

### Phase 3：真實世界驗證（Day 4 - Day 7）
1. **錄製 60 秒產品演示影片**：展示「上傳 ETABS CSV $\rightarrow$ 3D 模型瞬間抓出軟弱層與扭轉違規 $\rightarrow$ 一鍵匯出 Word 計算書」的完整流程。
2. **種子用戶訪談**：聯繫 UCLA 土木系結構組同學/教授，以及在結構事務所工作的學長姐，展示 Demo 並蒐集真實 ETABS 匯出欄位格式以微調 `parser.py`。