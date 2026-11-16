# Story Check：專案說明與審查請求

這份文件是給審查者（人或 AI）看的。請不要客氣：目的是找出這個專案在**規範正確性、工程實務、程式設計、產品與商業**上的問題。最後一節列了我們自己最沒把握的地方，請優先攻擊那裡。

文件寫於 2026-11-16。所有敘述以當天的程式碼為準。

---

## 1. 一句話說明

結構工程師把 ETABS 匯出的三張表丟進網頁，工具依 ASCE 7-22 Chapter 12 逐層檢核**扭轉不規則、軟弱層、層間變位角**，在 3D 模型上標出有問題的樓層，並產生一份附公式代入過程的 Word 送審計算書。

## 2. 要解決的問題與目標使用者

- **使用者**：美國高地震區（加州為主）的結構工程師，日常使用 ETABS / SAP2000。
- **現況的痛點（我們的假設，尚未經訪談驗證）**：
  1. 分析跑完後，整棟建築的不規則性檢核常用自製 Excel 處理，改模型重跑後容易出錯。
  2. 報表只告訴你「Story 4 有問題」，要回 3D 模型對位置。
  3. 審圖單位（plan check）要看公式代入過程與條文依據，整理計算書很花時間。
- **產品定位**：ETABS 與送審報告之間的後處理工具。計算是**確定性的規則引擎**，沒有使用 LLM 做任何判定。

## 3. 目前狀態

| 項目 | 狀態 |
| :--- | :--- |
| 規範計算引擎 | 完成，31 個單元測試函式（含參數化共 53 個案例） |
| ETABS 解析器 | 完成，但**從未用真實 ETABS 匯出檔測試過** |
| API | 完成 |
| Word 計算書 | 完成，**未在 Microsoft Word 中檢視過完整版面** |
| 前端（含 3D） | 完成，已在瀏覽器手動測試 |
| 測試 | 後端共 74 個案例全數通過；前端沒有自動化測試 |
| 部署 | 設定檔已備妥（Render + Vercel），尚未上線 |
| 使用者驗證 | **零**。沒有任何結構工程師看過或用過 |
| 規範條文核對 | **未做**。所有限值與條文編號由 AI 依記憶寫成，未對照 ASCE 7-22 正式文本 |

## 4. 架構

```
瀏覽器 (Next.js 16 + React 19 + Tailwind 4 + three.js / react-three-fiber)
   │  POST /api/analyze        multipart：三張表 + project_info(JSON)
   │  POST /api/export-report  JSON：analyze 的回應
   ▼
FastAPI
   ├─ parser.py          ETABS 表格 → BuildingAnalysisInput（統一成 in、kips）
   ├─ code_checker.py    BuildingAnalysisInput → CodeCheckResult（純函式，無 I/O）
   └─ report_builder.py  CodeCheckResult → .docx（python-docx）
```

- 沒有資料庫、沒有登入、沒有保存任何上傳資料；每次請求獨立處理。
- 前後端分開部署：前端 Vercel，後端 Render。

### 目錄

```
backend/
  code_checker.py     規範檢核引擎
  parser.py           ETABS CSV / Excel 解析
  mock_data_gen.py    產生三棟模擬大樓的匯出檔
  report_builder.py   Word 計算書
  main.py             FastAPI 路由
tests/
  test_checker.py     引擎單元測試
  test_backend.py     解析器、模擬資料、API、報告測試
frontend/
  app/page.tsx                  單頁應用
  components/SetupPanel.tsx     上傳與專案參數
  components/BuildingViewer.tsx 3D 檢視
  components/StoryPanel.tsx     總結數字、樓層清單、檢核詳情
  lib/api.ts, lib/types.ts
  public/samples/               三棟範例大樓（供「載入範例」按鈕使用）
data/                           模擬資料與範例輸出
structural_code_check_copilot_blueprint.md   原始藍圖（含數據契約）
render.yaml                     後端部署設定
```

## 5. 規範檢核邏輯（請重點審查）

實作在 `backend/code_checker.py`。每層、X 與 Y 兩個方向各做三項檢核，所以每層最多六項。

### 5.1 燈號定義

| 狀態 | 意義 |
| :--- | :--- |
| `PASS` | 規則，或在限值內 |
| `WARNING` | 不規則性存在，規範**允許**但會觸發額外要求 |
| `FAIL` | 規範**禁止**（§12.3.3.1），或變位超過容許值 |

樓層狀態取該層六項中最嚴重者；建築狀態取所有樓層中最嚴重者。

### 5.2 水平扭轉不規則（Table 12.3-1，Type 1a / 1b）

- 比值 = `max_drift / avg_drift`。`max_drift` 是樓層兩端中較大的層間變位，`avg_drift` 是兩端平均。
- 假設輸入的分析已含偶發扭矩且 A_x = 1.0。**工具無法驗證這點**。
- 比值 ≤ 1.2：`PASS`
- 1.2 < 比值 ≤ 1.4：Type 1a，`WARNING`
- 比值 > 1.4：Type 1b。SDC E、F 為 `FAIL`（§12.3.3.1 禁止），其他 SDC 為 `WARNING`
- SDC C–F 且不規則時，說明文字會提示需依 §12.8.4.3 放大偶發扭矩 A_x。**A_x 的數值沒有計算**（需要各層位移，目前只有層間變位）。
- 樓板為 `flexible` 時整項跳過。
- `dc_ratio` = 比值 / 1.2。

### 5.3 垂直軟弱層（Table 12.3-2，Type 1a / 1b）

令 r1 = K_i / K_(i+1)，r3 = K_i / (上方三層平均勁度)。

- Type 1a：r1 < 0.70 **或** r3 < 0.80 → `WARNING`
- Type 1b：r1 < 0.60 **或** r3 < 0.70 → SDC E、F 為 `FAIL`，其他為 `WARNING`
- 頂層沒有上方樓層，不產生此項檢核。上方不足三層時只用 r1。
- `capacity_limit` = 避免 Type 1a 所需的最小勁度 = max(0.70·K_(i+1), 0.80·K_avg3)；`dc_ratio` = 該值 / K_i。

**§12.3.2.2 例外條款**（預設啟用，可用 `apply_soft_story_exception: false` 關閉）：

- 例外 1：某方向所有受檢樓層的變位角（平均變位 / 樓高）都不大於上一層的 130% 時，該方向的 Type 1a/1b 不適用。
  - 不計扭轉，所以用平均變位。
  - 「最頂兩層的關係不需評估」被實作成：只跳過「次頂層 對 頂層」這一組比較。
  - 至少要三層才會套用。
- 例外 2：單層建築；以及 SDC B、C、D 的兩層建築。
- 被豁免的檢核狀態為 `PASS`，條文欄位為「Table 12.3-2; Section 12.3.2.2」，`dc_ratio` 改報「最大變位角倍數 / 1.30」。

### 5.4 容許層間變位角（§12.12.1，Table 12.12-1）

- 設計變位 Δ = C_d · Δ_e / I_e（§12.8.6）。輸入若標示 `drift_is_amplified: true` 則不再放大。
- I_e 未提供時依風險類別取 1.0 / 1.0 / 1.25 / 1.5。
- 取用哪個變位：
  - 該方向有扭轉不規則且 SDC C–F → 用 `max_drift`（邊緣）
  - 其他情況 → 用 `avg_drift`，作為**質心變位的近似值**
- 容許值 Δ_a / h_sx：

  | 結構類型 | I / II | III | IV |
  | :--- | :--- | :--- | :--- |
  | 4 層以下、非砌體、裝修可容納變位 | 0.025 | 0.020 | 0.015 |
  | 砌體懸臂剪力牆 | 0.010 | 0.010 | 0.010 |
  | 其他砌體剪力牆 | 0.007 | 0.007 | 0.007 |
  | 其他所有結構 | 0.020 | 0.015 | 0.010 |

- 填了 `moment_frame_rho` 且 SDC 為 D–F 時，容許值除以 ρ（§12.12.1.1）。**工具不判斷結構是否真的是抗彎矩構架**，完全信任使用者輸入。
- 超過容許值為 `FAIL`，否則 `PASS`。沒有「接近限值」的警告。
- 未計入樓板變形項 δ_di。

### 5.5 沒有做的檢核

Table 12.3-1 的其他類型（凹角、樓板不連續、面外偏移、非平行系統）、Table 12.3-2 的其他類型（質量、幾何、面內不連續、弱層）、P-Delta 穩定係數、贅餘度 ρ 的判定、建築分隔距離。

## 6. 資料格式

### 6.1 輸入：三張 ETABS 表

以欄位名稱自動辨識（不看檔名），接受 CSV 與 Excel，會跳過標題列與單位列。

| 表 | 必要欄位 | 備註 |
| :--- | :--- | :--- |
| Story Definitions | `Story`、`Height` | `Elevation` 選填，缺少時由高度累加（假設由上往下排列）。高度 ≤ 0 的列（Base）會被丟掉 |
| Story Max Over Avg Drifts | `Story`、`Direction`、`Max Drift`、`Avg Drift` | 有 `Output Case` 時可指定工況 |
| Story Stiffness | `Story`、`Stiff X`、`Stiff Y` | 有 `Shear X/Y` 時取該方向剪力最大的工況 |

工況選擇：使用者未指定時，每層每方向各自取 `Max Drift` 最大的那一列。**不同樓層可能因此取到不同工況**；採用了哪些工況會寫進計算書。

**欄位名稱是依對 ETABS 表格的印象推定的，沒有對照過真實匯出檔。**

### 6.2 `project_info`

```json
{
  "building_name": "Los Angeles 15-Story Commercial Tower",
  "risk_category": "II",
  "seismic_design_category": "D",
  "structure_type": "other",
  "diaphragm": "rigid",
  "cd": 5.5,
  "ie": 1.0,
  "drift_is_amplified": false,
  "moment_frame_rho": null,
  "drift_limit_ratio": null,
  "apply_soft_story_exception": true,
  "project_number": "24-117",
  "company": "...", "engineer": "...", "checked_by": "..."
}
```

只有 `risk_category` 必填；`drift_is_amplified` 為 false 時 `cd` 也必填。完整說明見藍圖 5.1 節。

### 6.3 輸出 `CodeCheckResult`

```json
{
  "summary": {"building_name": "...", "total_stories": 15, "overall_status": "FAIL",
              "total_violations": 1, "total_warnings": 3, "max_dc_ratio": 1.472},
  "story_results": [{
    "story_name": "Story1", "elevation_in": 180.0, "height_in": 180.0,
    "status": "FAIL", "max_dc_ratio": 1.472,
    "deformations": {"max_drift_x_in": 0.717, "avg_drift_x_in": 0.664, "...": 0},
    "checks": [{
      "check_type": "Allowable Story Drift (X-Dir)",
      "code_reference": "ASCE 7-22 Table 12.12-1",
      "demand_value": 0.02029, "capacity_limit": 0.02, "dc_ratio": 1.014,
      "status": "FAIL",
      "formula_breakdown": "Delta = C_d * Delta_e / I_e = 5.5 * 0.664 in / 1 = 3.650 in [center of mass (avg)]; Delta / h_sx = 3.650 in / 180.0 in = 0.0203 > 0.0200 (Table 12.12-1, Risk Category II)"
    }]
  }],
  "project_info": {"...": "API 回應才有，內含實際使用的參數與採用的工況"}
}
```

完整範例：`data/sample_output/15_story_tower_result.json`。

注意：`max_dc_ratio` 混合了三種不同性質的比值（扭轉比 / 1.2、勁度需求比、變位比）。不規則性的 D/C > 1 不代表違規。

## 7. 使用步驟

### 7.1 終端使用者（網頁）

1. 在 ETABS：`Display → Show Tables`，勾選 Story Definitions、Story Max Over Avg Drifts、Story Stiffness，選擇含偶發偏心的地震力工況，匯出成 CSV 或 Excel。
2. 打開網頁，把三個檔案拖進左上角的框（或點「載入範例大樓」直接看效果）。
3. 填專案參數：風險類別、SDC、結構類型、樓板類型、Cd（若匯出的變位已放大則勾選該選項）、檔案使用的單位。
4. 選填報告標題欄：專案編號、事務所、製作人、審核人。
5. 按「Run check」。
6. 看結果：
   - 中間 3D 模型：紅 = Fail、黃 = Irregular、綠 = Pass。可拖曳旋轉、調整變形放大倍率、開啟擺動動畫、點樓板選取。
   - 右欄：四個總結數字，以及由上而下的樓層清單。點任一層展開六項檢核的條文與公式。
7. 按右上角「Download calculation report (.docx)」取得計算書。

### 7.2 開發者（本機）

需求：Python 3.10+、Node 20+。

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python -m pytest -q                        # 74 passed
.venv/bin/python -m backend.mock_data_gen            # 重新產生 data/ 下的模擬資料
.venv/bin/python -m uvicorn backend.main:app --port 8000
```

```bash
npm --prefix frontend install
npm --prefix frontend run dev                        # http://localhost:3000
```

直接呼叫 API：

```bash
D=data/15_story_tower
curl -X POST localhost:8000/api/analyze \
  -F files=@$D/story_definitions.csv \
  -F files=@$D/story_max_over_avg_drifts.csv \
  -F files=@$D/story_stiffness.csv \
  -F "project_info=<$D/project.json" -o result.json
curl -X POST localhost:8000/api/export-report \
  -H 'Content-Type: application/json' -d @result.json -o report.docx
```

`/api/analyze` 另接受表單欄位 `length_unit`（in/ft/mm/cm/m）、`force_unit`（kip/lb/kN/N）、`case_x`、`case_y`。錯誤一律回 422，`detail` 是可直接顯示的訊息。

### 7.3 部署

- 後端：Render 讀取根目錄的 `render.yaml`。環境變數 `CORS_ORIGINS` 設為前端網址；`CORS_ORIGIN_REGEX` 選填。
- 前端：Vercel，Root Directory 設為 `frontend`，環境變數 `NEXT_PUBLIC_API_URL` 設為後端網址。
- Render 免費方案閒置後會休眠，第一次請求可能要等近一分鐘。

## 8. 模擬資料

`backend/mock_data_gen.py` 產生三棟大樓，數值是確定性的（沒有亂數）。**這些資料是用簡化的剪力/勁度分布公式捏出來的，不是真實分析結果，只用來示範與測試。**

| 資料夾 | SDC | 埋入的狀況 | 結果 |
| :--- | :--- | :--- | :--- |
| `05_story_office` | D | Story 2 X 向扭轉比 1.30 | WARNING |
| `15_story_tower` | D | Story 1 勁度減半（變位隨之加倍並超限）；Story 4 X 向扭轉比 1.50 | FAIL |
| `30_story_highrise` | E | Story 12 勁度降為 55%；Story 20 Y 向扭轉比 1.55 | FAIL |

## 9. 3D 檢視的真實性

匯出的表格沒有平面幾何，所以：

- 柱位是固定假設的 4×3 跨（1080 in × 720 in），**與實際建築無關**。
- 側移 = 各層平均層間變位由下往上累加，這部分來自資料。
- 扭轉角 = (最大變位 − 平均變位) / 假設的半個平面深度，**只是視覺示意**。
- 畫面左下角有文字說明這是示意模型。

## 10. 已知限制與風險

1. **規範條文未經核對**：這是最大的風險。限值、條文編號、例外條款的解讀都可能有錯。
2. **解析器未見過真實檔案**：欄位名稱、單位列格式、多工況的實際樣貌都是猜的。
3. **質心變位用平均值近似**：兩端平均不等於質心變位，質心偏離幾何中心時會有誤差。
4. **多工況取法粗糙**：逐層取最大值可能把不同工況混在一起；ETABS 的 Max/Min step type 也沒有特別處理。
5. **扭轉檢核的前提無法驗證**：工具不知道使用者選的工況是否真的含偶發扭矩、A_x 是否為 1.0。
6. **Story Stiffness 的定義**：ETABS 的樓層勁度是「樓層剪力 / 層間變位」，與載重型態有關。直接拿它做 Table 12.3-2 的判定是否被審圖單位接受，沒有確認過。
7. **沒有登入與權限**：上線後任何人都能使用；沒有流量限制。
8. **不保存資料**：重新整理頁面結果就消失。
9. **前端沒有自動化測試**。
10. **責任歸屬**：計算書上有免責聲明，但若工程師依賴錯誤結果送審，法律責任如何界定沒有研究過。

## 11. 請審查者回答的問題

**規範與工程**
1. 5.2–5.4 節的限值、條文編號、SDC 禁止條件，與 ASCE 7-22 正式文本有無出入？ASCE 7-22 相對於 7-16 在這三項上有沒有我們漏掉的修訂？
2. §12.3.2.2 例外 1 中「最頂兩層」的解讀（只跳過次頂層對頂層）正確嗎？例外條款逐方向套用合理嗎？
3. 扭轉不規則且 SDC C–F 時改用邊緣變位做變位檢核，這是 §12.8.6 的正確解讀嗎？
4. 用 ETABS 的 Story Stiffness 表判定軟弱層，實務上審圖單位接受嗎？工程師通常怎麼算？
5. 「不規則但允許 = WARNING、禁止 = FAIL」這個燈號設計，工程師會覺得清楚還是誤導？
6. 只做這三項檢核，對送審有實際幫助嗎？還是少了某些項目就等於沒用？

**程式**
7. `code_checker.py` 有沒有邊界條件錯誤（浮點比較、頂層、樓層數不足、零或負值）？
8. `parser.py` 逐層取最大變位工況的做法，會不會產生物理上不一致的結果？應該怎麼改？
9. 數據契約有沒有設計不良、之後難以擴充的地方？

**產品與商業**
10. 這個痛點真的存在嗎？工程師事務所是否早就有內部工具，或 ETABS 本身、既有外掛已經做到？
11. 誰會付錢？工程師個人、事務所，還是根本沒人？
12. 計算書要長成什麼樣子，審圖單位才會收？
13. 一個沒有 PE/SE 背書的工具產出的計算書，工程師敢用嗎？
