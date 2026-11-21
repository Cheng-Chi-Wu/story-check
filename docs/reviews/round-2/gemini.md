# Story Check：第二版（V2 / Round 2）QA 審查與技術反饋報告（by Gemini）

**審查版本：** 第二版（Round 2 Re-Test）  
**審查日期：** 2026-11-17  
**審查角色：** Senior Structural Engineer Role (California SE Perspective) & QA Tester (Gemini)  
**目標系統：** Story Check (`https://story-check-virid.vercel.app` / `https://story-check-api.onrender.com`)  
**規範依據：** ASCE 7-22 Chapter 12 (Seismic Design Requirements for Building Structures)  

*(註：本環境無終端機與外部即時網路存取權限，以下針對 `AI_RETEST_PROMPT.md` 與 `PROJECT_REVIEW.md` 揭露之新版邏輯進行靜態規範與架構複審，僅能透過實際執行環境確認的項目已標註為 `unverified`。)*

---

## 一、 第一輪審查項目複驗結果（Round 1 Findings Verdict）

| Original Finding ID | Verdict | Evidence & Technical Assessment |
| :--- | :--- | :--- |
| **F1 (Critical): Center of Mass Drift Approximated by `avg_drift`** | **Partially fixed** | **已改進處**：在報告與 `basis` 欄位中已明確揭露「以兩端平均變位近似質心變位」的限制。<br>**仍待補強**：在 L 型、T 型或質量偏心建築中，兩端幾何平均仍不等於質心變位（可能低估 15%~30%），建議在報告中明確限定適用範圍（僅適用於矩形對稱剛性樓板，不規則平面應改用 ETABS *Diaphragm Center of Mass Displacements*）。 |
| **F2 (Critical): Torsional Amplification Factor $A_x$ Not Computed** | **Partially fixed** | **已改進處**：當 SDC C–F 觸發扭轉不規則時，已在 `actions` 與 `summary.action_items` 中加入 §12.8.4.3 追蹤提示。<br>**仍待補強**：計算 $A_x = (\text{TIR} / 1.2)^2$（限制於 $[1.0, 3.0]$）只需要你已經算出的層間變位比 TIR，**不需要各層絕對位移**。以 $\text{TIR} = 1.50$ 為例，$A_x = (1.50/1.20)^2 = 1.5625$（偶發偏心率需從 $5\%$ 調高至 $7.81\%$）。目前未直接算出 $A_x$ 數值，且在 `drift_is_amplified: false` 時仍用未放大變位判定 `PASS`，對使用者有低估變位風險。 |
| **F3 (Critical): §12.3.2.2 Exception 1 ("Without Accidental Torsion")** | **Partially fixed** | **已改進處**：例外條款 1 已改為整棟建築單方向採用一致的控制工況（最大總平均變位），不再逐層混用不同工況。<br>**仍待補強**：ASCE 7-22 §12.3.2.2 Exception 1 規定變位角計算**不得包含偶發扭矩**。若用戶匯入含 5% 偶發偏心的工況，在扭轉耦聯建築中 `avg_drift` 仍受扭轉影響，建議在 `input_warnings` 中加註提醒。 |
| **F4 (Major): Soft Story Stiffness Inflection Points ($K \le 0$)** | **Fixed** *(logic verified; live API unverified)* | **已改進處**：當樓層勁度 $\le 0$（高層反曲點效應）時，不再誤判或除以零當機，而是正確回傳 `N/A` 並附上原因。 |
| **F5 (Major): ASCE 7-22 Torsional Framework (Type 1a/1b vs. Single Type 1 TIR & Table 12.6-1)** | **Fixed** *(code alignment verified; live API unverified)* | **已改進處**：修正第一輪誤用 ASCE 7-16（Type 1a/1b 與 Table 12.6-1）的敘述。**新版採用 ASCE 7-22 單一 Type 1 扭轉不規則（$\text{TIR} > 1.2$ 或 $>75\%$ 單側抗側力強度，§12.3.2.1.1），且移除 SDC E/F 禁止條款與刪除 Table 12.6-1**，完全符合 ASCE 7-22 正式規範精神。 |
| **F6 (Major): Multi-Load Case Mixing Across Stories** | **Partially fixed** | **已改進處**：軟弱層勁度與 §12.3.2.2 例外 1 已改為整棟單一控制工況；Drift 與 TIR 則採逐層包絡（Envelope）取最嚴重工況，符合工程包絡設計慣例。 |
| **F7 (Major): Moment Frame vs. Dual System ($\div \rho$ Rule)** | **Partially fixed** | **已改進處**：已對 `moment_frame_rho` 加入驗證（僅接受 `1.0` 或 `1.3`，其餘回傳 HTTP 422），但仍需由工程師自行確認該系統非雙重系統（Dual System，§12.12.1.1 不適用雙重系統）。 |
| **F8 (Minor): ETABS Schema (`Step Type`, `Item` Direction, Tabs, Multi-Sheet Excel)** | **Fixed** *(design verified; live API unverified)* | **已改進處**：支援多工作表 Excel、ETABS 剪貼簿 Tab 分隔文字（`.txt`）、從 `Item` 解析方向（如 `Diaph D1 X`），以及單向變位檔（缺向標記 `N/A`）。 |
| **F9 (Minor): `max_dc_ratio` Naming Ambiguity** | **Fixed** *(schema verified; live API unverified)* | **已改進處**：`summary.max_dc_ratio` 已純粹保留給層間變位角 D/C 比值，不再與 TIR 或勁度比值混雜。 |
| **UI-1 to UI-5: Frontend Onboarding, Paste Box, Privacy Notice, Filter, Report** | **Partially fixed** | **已改進處**：首頁預設載入 15 層大樓範例、新增貼上文字框、上傳區標示不保存資料、新增 `Issues only` 過濾器，且 `.docx` 報告已加入規範行動清單與 `N/A` 原因表。 |

---

## 二、 第二輪（V2）新發現問題（New Findings Table）

| Severity | Area | What Was Audited | Expected (Per ASCE 7-22 & SE Practice) | Actual (In V2 Spec) | Code Section |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **CRITICAL** | **Code Action Items: Outdated Section Citations & Wrong SDC Triggers** | 審查新版 `action_items` 觸發條件（`§12.3.3.4 +25%`、`Table 12.6-1`、`§12.5 正交組合僅限 SDC E/F`）。 | 1. **+25% 橫隔板/傳力構件放大**：在 ASCE 7-22 中已由 §12.3.3.4 重新編號為 **§12.3.3.5**（適用於 **SDC D、E、F** 存在 Type 1 扭轉不規則時）。原 §12.3.3.4 在 7-22 中是規範不連續牆/構架支承構件的 $\Omega_0$ 設計力。<br>2. **Table 12.6-1 已在 ASCE 7-22 刪除**：在 7-22 計算書中引用已刪除的 `Table 12.6-1` 會被加州審圖官直接退件（應改引 **§12.6** 高度/週期分析方法限制）。<br>3. **正交載重組合（100% + 30%）**：依 **Table 12.3-1a 與 §12.5.4**，Type 1 扭轉不規則（$\text{TIR} > 1.2$）在 **SDC C、D、E、F** 皆須觸發正交組合要求，**漏掉 SDC C 與 D 屬於不保守錯誤**。 | 仍引用舊版 `§12.3.3.4`（應為 `§12.3.3.5`）、引用已刪除的 `Table 12.6-1`，且將 `§12.5` 正交組合限縮在 SDC E/F（遺漏 SDC C 與 D）。 | **ASCE 7-22 Table 12.3-1a, §12.3.3.5, §12.3.4.2, §12.5.4, §12.6** |
| **MAJOR** | **Code Action Items: Missing $\text{TIR} > 1.6$ Tier** | 審查 ASCE 7-22 Table 12.3-1a 扭轉不規則分級門檻。 | ASCE 7-22 **Table 12.3-1a** 將 Type 1 扭轉後果分為三個數值門檻：**$\text{TIR} > 1.2$**、**$\text{TIR} > 1.4$** 與 **$\text{TIR} > 1.6$**（$\text{TIR} > 1.6$ 針對特定結構系統有額外動力/非線性分析限制；*具體條文細節標記為 unverified*）。 | 目前僅檢查 $\text{TIR} > 1.2$ 與 $\text{TIR} > 1.4$，未提示 $\text{TIR} > 1.6$ 門檻。 | **ASCE 7-22 Table 12.3-1a** |
| **MAJOR** | **Code Logic: $A_x$ Should Be Computed Directly** | 審查 §12.8.4.3 $A_x$ 處理方式。 | 因輸入已有各層 $\delta_{\max}$ 與 $\delta_{\text{avg}}$，可直接依 Eq. 12.8-14 算出 $A_x = \min(\max((\text{TIR}/1.2)^2, 1.0), 3.0)$，並在 `drift_is_amplified = false` 且 $A_x > 1.0$ 時發出醒目警告（說明目前變位尚未乘上 $A_x$）。 | 僅列為未計算的行動清單文字，未直接算出 $A_x$ 數值。 | **ASCE 7-22 §12.8.4.3 (Eq. 12.8-14)** |
| **MAJOR** | **Parser Edge Case: Blindly Dropping `Step Type = Min`** | 審查解析器「直接丟棄 `Step Type = Min` 資料列」規則。 | 在 ETABS 靜力多步偏心工況（`EQX` stepped eccentricity）或歷時分析中，`Min` 步驟代表負向極值；在非對稱建築中 `abs(Min)` 可能大於 `Max`。直接丟棄 `Min` 會漏抓負向最大變位。 | 無條件丟棄 `Step Type = Min` 列；應改為取 `max(abs(Max), abs(Min))`。 | **ETABS Post-Processing Practice** |
| **MINOR** | **Boundary Equality & LA Plan Check `.docx` Polish** | 審查邊界值（`TIR = 1.2`, `r1 = 0.70`, `drift = limit`）與 `.docx` 報告完整性。 | 1. 需確保浮點數精度容差（如 `1e-9`），避免 `0.6 / 0.5 = 1.2000000000000002` 誤判為 $> 1.2$（實機結果 `unverified`）。<br>2. 洛杉磯（LADBS）送審計算書仍建議補上 **California SE/PE 印章簽名框** 與 **開裂斷面折減假設（ACI 318 §6.6.3.1.1）** 摘要欄（`.docx` 實機版面 `unverified`）。 | 實機邊界測試與 `.docx` 開啟檢視在無終端機環境下為 `unverified`。 | **2022 CBC / LADBS Submittal Standards** |

---

## 三、 針對 Gemini 專屬問題的補充技術解答

1. **ASCE 7-22 扭轉架構與 Table 12.6-1 確認**：新版採用 ASCE 7-22 單一 Type 1 扭轉不規則（$\text{TIR} > 1.2$ 或 $>75\%$ 單側抗側力強度，§12.3.2.1.1）並移除 `Table 12.6-1` 是完全正確的（7-22 已刪除 Table 12.6-1，ELF 分析方法僅受 §12.6 高度/週期限制，如 SDC D/E 超過 160 ft 或 SDC F 超過 100 ft 之特定系統）。
2. **質心變位近似的報告標準措辭**：建議在報告與 `basis` 中寫為：*"Center-of-mass story drift is approximated as the arithmetic mean of the two extreme diaphragm edges ($\delta_{\text{avg}}$) from ETABS 'Story Max Over Avg Drifts'. For non-rectangular, L/T-shaped, or mass-eccentric diaphragms, engineers should verify translational drift directly from ETABS 'Diaphragm Center of Mass Displacements'."*
3. **從層間變位直接計算 $A_x$**：完全可行且應該直接計算。依 ASCE 7-22 Eq. 12.8-14，$A_x = (\text{TIR} / 1.2)^2$（限於 $[1.0, 3.0]$）只需要你已經算出的 $\text{TIR} = \delta_{\max}/\delta_{\text{avg}}$，不需要各層絕對位移。
4. **最具商業價值的下一步 UI 升級**：在現有界面基礎上，加上 **「網頁內建 A4 計算書預覽視窗（Report Preview Modal）」** 與 **「層間變位角垂直分佈折線圖（Story Drift Profile Chart，疊加紅色法規上限虛線）」**——這能讓結構技師在反覆改模型時不用每次下載 `.docx` 就能即時檢查分佈趨勢與列印版面。

---

## 四、 總結與最優先修正建議（Overall Verdict）

1. **總體評價（V2）**：第二版成功對齊了 ASCE 7-22 單一 Type 1 扭轉不規則架構、加入了 `N/A` 狀態與原因說明、統一了建築級勁度與例外條款控制工況，並補上了實用的規範行動簽核表與零摩擦網頁預設範例，整體成熟度大幅提升。
2. **單一最優先修正項目（Single Most Important Next Fix）**：立即修正 `action_items` 中的 **ASCE 7-22 條文編號與 SDC 觸發範圍**——將 +25% 橫隔板/傳力構件放大從舊版 `§12.3.3.4` 改為 **`§12.3.3.5`**、移除已刪除的 **`Table 12.6-1`** 引用、將 **`§12.5.4` 正交載重組合** 從 SDC E/F 擴大至 **SDC C–F**，並直接計算出 **`A_x = (TIR / 1.2)²`** 數值。