# 給 Codex、Muse、Gemini 的重測指令（第二輪）

## 使用方式

1. 先打開 https://story-check-api.onrender.com/api/health ，看到 `{"status":"ok"}` 再開始，避免後端休眠被誤判成網站壞掉。
2. 每個 AI 都貼「共同指令」，再接著貼它自己的那一段。
3. 附件：
   - 三個都附 `PROJECT_REVIEW.md`（第 12 節是修正紀錄）。
   - 各自附上它上一輪的報告：Codex → `STORY_CHECK_REVIEW_2026-11-17.md`；Muse → `Story_Check_審查報告_2026-11-17.md`；Gemini → `gemini_story_check_full_review_ui_ux_guide.md`。
4. GitHub repo 是私有的。Codex 在這台 Mac 上跑，可以直接讀 `backend/` 的程式碼；Muse 和 Gemini 只能用網站、API 和文件。

---

## 共同指令（三個都貼）

You reviewed Story Check on 2026-11-17. The developer has since changed the engine, parser, report and site based on your review and two others. Please re-test the **live** system and tell me what is still wrong. Be specific and skeptical; do not repeat praise.

Your previous report and `PROJECT_REVIEW.md` are attached. Section 12 of `PROJECT_REVIEW.md` lists every finding and how it was handled. Section 5 describes the new check logic.

**Live system**

- Website: https://story-check-virid.vercel.app (opens with the 15-story sample already shown)
- API: https://story-check-api.onrender.com
- Sample tables: append `story_definitions.csv`, `story_max_over_avg_drifts.csv`, `story_stiffness.csv` or `project.json` to
  - https://story-check-virid.vercel.app/samples/05_story_office/
  - https://story-check-virid.vercel.app/samples/15_story_tower/
  - https://story-check-virid.vercel.app/samples/30_story_highrise/
- Precomputed engine output for each sample: same folders, `result.json`

```bash
B=https://story-check-virid.vercel.app/samples/15_story_tower
for f in story_definitions story_max_over_avg_drifts story_stiffness; do curl -sO $B/$f.csv; done
curl -s $B/project.json -o project.json
curl -X POST https://story-check-api.onrender.com/api/analyze \
  -F files=@story_definitions.csv -F files=@story_max_over_avg_drifts.csv -F files=@story_stiffness.csv \
  -F "project_info=<project.json" -o result.json
curl -X POST https://story-check-api.onrender.com/api/export-report \
  -H 'Content-Type: application/json' -d @result.json -o report.docx
```

**What changed (summary)**

- Torsion follows ASCE 7-22 Table 12.3-1 Type 1 using TIR (§12.3.2.1.1). There is no Type 1b torsion and a large TIR is never FAIL. Optional input `torsion_strength_irregular` (true / false / null) covers the 75% lateral-strength criterion.
- New status `N/A` with a reason (flexible diaphragm, zero drift, stiffness ≤ 0, direction without data).
- Every check has `output_case` and `actions` (follow-up requirements). `summary.action_items` lists them with the triggering stories. `summary.max_dc_ratio` is drift D/C only. `basis` returns the parameters actually used, defaults included.
- Output cases: drift = largest drift per story; TIR = largest TIR per story; soft-story stiffness = one case per direction for the whole building (largest shear); §12.3.2.2 Exception 1 = one case per direction (largest total average drift).
- Rejected with HTTP 422: `moment_frame_rho` other than 1.0 / 1.3; the four-story drift limit on a building taller than 4 stories; average drift 0 with non-zero max drift.
- Parser: title rows of any width, tab-separated text (pasted from ETABS, sent as `.txt`), every sheet of an Excel workbook, `Step Type` Min rows dropped, direction read from `Item` (e.g. `Diaph D1 X`). One-direction drift files are accepted. `project_info.input_warnings` flags negative drifts, implausible story heights and drift ratios.
- Report: resolved I_e and diaphragm, the user's local date (sent by the website as `project_info.report_date`), output case per check, a Code-Triggered Action Items sign-off table, and a table of N/A checks with reasons.

**Please do the following**

1. **Re-run every test from your previous report** that found a problem, against the live API. For each, state: Fixed / Partially fixed / Not fixed, with the request you sent and the response you got.
2. **Check the new torsion logic and action items** against ASCE 7-22. For each action item (A_x §12.8.4.3, §12.8.4.2 for SDC B, §12.3.3.4 +25%, Table 12.6-1, ρ = 1.3 per §12.3.4.2 when TIR > 1.4, §12.5 orthogonal combination in SDC E/F): is the trigger condition right for each SDC? Cite your source and say clearly when you cannot confirm it from the published text.
3. **Try to break the new features**: one-direction input, pasted tab-separated tables, multi-sheet Excel, Step Type rows, `Item` direction, the N/A paths, the `torsion_strength_irregular` input, values exactly at thresholds (TIR = 1.2, r1 = 0.70, drift = limit).
4. **Hand-check** at least the 15-story Story1 and Story4 again, plus one story of the 30-story building, against `result.json`.
5. **Report**: open the exported .docx. Is it now acceptable as a calculation attachment for a Los Angeles plan check? What is still missing?

**Output format**

1. A table: original finding ID | your verdict (Fixed / Partially / Not fixed) | evidence.
2. A table of **new** findings: severity (critical / major / minor) | area | what you did | expected | actual | code section.
3. Three sentences: overall verdict and the single most important next fix.

Do not claim to be a licensed engineer. Mark anything you could not verify against the published ASCE 7-22 text as "unverified".

---

## Codex 追加段落

Your previous report (`STORY_CHECK_REVIEW_2026-11-17.md`) ran 14 edge-case tests. Re-run all 14 exactly as before and compare. In particular:

- Story4 X with an extra case of Max Drift 0.5 / Avg Drift 0.25: the TIR should now be 2.0.
- 15 stories with `four_story_or_less_drift_tolerant` and `moment_frame_rho = 0.5`: both should be rejected.
- The one-field title line before the CSV header: should now parse.
- Zero stiffness at Story1: should be N/A with a reason, not "missing data".
- SDC E: the torsion FAIL should be gone; the soft-story FAIL at Story1 should remain.

You can also read `backend/code_checker.py` and `backend/parser.py` locally. Review the case-selection logic in `_parse_drifts` and `_parse_stiffness`: is "envelope per story for drift and TIR, one case per building for stiffness and Exception 1" physically consistent? Is there a cleaner design?

---

## Muse 追加段落

Your previous report (`Story_Check_審查報告_2026-11-17.md`) listed Findings 1–14 and ran 18 edge cases. Use your finding numbers in the verdict table. In particular:

- F1: confirm the torsion framework is now 7-22 Type 1 / TIR, and check whether the strength criterion handling (engineer input, "not evaluated" note when blank) is acceptable for a plan checker.
- F3: are the listed consequences now complete for SDC D, and correct for SDC C, E and F?
- F4, F5, F8, F9, F14: re-run your exact inputs (Story3 Avg Drift 0, Story8 Stiff X 0, negative drifts at Story5, flexible diaphragm, `length_unit: "ft"`).
- F6, F10, F11, F12, F13: check the exported report for I_e, diaphragm, local date, PASS-row references, the drift-only Maximum D/C, and per-check output cases (use your EQX2 test).
- You mentioned a possible 7-22 "torsional strength irregularity" (§12.3.3.6) from a single source. If you can now confirm or rule it out, say which.

---

## Gemini 追加段落

Your previous report (`gemini_story_check_full_review_ui_ux_guide.md`) described torsion with the ASCE 7-16 Types 1a / 1b, for example "Type 1b torsional irregularity in SDC D prohibits ELF per Table 12.6-1". Other sources (Trimble / Tekla's ASCE 7-22 update notes) state that 7-22 has a single torsional type based on TIR, and the tool now follows that. Please check this against ASCE 7-22 sources and tell me which framing is correct, with the citation. If 7-22 Table 12.6-1 still restricts ELF for some torsion condition, state the exact condition in 7-22 terms (TIR value, SDC, height or period limits).

Also re-check your items:

- Center-of-mass drift approximated by the average of the two ends (still the case; disclosed in the report). How should the tool phrase or bound this until a center-of-mass displacement table is available?
- A_x: the tool lists it as an action item but does not compute it. Your example "5% × 1.45 = 7.25%" did not match A_x = (δmax / 1.2 δavg)² for TIR 1.5 (≈ 1.56); please recheck, and say whether A_x can be estimated from story drifts alone or needs story displacements.
- §12.3.2.2 Exception 1 "torsional effects need not be considered": the tool uses the average drifts of one output case. Is that acceptable, or must the user supply a separate case without accidental torsion?
- Stiffness ≤ 0, Step Type, `Item` direction, one-direction input, `max_dc_ratio` naming: verify the fixes.
- UI: the site now opens with the 15-story sample, has a paste box for ETABS tables, a "not saved" note on the upload area, and an "Issues only" filter. Which of your remaining UI suggestions would matter most to a working SE, and why?
