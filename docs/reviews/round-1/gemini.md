# Story Check：California SE & QA 深度審查報告、使用者體驗與網頁設計建議（by Gemini）

**審查日期：** 2026-11-17  
**審查角色：** Senior US Structural Engineer (Licensed SE, California) & QA Tester (Gemini)  
**目標系統：** Story Check (`https://story-check-virid.vercel.app` / `https://story-check-api.onrender.com`)  
**規範依據：** ASCE 7-22 Chapter 12 (Seismic Design Requirements for Building Structures)  

---

## 一、 QA 審查總表（Findings Table）

| Severity | Area | What Was Reviewed | Expected (Per ASCE 7-22 & SE Practice) | Actual (In `PROJECT_REVIEW.md`) | Code Section |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **CRITICAL** | **Code Interpretation (Story Drift & Torsion)** | 5.4 節：無扭轉不規則時，採用 `avg_drift` 作為質心（Center of Mass）變位近似值進行層間變位角檢核。 | 在 SDC C–F 且**無**扭轉不規則時，ASCE 7-22 §12.8.6 規定變位計算點為「質心（Center of Mass）」，但當**有**扭轉不規則（Type 1a 或 1b）且 SDC C–F 時，必須取建築物邊緣（Edges）的最大變位。此外，即便無扭轉不規則，幾何兩端平均（`avg_drift`）在 L 型、T 型或質量偏心建築中**不等於**質心變位，可能低估實際質心位移達 15%~30%。 | 直接將 `avg_drift`（兩端平均）當作質心變位。若建築非矩形對稱，算出的變位角會系統性偏低（不保守），在審圖時會直接被打槍。 | **ASCE 7-22 §12.8.6** |
| **CRITICAL** | **Code Interpretation (Torsional Amplification $A_x$)** | 5.2 節：扭轉不規則檢核與變位計算。 | 當 SDC C–F 存在 Type 1a 或 1b 扭轉不規則時，依 §12.8.4.3 必須計算放大係數 $A_x = (\delta_{\max} / 1.2\delta_{\text{avg}})^2 \le 3.0$，並用它放大偶發扭矩重新分析。不能同時把 `max_drift` 直接當成已放大變位，卻又假設輸入工況 $A_x=1.0$——如果輸入是 $A_x=1.0$ 且存在扭轉不規則，當前算出的 `max_drift` 還沒經過 $A_x$ 放大，直接拿去檢核 §12.12-1 變位角是低估（不安全）的。 | 僅在文字提示需放大 $A_x$，卻直接拿未經 $A_x$ 放大的 `max_drift` 去做 §12.12.1 層間變位角檢核，且狀態標示為 `PASS`（若未超限）。這在加州屬於嚴重設計疏失（Unconservative）。 | **ASCE 7-22 §12.8.4.3 & §12.8.6** |
| **CRITICAL** | **Code Interpretation (Soft Story Exception 1)** | 5.3 節：§12.3.2.2 例外條款 1（「最頂兩層的關係不需評估」之實作）。 | ASCE 7-22 §12.3.2.2 Exception 1 規定變位角計算**必須不含偶發扭矩（Without accidental torsion）**，且頂層（Story $N$）與次頂層（Story $N-1$）本身的變位角關係不需評估。 | 跳過「次頂層對頂層」的邏輯正確，但直接拿含偶發偏心的同一份工況 `avg_drift` 去算 §12.3.2.2 例外條款，違反條文前提。 | **ASCE 7-22 §12.3.2.2 Exception 1** |
| **MAJOR** | **Engineering Practice (Soft Story Stiffness)** | 5.3 節與 6.1 節：使用 ETABS `Story Stiffness` 表檢核 Table 12.3-2 Type 1a/1b。 | 高層建築中因高振態效應與反曲點移動，某層剪力 $V_i$ 可能趨近於零或變號，導致 ETABS `Story Stiffness` 出現無意義的暴增或負值。實務上常要求用「固定單位側力法」或「1.3 倍變位角法（§12.3.2.2）」替代。 | 無條件信任 ETABS 匯出的 `Story Stiffness` 數值，未對高層反曲點造成的負勁度或異常尖峰做防呆處理。 | **ASCE 7-22 Table 12.3-2** |
| **MAJOR** | **Code Interpretation (Prohibited Irregularities in SDC D)** | 5.1 節與 8 節：`15_story_tower`（SDC D）設定 Story 4 扭轉比 1.50（Type 1b）與 Story 1 勁度減半（Type 1b）。 | 在 SDC D 若有 Type 1b 扭轉不規則，依 Table 12.6-1 **禁止使用等值側力法（ELF）**（必須改用模態反應譜分析 MRSA），且必須依 §12.3.3.4 將接頭與傳力構件設計力放大 **25%**（$1.25$ 倍）。 | 5.2 節只提示需放大偶發扭矩 $A_x$，完全漏掉 Table 12.6-1（禁止繼續使用 ELF 分析法）以及 §12.3.3.4（設計力放大 1.25 倍）。 | **ASCE 7-22 §12.3.3.1, §12.3.3.4, Table 12.6-1** |
| **MAJOR** | **Parser & Data Integrity (Multi-Load Case Mixing)** | 6.1 節：不同樓層各自取 `Max Drift` 最大的工況。 | 同一個建築結構方向的物理狀態必須來自**同一個一致的地震工況（Load Case）**。 | Story 1 取 `EQX+Ecc`，Story 2 取 `EQX-Ecc`，把兩個不同方向的偏心工況硬拼在同一棟大樓上，物理上完全錯誤。 | **Engineering Mechanics / Data Integrity** |
| **MAJOR** | **Code Interpretation (Drift Limit & $\rho$ Rule)** | 5.4 節：`moment_frame_rho` 在 SDC D–F 時將容許變位角除以 $\rho$（§12.12.1.1）。 | 雙重系統（Dual System）不適用 $\Delta_a / \rho$ 懲罰條款。 | `structure_type` 只有 `"other"`，沒有區分 Moment Frame 與 Dual System。 | **ASCE 7-22 §12.12.1.1** |
| **MINOR** | **ETABS Table Schema Assumption** | 6.1 節：對 ETABS 匯出欄位名稱的假設。 | 實際 ETABS 匯出的 `Story Max Over Avg Drifts` 含有 `Step Type`（`Max` 與 `Min` 兩列）、單位列及 `Diaphragm` 名稱（如 `Diaph D1 X`）。 | 未處理 `Step Type`（`Max` vs `Min`）與 `Diaphragm` 名稱，真實檔案極易解析失敗。 | **ETABS v20–v22 Schema** |
| **MINOR** | **Metric Clarity (`max_dc_ratio`)** | 6.3 節：`summary.max_dc_ratio` 混合了三種不同性質的比值。 | 工程術語中 `D/C Ratio > 1.0` 代表超限（Fail）。將不規則性觸發門檻（比值 / 1.2）稱為 `dc_ratio` 會造成混淆。 | 建議將不規則性指標改名為 `irregularity_ratio` 或 `threshold_ratio`，把 `dc_ratio` 嚴格保留給「層間變位角 / 容許變位角」。 | **Engineering Terminology** |

---

## 二、 針對 13 個核心審查問題的關鍵結論

1. **ASCE 7-22 條文與 7-16 差異**：限值與條文編號基本正確，但 7-22 引入多週期反應譜，且 SDC D 存在 Type 1b 扭轉不規則時強制禁止 ELF（Table 12.6-1）並要求連接件放大 1.25 倍（§12.3.3.4）。
2. **§12.3.2.2 例外 1**：跳過「次頂層對頂層」正確，但變位角計算必須不含偶發扭矩；且若單一方向不符合例外，整棟建築仍須承擔垂直不規則懲罰。
3. **邊界變位檢核（§12.8.6）**：扭轉不規則且 SDC C–F 時改用邊緣變位（`max_drift`）完全正確，但須提醒 $A_x$ 放大。
4. **審圖單位對 ETABS `Story Stiffness` 的接受度**：中低層勉強接受，高層常因反曲點出現負勁度或暴增而被打槍，建議優先提供 §12.3.2.2 變位角法。
5. **燈號設計**：建議將 `WARNING` 改名為 `IRREGULAR (Triggered)`，更符合工程術語。
6. **擴充建議**：ETABS 的 `Story Forces` 與 `Story Drifts` 已包含 P-Delta 所需數據，建議順手加入 **§12.8.7 P-Delta 穩定係數 $\theta$ 檢核**。
7. **邊界條件防呆**：攔截 `K <= 0`（零或負勁度）、變位一律取 `abs()`、支援單向變位（另一向標記 `N/A`）、SDC B 永遠取質心變位。
8. **工況選擇修正**：先依工況（`Output Case` + `Step Type`）分組跑完整棟大樓，再挑出最嚴重的作為「控制工況（Governing Load Case）」。
9. **Schema 擴充性**：建議預留樓層總剪力 $V_x, V_y$ 與累計軸力 $P_x$，供未來計算 $A_x$ 與 P-Delta 使用。
10. **洛杉磯（LADBS）審圖計算書必備要素**：設計基準摘要頁（Design Criteria Summary）、California SE/PE 印章預留框、控制工況邊界條件說明（含開裂斷面折減假設）、以及規範連動行動清單（Action Items）。
11. **商業模式與定價**：痛點真實存在（取代事務所祖傳 Excel），主要付費者為中小型結構事務所老闆（團隊訂閱 $99～$199/月）。
12. **信任與背書**：不需要軟體公司擁有 SE 執照，關鍵在於計算過程 100% 透明（White-box）並附上對照 FEMA 範例的驗證白皮書（Verification Manual）。

---

## 三、 使用者視角：3 個關鍵操作摩擦與解法（留存率決定因素）

1. **摩擦一：從 ETABS 匯出 3 張表的步驟太繁瑣（最大殺手）**
   * **問題**：若工程師只想快速檢查單次改版，花 3 分鐘在 ETABS 勾選 3 張表、選工況再分別匯出 CSV 太慢。
   * **解法**：支援**單一 `.xlsx` 檔案（包含多個分頁 Tabs）自動辨識**，以及支援直接從 ETABS 表格 `Ctrl+C` 複製貼上文字，將操作摩擦降低 70%。
2. **摩擦二：機密專案的資安與隱私顧慮（NDA / Confidentiality）**
   * **問題**：美國中大型事務所接手的商業、醫院或政府專案均有嚴格保密協議，工程師會猶豫是否能將結構模型數據上傳至第三方伺服器。
   * **解法**：善用目前「無資料庫、不保存資料」的架構優勢，在上傳區掛上顯眼的綠色盾牌標章：**「100% Stateless & Zero Data Retention — Your structural data is processed in memory and immediately discarded.」** 未來甚至可透過 Pyodide 將 Python 計算引擎搬到瀏覽器本地執行，實現資料完全不離開用戶電腦。
3. **摩擦三：做完檢核後的「下一步修改引導」斷層**
   * **問題**：當系統算出 `Story 4 扭轉超標（Type 1b）` 時，工程師還得自己動手算完 $A_x$ 再回去調 ETABS 偏心率。
   * **解法**：在結果中直接給出具體修改參數建議（例如：「建議將 Story 4 的偶然偏心率從 5% 調高至 $5\% \times 1.45 = 7.25\%$ 後重新分析」），讓工具從「報錯器」升級為「解決問題的副駕駛」。

---

## 四、 網頁設計（UI/UX）升級建議

1. **CAD 深色工作站視覺（Dark Mode）**：
   * 3D 畫布採用深炭灰 `#0B0F19`（搭淡工程網格線），側邊欄採用 `#161B26` 與 `1px solid #262E3F` 細邊框。
   * 所有工程數值（標高、D/C Ratio、變位角）全面套用等寬數字（`tabular-nums` / `JetBrains Mono`），確保小數點垂直對齊。
2. **零摩擦首次體驗（Zero-Friction Onboarding）**：
   * 網頁載入時**預設直接載入 `15_story_tower` 範例結果**，讓訪客第 1 秒就看到 3D 紅燈大樓與右側公式推導；上方提供三個範例情境快速切換按鈕。
3. **3D 畫布診斷工具列（HUD）**：
   * 畫布頂部加入懸浮膠囊切換器：`[ X-Direction ] | [ Y-Direction ]`、`[ Deformed Shape ]` 與變形放大倍率滑桿。
   * 側面疊加垂直「層間變位角折線圖（Drift Profile Curve）」與法規上限紅虛線。
4. **右欄資訊架構優化**：
   * KPI 卡片明確區分 `Drift Violations`（紅字）與 `Triggered Irregularities`（黃字）。
   * 樓層列表新增 `[ Show All | Issues Only ]` 過濾開關。
   * 頂部新增「規範連動行動清單（Code Trigger Action Items）」Checklist，自動列出觸發的後續規範要求（如 §12.8.4.3 $A_x$ 放大、§12.3.3.4 連接件放大 1.25 倍）。
5. **計算書即時預覽（Report Preview Modal）**：
   * 在下載 `.docx` 旁提供 A4 紙張模擬預覽視窗，確認 SE 印章框與公式排版後再一鍵匯出。