"""Unit tests for backend/code_checker.py. Run from the repo root: python -m pytest"""

import pytest

from backend.code_checker import DRIFT_LIMITS, check_building


def story(n, max_x=0.30, avg_x=0.30, max_y=0.30, avg_y=0.30, kx=1000.0, ky=1000.0, h=144.0):
    return {
        "story_name": f"Story {n}",
        "elevation_in": n * h,
        "height_in": h,
        "max_drift_x_in": max_x,
        "avg_drift_x_in": avg_x,
        "max_drift_y_in": max_y,
        "avg_drift_y_in": avg_y,
        "stiffness_x_kip_in": kx,
        "stiffness_y_kip_in": ky,
    }


def building(stories, **info):
    # The 12.3.2.2 exceptions are off by default here so the stiffness criteria are tested alone.
    project = {"building_name": "Test Tower", "risk_category": "II", "cd": 5.5, "apply_soft_story_exception": False}
    project.update(info)
    return {"project_info": project, "stories": stories}


def get(result, story_name, check_type):
    sr = next(r for r in result["story_results"] if r["story_name"] == story_name)
    return next(c for c in sr["checks"] if c["check_type"] == check_type)


TORSION_X = "Torsional Irregularity (X-Dir)"
SOFT_X = "Soft Story Irregularity (X-Dir)"
DRIFT_X = "Allowable Story Drift (X-Dir)"


# ---------- Torsional irregularity, Table 12.3-1 Type 1 (TIR, Section 12.3.2.1.1) ----------


@pytest.mark.parametrize(
    "max_x, avg_x, status",
    [
        (1.00, 1.00, "PASS"),
        (1.20, 1.00, "PASS"),  # exactly 1.2 is not "more than 1.2"
        (1.21, 1.00, "WARNING"),
        (1.41, 1.00, "WARNING"),  # ASCE 7-22 has no separate extreme torsional type
    ],
)
def test_torsion_thresholds(max_x, avg_x, status):
    res = check_building(building([story(1, max_x=max_x, avg_x=avg_x)], drift_is_amplified=True))
    c = get(res, "Story 1", TORSION_X)
    assert c["status"] == status
    assert "Type 1;" in c["code_reference"] and "12.3.2.1.1" in c["code_reference"]
    assert "1b" not in c["code_reference"]
    assert c["demand_value"] == pytest.approx(max_x / avg_x, abs=1e-4)
    assert c["dc_ratio"] == pytest.approx(max_x / avg_x / 1.2, abs=1e-3)


@pytest.mark.parametrize("sdc", ["B", "D", "E", "F"])
def test_large_tir_is_never_prohibited(sdc):
    res = check_building(
        building([story(1, max_x=1.5, avg_x=1.0)], drift_is_amplified=True, seismic_design_category=sdc)
    )
    assert get(res, "Story 1", TORSION_X)["status"] == "WARNING"


def test_torsion_actions_depend_on_sdc_and_tir():
    def actions(sdc, ratio):
        b = building([story(1, max_x=ratio, avg_x=1.0)], drift_is_amplified=True, seismic_design_category=sdc)
        return " | ".join(get(check_building(b), "Story 1", TORSION_X)["actions"])

    assert "12.8.4.3" in actions("C", 1.3)
    assert "12.8.4.3" not in actions("B", 1.3)
    assert "12.8.4.2" in actions("B", 1.5)
    assert "12.3.3.4" in actions("D", 1.3) and "rho = 1.3" not in actions("D", 1.3)
    assert "rho = 1.3" in actions("D", 1.5)
    assert "12.5" in actions("E", 1.3)


def test_strength_criterion_input():
    regular = story(1, max_x=1.1, avg_x=1.0)
    c = get(check_building(building([dict(regular)], drift_is_amplified=True)), "Story 1", TORSION_X)
    assert c["status"] == "PASS" and "not evaluated" in c["formula_breakdown"]
    c = get(check_building(building([dict(regular)], drift_is_amplified=True, torsion_strength_irregular=False)),
            "Story 1", TORSION_X)
    assert c["status"] == "PASS" and "not evaluated" not in c["formula_breakdown"]
    res = check_building(building([dict(regular)], drift_is_amplified=True, torsion_strength_irregular=True))
    assert get(res, "Story 1", TORSION_X)["status"] == "WARNING"
    # Strength-triggered irregularity also moves the drift check to the edge
    assert get(res, "Story 1", DRIFT_X)["demand_value"] == pytest.approx(1.1 / 144, abs=1e-5)


def test_tir_from_parser_overrides_governing_drift_row():
    s1 = story(1, max_x=0.30, avg_x=0.29)
    s1.update(tir_x=2.0, tir_x_case="EQX-Ecc")
    c = get(check_building(building([s1], drift_is_amplified=True)), "Story 1", TORSION_X)
    assert c["demand_value"] == 2.0 and c["status"] == "WARNING"
    assert c["output_case"] == "EQX-Ecc"


def test_flexible_diaphragm_marks_torsion_not_applicable():
    res = check_building(building([story(1, max_x=1.5, avg_x=1.0)], drift_is_amplified=True, diaphragm="flexible"))
    c = get(res, "Story 1", TORSION_X)
    assert c["status"] == "N/A"
    assert "rigid or semirigid" in c["formula_breakdown"]
    assert res["summary"]["total_not_applicable"] == 2


def test_zero_drift_story_is_not_applicable_not_pass():
    res = check_building(building([story(1, max_x=0.0, avg_x=0.0)], drift_is_amplified=True))
    assert get(res, "Story 1", TORSION_X)["status"] == "N/A"


def test_zero_average_with_nonzero_max_is_rejected():
    with pytest.raises(ValueError, match="avg_drift_x_in is zero"):
        check_building(building([story(1, max_x=0.3, avg_x=0.0)], drift_is_amplified=True))


# ---------- Soft story, Table 12.3-2 ----------


@pytest.mark.parametrize(
    "k1, status, ref",
    [
        (700.0, "PASS", "Table 12.3-2"),  # exactly 70% is not "less than 70%"
        (690.0, "WARNING", "Type 1a"),
        (600.0, "WARNING", "Type 1a"),  # exactly 60% is still Type 1a
        (590.0, "WARNING", "Type 1b"),
    ],
)
def test_soft_story_vs_story_above(k1, status, ref):
    res = check_building(building([story(1, kx=k1), story(2, kx=1000.0)], drift_is_amplified=True))
    c = get(res, "Story 1", SOFT_X)
    assert c["status"] == status
    assert c["code_reference"].endswith(ref)
    assert c["capacity_limit"] == pytest.approx(700.0)
    assert c["dc_ratio"] == pytest.approx(700.0 / k1, abs=1e-3)


def test_soft_story_three_story_average_criterion():
    # K1 = 780 vs above 1000 -> 0.78 (passes the 70% test)
    # average of three above = (1000 + 1000 + 1000) / 3 -> 0.78 < 0.80 -> Type 1a
    stories = [story(1, kx=780.0)] + [story(n, kx=1000.0) for n in (2, 3, 4)]
    c = get(check_building(building(stories, drift_is_amplified=True)), "Story 1", SOFT_X)
    assert c["status"] == "WARNING"
    assert c["code_reference"].endswith("Type 1a")
    assert c["capacity_limit"] == pytest.approx(800.0)


def test_extreme_soft_story_three_story_average_criterion():
    # K1 = 690 vs above 1000 -> 0.69 (Type 1a by the adjacent test, not below 0.60)
    # vs three-story average 1000 -> 0.69 < 0.70 -> Type 1b
    stories = [story(1, kx=690.0)] + [story(n, kx=1000.0) for n in (2, 3, 4)]
    c = get(check_building(building(stories, drift_is_amplified=True)), "Story 1", SOFT_X)
    assert c["code_reference"].endswith("Type 1b")


def test_three_story_average_needs_three_stories_above():
    # Only two stories above: the average criterion must not be applied.
    stories = [story(1, kx=780.0), story(2, kx=1000.0), story(3, kx=1000.0)]
    c = get(check_building(building(stories, drift_is_amplified=True)), "Story 1", SOFT_X)
    assert c["status"] == "PASS"
    assert "K_avg" not in c["formula_breakdown"]


def test_extreme_soft_story_fails_in_sdc_e():
    b = building([story(1, kx=500.0), story(2)], drift_is_amplified=True, seismic_design_category="E")
    assert get(check_building(b), "Story 1", SOFT_X)["status"] == "FAIL"


def test_top_story_has_no_soft_story_check_and_input_order_is_irrelevant():
    stories = [story(2), story(1, kx=500.0)]  # top-down order, as ETABS exports
    res = check_building(building(stories, drift_is_amplified=True))
    assert [r["story_name"] for r in res["story_results"]] == ["Story 1", "Story 2"]
    assert SOFT_X not in [c["check_type"] for c in res["story_results"][1]["checks"]]
    assert get(res, "Story 1", SOFT_X)["code_reference"].endswith("Type 1b")


# ---------- Allowable story drift, Table 12.12-1 ----------


def test_drift_is_amplified_by_cd_over_ie():
    # 5.5 * 0.40 / 1.0 = 2.20 in; 2.20 / 144 = 0.01528 <= 0.020
    res = check_building(building([story(1, max_x=0.40, avg_x=0.40)], cd=5.5))
    c = get(res, "Story 1", DRIFT_X)
    assert c["demand_value"] == pytest.approx(5.5 * 0.40 / 144.0, abs=1e-5)
    assert c["capacity_limit"] == 0.020
    assert c["status"] == "PASS"
    assert "C_d" in c["formula_breakdown"]


def test_drift_fails_when_amplified_drift_exceeds_limit():
    # 5.5 * 0.60 / 144 = 0.02292 > 0.020
    c = get(check_building(building([story(1, max_x=0.60, avg_x=0.60)])), "Story 1", DRIFT_X)
    assert c["status"] == "FAIL"
    assert c["dc_ratio"] == pytest.approx(5.5 * 0.60 / 144.0 / 0.020, abs=1e-3)


def test_ie_defaults_from_risk_category():
    # Risk Category IV: Ie = 1.5, limit = 0.010
    b = building([story(1, max_x=0.30, avg_x=0.30)], risk_category="IV")
    c = get(check_building(b), "Story 1", DRIFT_X)
    assert c["demand_value"] == pytest.approx(5.5 * 0.30 / 1.5 / 144.0, abs=1e-5)
    assert c["capacity_limit"] == 0.010


def test_drift_at_exact_limit_passes():
    # 2.88 / 144 = 0.0200 exactly
    b = building([story(1, max_x=2.88, avg_x=2.88)], drift_is_amplified=True)
    assert get(check_building(b), "Story 1", DRIFT_X)["status"] == "PASS"


def test_missing_cd_is_rejected_for_elastic_drifts():
    b = building([story(1)])
    del b["project_info"]["cd"]
    with pytest.raises(ValueError, match="cd is required"):
        check_building(b)


@pytest.mark.parametrize(
    "structure_type, risk, limit",
    [
        ("other", "I", 0.020),
        ("other", "II", 0.020),
        ("other", "III", 0.015),
        ("other", "IV", 0.010),
        ("four_story_or_less_drift_tolerant", "II", 0.025),
        ("four_story_or_less_drift_tolerant", "III", 0.020),
        ("four_story_or_less_drift_tolerant", "IV", 0.015),
        ("masonry_cantilever_shear_wall", "II", 0.010),
        ("other_masonry_shear_wall", "IV", 0.007),
    ],
)
def test_table_12_12_1(structure_type, risk, limit):
    assert DRIFT_LIMITS[structure_type][risk] == limit
    b = building([story(1)], structure_type=structure_type, risk_category=risk, drift_is_amplified=True)
    assert get(check_building(b), "Story 1", DRIFT_X)["capacity_limit"] == limit


def test_moment_frame_limit_divided_by_rho_in_sdc_d():
    b = building([story(1)], drift_is_amplified=True, moment_frame_rho=1.3)
    c = get(check_building(b), "Story 1", DRIFT_X)
    assert c["capacity_limit"] == pytest.approx(0.020 / 1.3, abs=1e-5)
    assert "12.12.1.1" in c["code_reference"]


def test_rho_not_applied_below_sdc_d():
    b = building([story(1)], drift_is_amplified=True, moment_frame_rho=1.3, seismic_design_category="C")
    assert get(check_building(b), "Story 1", DRIFT_X)["capacity_limit"] == 0.020


def test_drift_limit_override():
    b = building([story(1)], drift_is_amplified=True, drift_limit_ratio=0.0125)
    assert get(check_building(b), "Story 1", DRIFT_X)["capacity_limit"] == 0.0125


def test_edge_drift_governs_only_when_torsionally_irregular():
    # Regular: ratio 1.1 -> uses average (CM proxy) 1.0 in
    regular = building([story(1, max_x=1.1, avg_x=1.0)], drift_is_amplified=True)
    assert get(check_building(regular), "Story 1", DRIFT_X)["demand_value"] == pytest.approx(1.0 / 144, abs=1e-5)
    # Irregular: ratio 1.3 -> uses edge (max) 1.3 in
    irregular = building([story(1, max_x=1.3, avg_x=1.0)], drift_is_amplified=True)
    assert get(check_building(irregular), "Story 1", DRIFT_X)["demand_value"] == pytest.approx(1.3 / 144, abs=1e-5)
    # Irregular but SDC B -> CM drift
    sdc_b = building([story(1, max_x=1.3, avg_x=1.0)], drift_is_amplified=True, seismic_design_category="B")
    assert get(check_building(sdc_b), "Story 1", DRIFT_X)["demand_value"] == pytest.approx(1.0 / 144, abs=1e-5)


# ---------- Summary and validation ----------


def test_summary_aggregation():
    stories = [
        story(1, max_x=1.5, avg_x=1.0, kx=500.0),  # torsional irregularity + extreme soft story
        story(2),
        story(3, max_y=4.0, avg_y=4.0),  # drift 4.0 / 144 = 0.0278 > 0.020
    ]
    res = check_building(building(stories, drift_is_amplified=True, seismic_design_category="E"))
    s = res["summary"]
    assert s["building_name"] == "Test Tower"
    assert s["total_stories"] == 3
    assert s["overall_status"] == "FAIL"
    assert s["total_violations"] == 2  # soft story (prohibited in E) + drift; torsion is a WARNING
    statuses = {r["story_name"]: r["status"] for r in res["story_results"]}
    assert statuses == {"Story 1": "FAIL", "Story 2": "PASS", "Story 3": "FAIL"}
    # Max D/C is the drift D/C only
    assert s["max_dc_ratio"] == pytest.approx(4.0 / 144 / 0.020, abs=1e-3)
    items = {i["action"]: i["stories"] for i in s["action_items"]}
    assert len(items) == len(s["action_items"])
    assert any("12.3.3.1" in a and stories == ["Story 1"] for a, stories in items.items())


def test_regular_building_passes_everything():
    res = check_building(building([story(n) for n in range(1, 6)]))
    assert res["summary"]["overall_status"] == "PASS"
    assert res["summary"]["total_violations"] == 0
    assert res["summary"]["total_warnings"] == 0


def test_output_matches_contract_keys():
    res = check_building(building([story(1), story(2)]))
    assert set(res) == {"summary", "basis", "story_results"}
    sr = res["story_results"][0]
    assert {"story_name", "elevation_in", "height_in", "status", "max_dc_ratio", "deformations", "checks"} == set(sr)
    assert set(sr["checks"][0]) == {
        "check_type",
        "code_reference",
        "demand_value",
        "capacity_limit",
        "dc_ratio",
        "status",
        "formula_breakdown",
        "output_case",
        "actions",
    }


@pytest.mark.parametrize(
    "mutation, message",
    [
        ({"risk_category": "V"}, "risk_category"),
        ({"seismic_design_category": "G"}, "seismic_design_category"),
        ({"structure_type": "timber"}, "structure_type"),
    ],
)
def test_invalid_project_info(mutation, message):
    with pytest.raises(ValueError, match=message):
        check_building(building([story(1)], **mutation))


def test_invalid_story_values():
    with pytest.raises(ValueError, match="smaller than avg"):
        check_building(building([story(1, max_x=0.2, avg_x=0.3)]))


# ---------- Soft story exceptions, Section 12.3.2.2 ----------


def soft_building(drifts, **info):
    """Story 1 has an extreme soft story by stiffness; `drifts` are the average drifts bottom-up."""
    stories = [story(n + 1, max_x=d, avg_x=d, kx=500.0 if n == 0 else 1000.0) for n, d in enumerate(drifts)]
    return building(stories, drift_is_amplified=True, apply_soft_story_exception=True, **info)


def test_exception_1_removes_soft_story_when_drift_ratios_are_within_130_percent():
    # 0.39 / 0.30 = 1.30 exactly -> exception applies
    c = get(check_building(soft_building([0.39, 0.30, 0.30, 0.30])), "Story 1", SOFT_X)
    assert c["status"] == "PASS"
    assert "12.3.2.2" in c["code_reference"]
    assert "Exception 1" in c["formula_breakdown"]
    assert "500.0 / 1000.0 = 0.500" in c["formula_breakdown"]  # stiffness numbers are still shown
    assert (c["demand_value"], c["capacity_limit"], c["dc_ratio"]) == (1.3, 1.3, 1.0)


def test_exception_1_not_met_keeps_the_irregularity():
    # 0.40 / 0.30 = 1.33 > 1.30
    c = get(check_building(soft_building([0.40, 0.30, 0.30, 0.30])), "Story 1", SOFT_X)
    assert c["status"] == "WARNING"
    assert c["code_reference"].endswith("Type 1b")
    assert "Exception 1 not met" in c["formula_breakdown"]
    assert "Story 1 is 1.33 x" in c["formula_breakdown"]


def test_exception_1_ignores_the_top_two_stories_relationship():
    # Story 3 / Story 4 = 3.0, but that pair is the top two stories and is not evaluated.
    c = get(check_building(soft_building([0.30, 0.30, 0.90, 0.30])), "Story 1", SOFT_X)
    assert c["status"] == "PASS"
    # The same jump one level lower (Story 3 / Story 4 of five) is evaluated and blocks the exception.
    c = get(check_building(soft_building([0.30, 0.30, 0.90, 0.30, 0.30])), "Story 1", SOFT_X)
    assert c["status"] == "WARNING"
    assert "Story 3 is 3.00 x" in c["formula_breakdown"]


def test_exception_1_is_per_direction_and_uses_average_drift():
    b = soft_building([0.39, 0.30, 0.30, 0.30])
    b["stories"][0]["stiffness_y_kip_in"] = 500.0
    b["stories"][0]["avg_drift_y_in"] = b["stories"][0]["max_drift_y_in"] = 0.45  # 1.5 x in Y
    res = check_building(b)
    assert get(res, "Story 1", SOFT_X)["status"] == "PASS"
    assert get(res, "Story 1", "Soft Story Irregularity (Y-Dir)")["status"] == "WARNING"


@pytest.mark.parametrize("sdc, status", [("B", "PASS"), ("D", "PASS"), ("E", "FAIL")])
def test_exception_2_two_story_buildings(sdc, status):
    c = get(check_building(soft_building([0.60, 0.30], seismic_design_category=sdc)), "Story 1", SOFT_X)
    assert c["status"] == status
    assert ("Exception 2" in c["formula_breakdown"]) == (status == "PASS")


def test_exception_can_be_switched_off():
    b = soft_building([0.39, 0.30, 0.30, 0.30])
    b["project_info"]["apply_soft_story_exception"] = False
    assert get(check_building(b), "Story 1", SOFT_X)["status"] == "WARNING"


# ---------- Input validation and basis (reviewer findings 2026-11-17) ----------


@pytest.mark.parametrize("rho", [0.5, 1.2, 3.0])
def test_rho_must_be_1_0_or_1_3(rho):
    with pytest.raises(ValueError, match="1.0 or 1.3"):
        check_building(building([story(1)], drift_is_amplified=True, moment_frame_rho=rho))


def test_four_story_limit_rejected_for_taller_buildings():
    stories = [story(n) for n in range(1, 6)]
    with pytest.raises(ValueError, match="4 stories or fewer"):
        check_building(building(stories, drift_is_amplified=True, structure_type="four_story_or_less_drift_tolerant"))
    check_building(building(stories[:4], drift_is_amplified=True, structure_type="four_story_or_less_drift_tolerant"))


def test_zero_or_negative_stiffness_is_not_applicable():
    stories = [story(1, kx=0.0), story(2), story(3, kx=-50.0), story(4)]
    res = check_building(building(stories, drift_is_amplified=True))
    for name in ("Story 1", "Story 2", "Story 3"):
        c = get(res, name, SOFT_X)
        assert c["status"] == "N/A"
        assert "stiffness <= 0" in c["formula_breakdown"]


def test_pass_rows_are_not_labelled_with_an_irregularity_type():
    res = check_building(building([story(1), story(2)], drift_is_amplified=True))
    for c in res["story_results"][0]["checks"]:
        if c["status"] == "PASS" and "Soft" in c["check_type"]:
            assert "Type" not in c["code_reference"]


def test_basis_records_resolved_defaults():
    b = building([story(1)], risk_category="III")
    basis = check_building(b)["basis"]
    assert basis["ie"] == 1.25 and basis["diaphragm"] == "rigid" and basis["seismic_design_category"] == "D"
    assert basis["drift_limit"] == 0.015
    assert basis["torsion_strength_irregular"] is None


def test_exception_uses_single_case_drifts_when_given():
    b = soft_building([0.40, 0.30, 0.30, 0.30])  # envelope drifts would fail Exception 1 (1.33)
    for st, d in zip(b["stories"], [0.36, 0.30, 0.30, 0.30]):  # one consistent case: 1.20
        st["exc_drift_x_in"] = d
        st["exc_drift_x_case"] = "EQX"
    c = get(check_building(b), "Story 1", SOFT_X)
    assert c["status"] == "PASS" and "output case EQX" in c["formula_breakdown"]
