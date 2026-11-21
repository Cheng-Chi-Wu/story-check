# Story Check 審查報告 — 第二版（重測）

- **版本**：第二版（第一版：`Story_Check_審查報告_2026-11-17.md`，同日稍早）
- **重測日期**：2026-11-17（PT）
- **受測系統**：線上正式環境——前端 https://story-check-virid.vercel.app ；後端 API https://story-check-api.onrender.com（全部測試經 API 執行；前端僅核對範例與預算結果一致）
- **測試依據**：`AI_RETEST_PROMPT.md`、`PROJECT_REVIEW.md` 更新版（第 5 節新邏輯、第 12 節修正紀錄）、第一版報告 Findings 1–14
- **審查者立場**：本報告由 AI 執行 QA 重測，**審查者不是持照 SE**；內容是測試與條文查核結果，不構成設計意見。
- **本版新增的查核手段**：除重跑第一版全部問題案例外，本版取得了 **ASCE/SEI 7-22 正式出版文本的目錄全文**並逐項比對條號（§12.3.3 各子節標題、§12.5、§12.8.4、§12.12.1.1 的編號均由此核對）。條文「本文」未能取得者，仍標示「未驗證」。

---

## 總判定（Verdict）

第一版的 14 項 findings：**10 項 Fixed、4 項 Partially fixed、0 項 Not fixed**。計算核心再次全數通過獨立重算（三棟共 200 項扭轉與變位 demand，零實質不一致）。扭轉框架已真正換成 ASCE 7-22 的 Type 1 / TIR；第一版懸而未決的「§12.3.3.6」經查正式目錄——**不存在，本節結案**。剩下的問題只剩一處條號錯誤（新 Finding N1）、數個 Minor 級的輸入防線與文件缺口。**目前定位：可以作為 EOR 簽章背書的計算附件；對外宣稱「ASCE 7-22」的最後一塊拼圖，是把 N1 的條號改對，並完成 §12 自承尚未做的正式文本逐條核對。**

---

## 一、第一版 Findings 裁定表

| # | 第一版問題 | 裁定 | 證據（本次實測） |
| :--- | :--- | :--- | :--- |
| F1 | 扭轉用 7-16 的 Type 1a/1b 框架、冒充 7-22；缺強度觸發 | **Fixed** | 檢核改名「Torsional Irregularity」，條文欄為「ASCE 7-22 Table 12.3-1, Type 1; Section 12.3.2.1.1」；30 層 Story20 TIR 1.55 由 FAIL 改為 WARNING；SDC E 全棟掃描無任何扭轉 FAIL。強度條件改由工程師輸入：未填時每一筆 PASS 的公式說明都附「strength criterion … not evaluated, confirm separately」，計算書參數表亦列「Lateral Strength > 75% on One Side of CM (12.3.2.1.1) \| Not evaluated」。此處理方式可接受——表格本來就沒有強度資料，工具把「未評估」寫在每一筆結果上，而不是假裝評估過。殘留問題見 N1（條號）與 N3（輸入粒度）。 |
| F2 | 單欄標題列讓 CSV 解析吐 pandas 原始錯誤 | **Fixed** | 同一輸入重送：HTTP 200，summary 與基準完全相同。 |
| F3 | WARNING 不列被觸發的後果（ρ、+25%、A_x） | **Partially fixed** | 後果已完整列出，且經 SDC B/C/D/E/F 五組掃描逐一核對（矩陣見第二節），內容與 SDC 對應正確。唯一未改對的是 +25% 那一項的條號：寫「per 12.3.3.4」，但 7-22 該條是「Elements Supporting Discontinuous Walls or Frames」，+25% 在 **§12.3.3.5**（見 N1）。 |
| F4 | 平均變位 = 0 讓扭轉檢核靜默消失、壞數據變 PASS | **Partially fixed** | avg = 0、max ≠ 0 → HTTP 422，訊息精確：「Story3: avg_drift_x_in is zero while max_drift_x_in is 0.38264; check the drift export」✓。兩者皆 0 → 扭轉改判 N/A 並附原因 ✓。但同一筆退化數據下，**變位檢核仍以 demand = 0.0 判 PASS 且無任何旗標**（見 N2）——第一版批評的「退化數據被洗成通過」在這一項上仍成立。 |
| F5 | 勁度 = 0 被誤診為「缺資料」 | **Fixed** | Story8 Stiff X = 0 重送：HTTP 200，該項改判 N/A，原因寫明「story stiffness <= 0 at Story8 (often a story-shear reversal under higher-mode response)」並給替代做法。連帶受影響的樓層集合也正確：N/A 出現在 Story5、6、7、8（本層或上方任一層 ≤ 0 的傳播範圍，與 §5.3 所述規則一致），不多不少。 |
| F6 | 計算書依據頁不自足（缺 I_e、樓板、偶發扭矩前提、輸入附錄） | **Partially fixed** | 已補：參數表含 I_e、樓板型式、例外條款是否套用、強度條件狀態、四種工況選取政策、單位；Scope and Basis 明文寫出「The input drifts are taken to include accidental torsion with A_x = 1.0」、質心近似的非保守警告、Not covered 清單。仍缺：(1) 輸入資料附錄（原始三張表未附）；(2) 實際採用的分析方法（ELF/MRSA）沒有記錄在計算書裡——只有一條 action 要 EOR「確認方法被允許」，但方法本身是什麼，文件沒寫。 |
| F7 | ρ 可填任意值（如 3.0）且套用到非彎矩構架無警告 | **Fixed** | ρ = 3.0 與 0.5 均回 422：「moment_frame_rho must be 1.0 or 1.3 (Section 12.3.4)」。非純彎矩構架的適用性仍靠使用者負責（文件已揭露），輸出端 `basis.rho_applied_to_drift` 可查，接受此處理。 |
| F8 | 負變位被靜默取絕對值 | **Fixed** | 回應含 `input_warnings`：「4 negative drift value(s) were converted to absolute values. … check that the right table was exported.」；匯出的計算書參數表亦有「Input Data Warnings」列印出同一訊息。 |
| F9 | flexible 樓板時檢核整項消失、不留痕 | **Fixed** | 30 筆扭轉檢核改為 N/A 並附原因（「Table 12.3-1 Type 1 applies only to rigid or semirigid diaphragms」）；summary 有 `total_not_applicable` 計數；計算書新增 N/A 彙總表（檢核＋原因逐項列出）；Story4 變位改回質心近似（0.01276）且依據切換在公式中可見。 |
| F10 | PASS 的扭轉列被誤標「Type 1a」 | **Fixed** | 新版計算書全文搜尋「Type 1a」：零出現。PASS 的軟弱層列只引「Table 12.3-2」不標型；扭轉列引「Type 1」——那是 7-22 該型的正式名稱，不是誤標。 |
| F11 | 計算書日期用 UTC、差一天 | **Fixed** | 以 `report_date: "2026-11-17"`（ISO 格式）匯出，日期正確印為 November 17, 2026。殘留：非 ISO 格式的字串（如 "November 17, 2026"）會被**靜默忽略**並退回伺服器 UTC 日期——第一版的失敗模式對 API 使用者仍在，只是網站路徑已修好（見 N4）。 |
| F12 | `max_dc_ratio` 混雜三種不同性質的比值 | **Fixed** | summary 改為「Maximum story drift D/C ratio \| 1.014」，只取變位 D/C；被標記項目表下方有 Ratio 語義註腳（不規則的 Ratio 只是距門檻距離、> 1 不代表違規）。附帶觀察：樓層總覽表的「Max Ratio」欄仍是混合值（Story1 顯示 1.47，那是軟弱層的比值，而它的 FAIL 來自變位 1.01）——文件 §6.3 已揭露此設計，註腳也在，接受；但總覽表旁若能比照加一行註腳會更好。 |
| F13 | 逐層逐向取最大變位工況，同一層檢核混用多工況且不可追溯 | **Fixed** | 用鑑別性測試驗證新選取規則：給 Story4 加 EQX3（Max = 0.5、Avg = 0.25、TIR = 2.0）——扭轉檢核取 EQX3（demand 2.0），變位檢核留在 EQX（0.01915），兩者各自正確；每項檢核有 `output_case`，計算書的被標記表與逐層明細都印出工況，公式說明亦註明「governing: EQX3」。勁度與例外 1 改為整棟每方向單一工況（計算書參數表列明政策）。第一版批評的物理不一致已按用途拆開處理，是正確的設計。 |
| F14 | 單位誤宣告（ft/in）無合理性檢查 | **Fixed** | 同一輸入重送：`input_warnings` 出現「Story heights range from 156.0 ft to 180.0 ft after unit conversion; check that the length unit matches the files.」，且印進計算書。 |

### 附帶結案：§12.3.3.6 不存在

第一版我曾引單一二手來源稱 7-22 可能新增「§12.3.3.6 torsional strength irregularity」。本版查 ASCE/SEI 7-22 正式出版文本目錄：§12.3.3 只有五個子節——.1 Prohibited Vertical Irregularities for SDC E or F、.2 Prohibited Vertical Irregularities for SDC D、.3 Extreme Weak Stories for SDC B or C、.4 Elements Supporting Discontinuous Walls or Frames、.5 Increase in Forces Caused by Irregularities for SDC D through F——**沒有 12.3.3.6**，全文搜尋亦無此條號。該二手來源（alpsconsult.net）的說法可排除；強度條件就是 Table 12.3-1 Type 1 定義的一部分，工具目前以工程師輸入處理，方向正確。

---

## 二、Action Items 觸發矩陣查核（對 §5.2 的承諾逐格驗證）

以 15 層範例（Story4 X 向 TIR = 1.50、Story1 極端軟弱層）改 SDC 重送，讀 Story4 扭轉檢核的 `actions`：

| SDC | 工具給的 actions | 查核 |
| :--- | :--- | :--- |
| B | 僅「Include accidental torsion per 12.8.4.2 (SDC B with TIR > 1.4)」；變位檢核用質心值（0.01276），不切邊緣 | ✓ 與 §5.2 承諾一致；邊緣變位的 C–F 限定也正確未套用到 B |
| C | 僅 A_x（§12.8.4.3） | ✓ |
| D | A_x、+25%（§12.3.3.4 → 應為 §12.3.3.5，見 N1）、確認 Table 12.6-1、ρ = 1.3（§12.3.4.2, TIR > 1.4） | 內容 ✓，一處條號 ✗ |
| E | D 的四項 + 「Apply orthogonal load combination per 12.5」；Story1 軟弱層 FAIL 附「not permitted in SDC E or F (12.3.3.1)」 | ✓ |
| F | 同 E | ✓ |

邊界與連動驗證（都通過）：
- TIR 恰 = 1.4 → WARNING，但 **不**觸發 ρ = 1.3（觸發條件是 > 1.4，正確）。
- 強度條件觸發的 WARNING（TIR 僅 1.08）→ actions 有 A_x、+25%、Table 12.6-1，**沒有** ρ = 1.3（ρ 是 TIR 觸發的，工具分得很清楚）。
- 強度條件觸發後，SDC D 下各層變位檢核連動改用邊緣變位（Story1 X：0.02028 → 0.0219），與 §5.4 的規則一致。

未能對照正式文本的部分（標示未驗證）：§12.8.4.2 在 7-22 中「SDC B 僅 TIR > 1.4 才需計入偶發扭矩」的門檻原文；ρ = 1.3 在 SDC E/F 是否同樣由 TIR > 1.4 觸發（工具在 D/E/F 都給，二手來源如 WoodWorks 文件支持 D–F 皆然）；§12.5 正交組合在 SDC D 是否也應列（Trimble 的彙整表曾把 100/30 列入 SDC D 扭轉後果，工具只在 E/F 給）——這三點需要 Table 12.3-1 的引用欄與 §12.3.4.2、§12.5.4 原文才能定案，本版不據此列 finding。

---

## 三、手算複核（第二版）

以第一版的獨立程式邏輯、依新版 §5 的工況選取規則（TIR 取最大 TIR 工況、變位取最大變位工況、扭轉不規則且 SDC C–F 時變位改用邊緣值）重算三棟全部樓層的扭轉與變位 demand，與 live API 輸出逐項比對：**200 項，零實質不一致**（30 層 Story30 變位有一處 0.00126 對 0.001265 的末位四捨五入差異，是輸出取位，不是算錯）。live 輸出與網站預算 `result.json` 三棟 summary 完全一致。

重點樓層（狀態已依新框架更新）：15 層 Story1——軟弱層 X/Y WARNING（dc 1.472）、變位 X FAIL（0.02028）；Story4——扭轉 X WARNING（TIR 1.50）、變位 X 用邊緣值 0.01915 PASS。30 層 Story12——軟弱層 X/Y FAIL（dc 1.38）、變位 X FAIL（0.01634, dc 1.09）；Story20——扭轉 Y WARNING（1.55），不再是 FAIL。5 層 Story2——扭轉 X WARNING（1.30），actions 無 ρ（1.30 ≤ 1.4，正確）。

---

## 四、新功能破壞測試結果

| 測試 | 結果 |
| :--- | :--- |
| 單一方向輸入（拿掉全部 Y 向變位列） | ✓ 200；每層產生一筆「Y-Direction Checks」N/A，`basis.directions_checked = ["X"]`，並有輸入警告說明 |
| Tab 分隔 .txt（模擬 ETABS 複製貼上） | ✓ 結果與基準完全相同 |
| 多工作表 Excel（三張表各一分頁 + 一張垃圾分頁） | ✓ 結果與基準完全相同，垃圾分頁被忽略 |
| Step Type 欄（Max 列為真值、Min 列塞垃圾值 9.99/3.33） | ✓ 結果與基準完全相同，Min 列確實被丟棄 |
| 無 Direction 欄、方向寫在 Item（`Diaph D1 X`） | ✓ 結果與基準完全相同 |
| TIR 恰 = 1.2 | ✓ PASS（不規則條件是 > 1.2） |
| TIR 恰 = 1.4 | ✓ WARNING 且不觸發 ρ = 1.3 |
| r1 恰 = 0.70（4200/6000） | ✓ PASS，公式印出「0.700 (limit 0.70) -> No Soft Story」 |
| 變位恰 = 限值（Δ/h = 0.0200） | ✓ PASS，公式印出「0.0200 <= 0.0200」 |
| 4 層以下限值用在 15 層建築 | ✓ 以 `structure_type` 選用時回 422，訊息寫明「applies to buildings of 4 stories or fewer (Table 12.12-1); this building has 15」 |
| `torsion_strength_irregular: false` | ✓ 結果與未填相同（但公式說明不記錄「已評估為否」，見 N3） |
| 未知欄位（`four_story_or_less_drift_tolerant: true` 布林） | 被靜默忽略、回 200（見 N5） |

門檻邊界四項全對：工具一致地用嚴格不等號（> 觸發、≤ 通過），與條文文字（"exceeds"、"less than"）相符，第一版未測的浮點邊界在本版的乾淨小數構造下沒有出現誤判。

---

## 五、新 Findings

| # | Severity | Area | 我做了什麼 | Expected | Actual | Code section |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| N1 | **Major** | 條文引用 | 讀 SDC D/E/F 下扭轉 WARNING 的 actions 與計算書 Action Items 表，並對照 ASCE/SEI 7-22 正式出版文本目錄 | +25% 設計力增量的出處應為 7-22 的條號 | 工具寫「per 12.3.3.4」——那是 **7-16** 的編號；在 7-22，§12.3.3.4 是「Elements Supporting Discontinuous Walls or Frames」，+25% 增量在 **§12.3.3.5**「Increase in Forces Caused by Irregularities for Seismic Design Categories D through F」。內容（D–F、+25%、樓板連接與集力構件）正確，只有條號差一位——但這正是第一版 F1 的同類錯誤（版本混用）在修正後殘留的一處，而且它印在計算書要給審圖者看的表格裡 | ASCE 7-22 §12.3.3.5（7-16 為 §12.3.3.4） |
| N2 | Minor | 資料有效性 | 把 Story3 的 Max 與 Avg Drift 同時改成 0.0 | 兩項受影響的檢核都應標記資料異常（N/A 或警告） | 扭轉改判 N/A ✓，但變位檢核以 demand = 0.0 判 PASS、無任何旗標。一棟中間樓層變位恰為零在物理上不可能（鄰層約 0.35 in），這是匯出錯誤的典型樣貌，卻被洗成全棟最乾淨的一筆 PASS | §12.12（資料前提） |
| N3 | Minor | 輸入設計 | 送 `torsion_strength_irregular: true` | 強度條件是逐層的（「任一樓層」其樓板下方強度分布），輸入粒度應能對應，或至少揭露套用範圍 | 單一全棟布林被套用到全部 30 筆樓層×方向檢核：warnings 由 3 變 32，且 SDC C–F 下每一層的變位檢核連動改用邊緣變位（此連動本身合規）。工程師若只知道「某一層」有此狀況，無法只標那一層。另外 `false` 時公式說明不留下「已評估、結果為否」的紀錄，與 `null` 的「not evaluated」不對稱 | §12.3.2.1.1 / Table 12.3-1 Type 1 |
| N4 | Minor | API／文件 | 以 `report_date: "November 17, 2026"`（非 ISO 格式）匯出計算書 | 格式不符應報錯或至少警告；接受的格式應寫在文件裡 | 靜默忽略，退回伺服器 UTC 日期（印出 November 18）——與 F11 原始症狀相同。ISO 格式（"2026-11-17"）正常。`PROJECT_REVIEW.md` §6.2 只說「前端另加 report_date」，未註明格式 | —（report_builder） |
| N5 | Minor | API | 在 project_info 加入不存在的欄位（`four_story_or_less_drift_tolerant: true`） | 未知欄位應被拒絕或回報 | 靜默忽略、回 200 與正常結果。風險在對稱面：把 `moment_frame_rho`、`torsion_strength_irregular` 這類選填欄位拼錯時，使用者會拿到一份「看起來正常、但少算了東西」的結果而無從察覺（`basis` 有回顯實際採用參數，可部分緩解，但前提是有人去看） | —（API 契約） |

其餘觀察（不列 finding）：SDC B/C 下軟弱層 WARNING 的 `actions` 為空清單——這兩個 SDC 對軟弱層本來就沒有額外強制要求，空清單是誠實的；30 層 Story30 的 demand 有末位取位（0.00126），無實質影響。

---

## 六、Word 計算書複審（任務 5）

以 15 層範例重新匯出（含補填 project_number / company / engineer 測試欄位渲染——三者都正確印出，補上了第一版的未驗證項），並另匯出 flexible、EQX3、多工況、負變位、ft 單位五種變體交叉檢查。

**現在可以作為洛杉磯送審的計算附件**（由 EOR 簽章背書的前提不變）。第一版缺的依據頁這次補齊了大半：解析參數（含預設值）逐項列出、偶發扭矩前提寫進 Scope and Basis、質心近似附非保守警告、Not covered 清單誠實、Action Items 表附「Done (initials)」簽核欄、N/A 彙總表附原因、輸入警告（負變位、單位）會印進參數表、每一筆被標記的檢核都帶工況欄。

還差的（按重要性）：
1. **N1 的條號就在這份文件的 Action Items 表裡**——送審前改掉，這是審圖者最容易一眼看到的一處。
2. **沒有輸入資料附錄**：計算書引用的是「EQX 工況、某層變位若干」，但原始三張表不在文件內，審圖者無法從文件本身追溯輸入。附上輸入表（或其雜湊/檔名+工況清單）是低成本的補強。
3. **實際分析方法未記錄**：文件要 EOR 確認「方法被 Table 12.6-1 允許」，卻沒寫方法是什麼。參數表加一行「Analysis procedure used (engineer input)」即可閉環。

---

## 七、三句判定

1. 引擎算術第二輪再次全數通過獨立重算（200 項 demand 零實質不一致），第一版 14 項 findings 有 10 項完全修好、4 項部分修好、0 項未修，解析器對真實世界格式（標題列、貼上表格、多分頁 Excel、Step Type、Item 方向、單一方向）的防線這次都實測站住了。
2. 扭轉框架已是真正的 ASCE 7-22 Type 1 / TIR，「§12.3.3.6」經查正式目錄確定不存在，第一版留下的規範疑點只剩三處需原文定案的 action 門檻（已在第二節標示未驗證），不影響目前結論。
3. **最重要的一件下一步**：把 +25% 增量的條號從 §12.3.3.4 改成 §12.3.3.5——這份產品的全部價值就是條文引用正確，而這是目前唯一一處印在計算書上、會被審圖者直接跟著查到錯誤條文的引用。

---

## 附錄：測試產物

- 本輪工作資料夾 `~/workspace/story-check-retest/`：三棟範例與 live/預算結果（`result_live.json`、`result_precomputed.json`）、全部邊界測試的請求與回應（`edge2/`，含 SDC 掃描、F 系列重跑、新功能破壞測試）、六份匯出的計算書（`report_v2_*.docx`）、測試腳本 `retest1.py`、`retest2.py`。
- ASCE/SEI 7-22 條號查核依據：正式出版文本（ASCE/SEI 7-22, ISBN 978-0-7844-1578-8）目錄全文，於 2026-11-17 經公開預覽副本讀取；§12.3.3 子節清單與 §12.3.3.5 標題均出自該目錄。條文本文未能取得的部分已在文中標示未驗證。
