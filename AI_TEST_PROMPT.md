# 給 GPT / Gemini 的測試指令

使用方式：把下方「---」以下的整段貼給 AI，並把 `PROJECT_REVIEW.md` 當附件一起上傳。
開始前先自己打開一次網站或 https://story-check-api.onrender.com/api/health ，喚醒休眠的後端。

---

You are a senior US structural engineer (licensed SE, California) and a QA tester. Please test this web tool and tell me where it is wrong, not where it is good. The attached PROJECT_REVIEW.md explains the design and the check logic.

**What it is:** a post-processor for ETABS results. It checks ASCE 7-22 Chapter 12 torsional irregularity (Table 12.3-1 Type 1a/1b), soft story (Table 12.3-2 Type 1a/1b, with §12.3.2.2 exceptions) and story drift (§12.8.6, Table 12.12-1), shows a 3D model, and exports a Word calculation report.

**Website:** https://story-check-virid.vercel.app
(The backend may take up to a minute to wake up on the first request.)

**Sample input files** (three mock buildings). Folders do not list their contents; append one of these file names to a base URL: `story_definitions.csv`, `story_max_over_avg_drifts.csv`, `story_stiffness.csv`, `project.json`.

- https://story-check-virid.vercel.app/samples/05_story_office/
- https://story-check-virid.vercel.app/samples/15_story_tower/
- https://story-check-virid.vercel.app/samples/30_story_highrise/

Full example: https://story-check-virid.vercel.app/samples/15_story_tower/story_stiffness.csv

**API** (if you can run code instead of using the browser):

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

**Please do the following:**

1. **Hand-check the numbers.** Using the sample CSVs, independently compute torsion ratios, soft-story stiffness comparisons and amplified drift ratios for at least 3 stories of the 15-story building (include Story1 and Story4). Compare with the tool's output. List every mismatch.
2. **Check the code interpretation.** Are the thresholds, exceptions, drift limits, the ÷ρ rule, and the use of max vs. average drift correct per ASCE 7-22? Cite the section for each issue. Say clearly when you are unsure rather than guessing.
3. **Try to break it.** Wrong units, missing file, a file with an extra header row, a story with zero stiffness, negative drifts, non-English story names, only one direction of drift, flexible diaphragm, SDC B. Report what happens and whether the error message is useful.
4. **Review the Word report** (if you can open it): would a plan checker in Los Angeles accept it as a calculation package? What is missing?
5. **Product view:** would a working SE pay for this? What existing tools (ETABS built-in, spreadsheets, other plugins) already do the same?

**Output format:** a table of findings with columns: severity (critical / major / minor), area, what you did, expected, actual, code section. Then a short overall verdict.
