# Story Check 第二版反饋與第二輪線上重測

版本：V2／第二版  
日期：2026-11-17（America/Los_Angeles）  
對照：STORY_CHECK_REVIEW_2026-11-17.md  
範圍：AI_RETEST_PROMPT.md 的共同要求與 Codex 追加段落。

## 結論

上一輪指定案例多數已修正，但新測試仍可讓實際超限的變位顯示 PASS，尚不能視為可直接送審的合規檢核工具。
最重要的下一步是保留逐列、逐工況、逐步階資料，按實際檢核量選控制結果，取消「先以最大邊緣變位選一列，再拿該列平均值檢核」的方式。
規範後續要求與軟弱層例外仍須正版 ASCE 7-22 覆核；本報告把無法以正式出版文本確認的判讀標為 **unverified**。

## 證據與限制

- 先確認線上 GET /api/health 回應 {"status":"ok"}，再測試。
- 所有下列 HTTP 結果均來自 https://story-check-api.onrender.com/api/analyze；不是只跑本機引擎。
- 重跑第一輪 14 組變異測試，另測 Tab、多工作表 Excel、Item 方向、步階、強度條件、N/A、邊界值與工況選取反例。
- 重新下載三棟樓範例的 CSV、project.json、result.json；三組線上 analyze 回應均與各自預算 result.json 完整相等。
- 閱讀目前本機 backend/code_checker.py、backend/parser.py、backend/main.py、backend/report_builder.py，以及 PROJECT_REVIEW.md 第 12 節。
- 本機原始碼與線上現象相符，但無線上部署 commit ID 可完整證明部署版本。
- 未修改應用程式碼；未執行整套專案測試；未測瀏覽器互動與貼上框本身，Tab 測試是上傳 .txt 到 API。
- 審查者不具加州 SE 執照；未取得完整正版 ASCE 7-22 與適用增補逐條核對，因此不是工程認證。
- 使用前一輪已讀的 documents 技能檢查 Word，並用 LibreOffice 渲染為 PDF；不是 Microsoft Word 原生排版驗證。
- 原始回應、樣本、測試腳本、Word 與渲染 PDF 已保存在同資料夾下 review_v2_evidence/。腳本仍引用本次工作目錄 /tmp/story-check-retest；移機重跑須調整路徑。

## 一、原問題判定

第一輪主要問題表未編號；本版依原表順序補上 F1–F10，供後續追蹤。

| 原問題 ID | 判定 | 本次請求與證據 |
|---|---|---|
| F1 舊版扭轉分類及 E/F 禁止條件 | Fixed（就原案例） | SDC 改 E；HTTP 200，3 FAIL／1 WARNING。Story4 X 扭轉為 Type 1 WARNING，Story1 X/Y extreme soft story 仍 FAIL，另有 Story1 X 變位 FAIL。後續 action 正確性另列，不代表全面規範認證。 |
| F2 漏最大 TIR 工況 | Partially fixed | 原案例新增 EQX_HIGH_RATIO，Story4 X Max＝0.5、Avg＝0.25；200，TIR＝2.0、output_case＝EQX_HIGH_RATIO。相同工況內多步階仍漏，見 N2。 |
| F3 15 層可選四層以下限值 | Fixed（層數限制） | structure_type＝four_story_or_less_drift_tolerant；422，說明僅適用四層以下、此棟為 15 層。其他裝修及系統適用條件仍靠工程師確認。 |
| F4 ρ＝0.5 可放寬限值 | Fixed（值域） | moment_frame_rho＝0.5；422：must be 1.0 or 1.3，got 0.5。未驗證結構是否適用此除法。 |
| F5 兩端平均代替質心 | Not fixed（計算） | 仍使用平均變位；報告已明示可能不保守。揭露限制不等於修正數值來源。 |
| F6 強度條件無輸入且仍 PASS | Partially fixed | true／false／null 可輸入；null 顯示 not evaluated，但仍給 PASS；true 會套到全棟兩方向，且零變位時被 N/A 提前返回，見 N5。 |
| F7 單欄 CSV 標題解析失敗 | Fixed | 同原測試在 Story Definitions 前加 ETABS Story Definitions 單欄行；200，摘要與基準相同。 |
| F8 零勁度誤報缺資料 | Fixed（原案例） | Story1 X/Y 勁度改零；200，兩項 soft-story N/A，含 stiffness <= 0 原因；不再是 missing data。 |
| F9 錯選合法單位無提示 | Partially fixed | length_unit＝mm；200，input_warnings 指出層高約 0.5–0.6 ft、要求核對單位。原始來源單位與檔案識別仍未完整留存。 |
| F10 工況與報告可追溯性不足 | Partially fixed | 每項有 output_case，另列 stiffness／exception 工況；但缺 Step Type／Step Number、TIR 控制列的成對原始數據及檔案識別。多步階仍先被折疊。 |

### 第一輪 14 組變異測試逐項重跑

共同請求：multipart 上傳三份 15 層 CSV，project_info 採線上 project.json，除表列變更外維持原值。每個案例的 JSON 回應檔均在 review_v2_evidence/，名稱為下列證據鍵加 .json。

| # | 請求變更／證據鍵 | 第一輪 | 第二輪回應 | 判定 |
|---|---|---|---|---|
| 1 | length_unit＝banana／wrong_unit | 422 | 422：unsupported unit 'banana' | Fixed／維持正確拒絕 |
| 2 | length_unit＝mm／wrong_valid_unit | 200，無提示 | 200，增加不合理層高警告；D/C 仍相同 | Partially fixed |
| 3 | 移除 stiffness CSV／missing_file | 422 | 422：missing table(s): stiffness | Fixed／維持正確拒絕 |
| 4 | 單欄標題行／extra_header | 422 tokenizing error | 200，正常分析 | Fixed |
| 5 | Story1 X/Y stiffness＝0／zero_stiffness | 422 缺資料 | 200，2 N/A、具原因 | Fixed |
| 6 | 三表 Story1 改第一層／chinese_names | 200 | 200，action stories 也保留第一層 | Fixed／維持正常 |
| 7 | 所有 Max/Avg Drift 改負值／negative_drifts | 200 無提示 | 200，警告 60 個負值取絕對值 | Fixed（提示） |
| 8 | 移除全部 Y drift 列／only_x | 422 | 200，15 筆 Y-Direction Checks N/A，basis 僅 X，另有警告 | Fixed（新設計） |
| 9 | diaphragm＝flexible／flexible | 200，直接略過 | 200，30 筆 torsion N/A | Fixed（留痕） |
| 10 | SDC＝B／sdc_b | 200 | 200，Story4 加 SDC B／TIR>1.4 偶發扭矩 action | Partially：程式觸發可見，正式條文 unverified |
| 11 | SDC＝E／sdc_e | 4 FAIL | 3 FAIL、1 WARNING；錯誤扭轉 FAIL 消失，軟弱層 FAIL 保留 | Fixed（原誤判） |
| 12 | 四層以下限值選項／four_story_option | 200，變位 FAIL 消失 | 422，指出 15 層不適用 | Fixed |
| 13 | moment_frame_rho＝0.5／rho_half | 200，變位 FAIL 消失 | 422，僅接受 1.0 或 1.3 | Fixed |
| 14 | Story4 X 新工況 0.5／0.25／missed_governing_ratio | 錯報 TIR＝1.5 | 200，TIR＝2.0，工況 EQX_HIGH_RATIO | Fixed（此精確案例）；廣義問題仍 Partially |

原正常分析本次為 1 FAIL、3 WARNING、summary.max_dc_ratio＝1.014；第一版的 1.472 是混合比值，不應拿兩者直接判斷需求變小。

## 二、新發現

| ID／嚴重度 | 範圍 | 我做了什麼 | 預期 | 實際 | 條文／依據 |
|---|---|---|---|---|---|
| N1 critical | 變位控制工況 | 兩層、h＝100、Cd＝Ie＝1；A 工況 Max/Avg＝2.1/1.8，B＝2.05/2.04；兩者 TIR<1.2 | 依目前平均值方法，B 的變位角＝0.0204，應 FAIL | 選 Max 較大的 A，兩層都報 0.018 PASS，overall PASS | §12.8.6、Table 12.12-1；算術反例明確，不依賴質心近似是否正確 |
| N2 major | 同工況多步階 TIR | 15 層 EQX，Step 1 原值；Story4 X Step 2＝0.5/0.25 | 最大 TIR＝2.0，保留步階來源 | HTTP 200，仍為 1.5；只有一個 case 名稱時不計 TIR envelope | §12.3.2.1.1；步階是否適合 TIR 另須確認，但不能靜默折疊 |
| N3 critical | 無條件刪 Min | 兩層 case A：Max 列 1/1，Min 列 -3/-3，h＝100、Cd＝1 | 若為有效 signed envelope，幅值 3 對應變位角 0.03；或明確拒絕此類輸出 | 一律刪 Min，回 0.01 PASS、overall PASS | 解析器支援範圍／§12.8.6；此非真實 ETABS 檔，實際表格語意 unverified |
| N4 major | 軟弱層例外工況 | 三層 A 平均變位皆 1，總和 3；B 自下而上 0.9/0.1/0.1，總和 1.1；S1 K＝50、S2/S3＝100 | B 相鄰層比為 9，不能由最大總變位推論所有相關工況符合 1.3 | 只選 A，以倍數 1.0 豁免 S1，soft-story PASS | §12.3.2.2；何種載重必須納入例外的正式判讀 unverified，但自動選取並非最不利 |
| N5 major | 強度條件被零變位遮蔽 | 全部變位為 0，同時 torsion_strength_irregular＝true | TIR 不可算，仍應保留已知強度不規則及後續要求 | torsion N/A，整體 PASS，無扭轉 action | Type 1 的獨立強度條件；精確條文 unverified；與目前自身邏輯矛盾 |
| N6 major | 非控制原始列未驗證 | Story4 X 另加 case BAD，Max＝0.1、Avg＝0 | 依宣稱契約拒絕非零 Max／零 Avg | 200；該列沒選為 drift 控制列，也被 TIR 分母過濾，故未拒絕 | 資料驗證；selected_zero_avg 案例則確實 422 |
| N7 major | ρ action 過度簡化 | 原範例只有 X TIR＝1.5、Y＝1.05；SDC D | 釐清同層雙方向條件後再給確定要求 | 單方向即列 Use rho＝1.3；與 Tekla 的 both directions 條件不一致 | §12.3.4.2／相關子節；正式文本 unverified |
| N8 major | D 類正交組合提示可能缺漏 | actions_D 用原範例重跑 | 核對 D 類 Type 1 的正交要求 | 只有 E/F 加 orthogonal action；D 無此項 | §12.5；Tekla D 類列有 100/30，正式文本 unverified |
| N9 minor | 布林值型別 | torsion_strength_irregular 傳 JSON 字串 "false"，對照布林 false | 422，或有明確解析規則 | 字串被 bool() 轉 true；warnings 3→32，最大變位 D/C 1.014→1.095 | API 型別驗證；不是前端已證實的操作問題 |
| N10 major | 不適用與未知混成 N/A | 單方向／零勁度／零 drift 案例 | 不適用、資料不足、不可算應區分，摘要顯示未完成檢核 | N/A 嚴重度低於 PASS；可 overall PASS 且仍有未完成項目 | QA 狀態設計；不代表已完成的單項 PASS 錯誤 |
| N11 minor | Word 排版 | 匯出 15 層報告並渲染全部 25 頁 | 續頁有欄名，公式不任意斷頁 | 第14頁底出現下一層表頭與首列碎片；第25頁僅餘公式尾段；續頁無重複欄名 | 計算附件可讀性；LibreOffice 渲染結果 |

N1、N2、N4、N5 是本輪最值得先處理的資料／判定問題。N7、N8 是有來源衝突的規範疑點，不能在尚未取得正式文本時宣稱已完成法規定論。

### N1 可重現輸入

project_info 重點：risk_category＝II、SDC＝D、structure_type＝other、diaphragm＝rigid、cd＝1、ie＝1、apply_soft_story_exception＝false、torsion_strength_irregular＝false；沒有自訂 drift limit 或 ρ。

```csv
Story,Height,Elevation
S2,100,200
S1,100,100
```

```csv
Story,Output Case,Direction,Max Drift,Avg Drift
S2,A,X,2.1,1.8
S1,A,X,2.1,1.8
S2,B,X,2.05,2.04
S1,B,X,2.05,2.04
```

```csv
Story,Output Case,Stiff X,Stiff Y
S2,EQX,100,100
S1,EQX,70,70
```

回應檔：missed_average_drift.json。A 的 TIR＝1.1667，B＝1.0049；兩者均不觸發 TIR 不規則，所以即使沿用工具自己的平均變位方法，B 的 2.04/100＝0.0204 也應超過 0.020。實際回傳兩層 drift demand_value＝0.018、status＝PASS、output_case＝A。

## 三、新功能與邊界測試

| 功能／證據鍵 | 結果 |
|---|---|
| Tab 分隔 .txt／tabs | 200，摘要與基準相同；測的是 API 格式支援，未測實際 ETABS Ctrl+C 或網站貼上框。 |
| 三工作表單一 .xlsx／workbook | 200，三張必要表可從同一 workbook 讀入。未涵蓋多餘帶 Story 欄的非必要表。 |
| Item 取代 Direction／item | Diaph D1 X／Y 正常辨識，200。 |
| Step Type Min／step_min | 人工較大 Min 列被丟棄，200；這僅證明目前設計，是否安全取決於資料語意，見 N3。 |
| 同 case 多 Step／same_case_step | 失敗案例，TIR＝2.0 被漏掉。 |
| 非零 Max／零 Avg 為控制列／selected_zero_avg | 422，明確指出 Story4、avg_drift_x_in 為零、Max＝0.54303。 |
| 同問題出現在非控制列／nonselected_zero_avg | 200，漏驗，見 N6。 |
| 強度 true／strength_True | 200；即使 Y TIR＝1.05 也全棟判 WARNING。單一全棟旗標無法表達特定樓層／方向的強度分布，屬粒度限制。 |
| 強度 false／strength_boolean_false | 200，3 warnings；低 TIR 方向維持 PASS。 |
| 強度 null／strength_None | 200，PASS 文字附 strength criterion not evaluated；仍須明顯標出未完成判定。 |
| 字串 false／strength_string_false | 被當 true，見 N9。 |
| 強度 true＋零 drift／zero_strength_true | N/A 提前返回，見 N5。 |
| 精確門檻／thresholds | S1 TIR＝1.2 PASS；S1 r1＝0.70 PASS（例外停用，僅兩層無 r3）；S2 drift＝0.02000 PASS。 |

注意：現行 parser 先轉換、再將每個數值 round 到六位小數，這會限制更細門檻附近的判讀精度；本次沒有再用極微小擾動宣稱新的工程誤判。

## 四、扭轉 action items 的條文核對

本節所有「正式文本」狀態均為 **unverified**。可取得的 Tekla 官方更新說明是原廠實作說明，可交叉比對，不能取代 ASCE 出版文本；本次搜尋亦發現其他來源混用舊版詞彙，未據此直接作定論。

| Action | 本機／線上實際觸發 | 交叉核對結論與限制 |
|---|---|---|
| Ax，§12.8.4.3 | Type 1，SDC C–F | 與 Tekla 概述相符；分析方法與例外未建模，正式適用條件 unverified。TIR 用 Ax＝1 的工況與設計變位用放大後工況應分離，單一 CSV 集合目前沒有驗證兩種用途。 |
| 偶發扭矩，§12.8.4.2，SDC B | B 且 TIR>1.4 | 與 Tekla 概述相符；正式文本 unverified。 |
| +25%，§12.3.3.4 | D–F 的 Type 1 均加 | 缺少構件類別、例外與是否已有 overstrength 設計等資訊；本次無正式文本確認完整條件，unverified。建議用「確認是否適用」而非無條件命令。 |
| Table 12.6-1 | D–F 觸發不規則即提醒 | 作為人工確認提示可接受；缺高度、週期等完整條件，不能聲稱已決定 ELF 是否允許。確切 7-22 條件 unverified。 |
| ρ＝1.3，§12.3.4.2 | D–F，任一方向 TIR>1.4 | Tekla 概述要求 both directions；現行單方向觸發有衝突，見 N7，正式文本 unverified。Action 也不會自動改 basis 的 rho_applied_to_drift，必須區分提醒與實際採用。 |
| §12.5 正交組合 | 只在 E/F 的扭轉不規則列出 | Tekla 概述的 D 類亦列正交組合，現行 D 可能漏提示；正式文本 unverified。E/F 若無扭轉，本工具亦無此 action；是否有獨立於扭轉的要求須按 §12.5 逐條覆核。 |

actions_A/B/C/D/E/F.json 保存了完整觸發清單。A 無扭轉 action；B 只列偶發扭矩；C 列 Ax；D 列 Ax、+25%、分析方法與 ρ；E/F 再加正交組合。

不能僅因提示表列了 action，就將該要求視為已完成；也不能把「請確認分析方法」當作工具已檢查 Table 12.6-1。

## 五、手算再核對與預算輸出

15 層使用 Cd＝5.5、Ie＝1；30 層依回應 basis 使用 Cd＝5.5、Ie＝1.25。下表變位仍沿用工具現行平均／最大選值方式，並非認可其質心近似。

| 建築／層／方向 | TIR 手算 | K/K上一層 | K/K上三層平均 | 設計變位角手算 | API／result.json |
|---|---:|---:|---:|---:|---|
| 15層 Story1 X | 1.080005 | 0.520834 | 0.543478 | 0.0202800 | 一致（顯示精度內），drift FAIL |
| 15層 Story1 Y | 1.050005 | 0.520834 | 0.543479 | 0.0176348 | 一致 |
| 15層 Story4 X | 1.500000 | 1.047618 | 1.100000 | 0.0191453 | 一致 |
| 15層 Story4 Y | 1.050000 | 1.047619 | 1.100000 | 0.0110987 | 一致 |
| 30層 Story12 X | 1.080011 | 0.564474 | 0.579730 | 0.0163426 | 一致 |
| 30層 Story12 Y | 1.050016 | 0.564474 | 0.579730 | 0.0142109 | 一致 |
| 30層 Story20 X | 1.080029 | 1.033333 | 1.068965 | 0.0078241 | 一致 |
| 30層 Story20 Y | 1.549996 | 1.033333 | 1.068965 | 0.0105456 | 一致 |

例：30 層 Story12 X，K＝9859.26，上方 K＝17466.29、17006.65、16547.01，Max/Avg＝0.62578/0.57942，h＝156。變位角＝5.5×0.57942/1.25/156＝0.0163426；Risk III 的 other 限值＝0.015，故 FAIL。

30 層 Story20 Y：Max/Avg＝0.37389/0.24122，TIR＝1.549996；採最大變位時 5.5×0.37389/1.25/156＝0.0105456。扭轉為 WARNING，沒有舊版 extreme torsion FAIL。

三棟預算結果均與線上相等只證明部署樣本同步，不是獨立規範驗證；上述反例仍可在相同引擎重現。

## 六、Word 計算附件

本次正常報告為 44,568 bytes，可下載並讀取，另匯出僅 X 資料的 report_na.docx。

已確認補入：實際 Ie＝1.0、rigid diaphragm、逐項 output case、強度條件 Not evaluated、drift-only 最大 D/C、action 簽核表，以及單方向案例的 N/A 原因表。report_na 明確傳入 report_date＝2026-11-17，報告顯示 November 17, 2026；未傳日期的 API 基準報告仍使用伺服器日期，不能視為後端自動知道使用者時區。

仍不能稱為可直接提交的完整計算附件：

1. N1 等錯誤會直接進入附件，應先修計算資料選取。
2. 兩端平均近似質心仍可能不保守；應標示為暫估結果或要求工程師確認，不能僅以免責文字取代資料。
3. 每項 output case 已補，但欠步階、原始數值對、檔案版本及部署／規則版本。
4. 強度條件未評估仍顯示 PASS，未完成條文與已核算合格需分開。
5. Ax＝1 的 TIR 資料與可能包含放大偶發扭矩的 drift 資料未明確分離；報告假設與 action 不應互相混淆。
6. +25%、ρ、正交與分析方法的實際適用條件未完成正式核對，不能用自動 action 代替工程簽核。
7. LibreOffice 渲染為25頁，檢視所有頁面縮圖，並放大第14與25頁：續頁無重複欄名、同一公式列跨頁、末頁只有公式尾段。需加寬 Calculation 欄、合理分配欄寬、重複表頭及控制列／段落跨頁。
8. 缺真實 ETABS 專案端到端驗證；是否獲洛杉磯 plan checker 接受，取決於適用法規版本、整套計算文件與負責工程師審核，本次不能保證。

## 七、工況選取的建議設計

「逐層 envelope、勁度整棟同一工況」比原版少了一部分混用，但依最大剪力挑一個工況不保證勁度比最不利；依總平均變位挑例外工況也沒有最不利保證。同一工況內仍 groupby max 更會混掉步階，不能只憑 case 名相同就視為同一物理狀態。

建議保留資料主鍵：story、direction、diaphragm、case/combo、step_type、step_number、原始列識別與來源檔案，避免解析階段先不可逆折疊。讓檢核層分別執行：

- TIR：在合適的 ELF／偶發偏心、Ax＝1 資料內計算每一對 Max/Avg，再取控制比；不用 case 名數量決定是否 envelope。
- Drift：先決定適用位置與資料類型，逐列計算實際設計變位角，再選控制值。
- Soft story：指定經工程確認的勁度評估工況或逐一比較可用完整工況；不要宣稱最大剪力一定控制勁度比。
- Exception 1：用工程師指定、符合條文用途的完整工況；若自動處理多工況，應逐工況評估相鄰層比例，不能以總變位排序代替。
- Step Type：依 case type 及表格語意解讀 signed envelope，不能一律把 Min 當無效。無法支援時明確拒絕並說明支援範圍。
- Validation：在挑控制列之前驗證所有候選原始列，不能讓壞資料因未控制而消失。
- Status：增加「未完成／資料不足」的 completeness 狀態，與工程 demand/capacity 判定分開。

## 八、外部來源與驗證界線

- [Trimble／Tekla 官方 ASCE 7-22 updates](https://help.trimble.com/doc/tekla-structural-designer/2025/asce7_22_updates)：本次重新查閱，用於交叉比對扭轉、SDC、ρ與正交要求；屬原廠實作說明，非規範原文。
- [FEMA P-749](https://www.fema.gov/sites/default/files/documents/fema_p-749-earthquake-resistant-design-concepts_112022.pdf)：第一版使用的政府說明來源，支持新版移除 extreme torsional irregularity 的架構；本次未依它推導完整 action 條件。

正式 ASCE 7-22、適用 errata／supplement、§12.3.2.2 例外、§12.3.3.4 完整例外、§12.3.4.2 的方向與同層條件、§12.5、Table 12.6-1 的完整高度／週期／分析方法條件，均保留 **unverified** 標註。不得將此報告當成上述條文已全面核准。
