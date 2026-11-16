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


# ---------- Torsional irregularity, Table 12.3-1 ----------


@pytest.mark.parametrize(
    "max_x, avg_x, status, ref",
    [
        (1.00, 1.00, "PASS", "Type 1a"),
        (1.20, 1.00, "PASS", "Type 1a"),  # exactly 1.2 is not "more than 1.2"
        (1.21, 1.00, "WARNING", "Type 1a"),
        (1.40, 1.00, "WARNING", "Type 1a"),  # exactly 1.4 is still Type 1a
        (1.41, 1.00, "WARNING", "Type 1b"),  # permitted in SDC D
    ],
)
def test_torsion_thresholds_sdc_d(max_x, avg_x, status, ref):
    res = check_building(building([story(1, max_x=max_x, avg_x=avg_x)], drift_is_amplified=True))
    c = get(res, "Story 1", TORSION_X)
    assert c["status"] == status
    assert c["code_reference"].endswith(ref)
    assert c["demand_value"] == pytest.approx(max_x / avg_x, abs=1e-4)
    assert c["dc_ratio"] == pytest.approx(max_x / avg_x / 1.2, abs=1e-3)


@pytest.mark.parametrize("sdc, status", [("B", "WARNING"), ("D", "WARNING"), ("E", "FAIL"), ("F", "FAIL")])
def test_extreme_torsion_prohibited_only_in_sdc_e_f(sdc, status):
    res = check_building(
        building([story(1, max_x=1.5, avg_x=1.0)], drift_is_amplified=True, seismic_design_category=sdc)
    )
    assert get(res, "Story 1", TORSION_X)["status"] == status


def test_ax_note_only_for_sdc_c_to_f():
    def text(sdc):
        b = building([story(1, max_x=1.3, avg_x=1.0)], drift_is_amplified=True, seismic_design_category=sdc)
        return get(check_building(b), "Story 1", TORSION_X)["formula_breakdown"]

    assert "12.8.4.3" in text("C")
    assert "12.8.4.3" not in text("B")


def test_flexible_diaphragm_skips_torsion():
    res = check_building(building([story(1, max_x=1.5, avg_x=1.0)], drift_is_amplified=True, diaphragm="flexible"))
    types = [c["check_type"] for c in res["story_results"][0]["checks"]]
    assert TORSION_X not in types


# ---------- Soft story, Table 12.3-2 ----------


@pytest.mark.parametrize(
    "k1, status, ref",
    [
        (700.0, "PASS", "Type 1a"),  # exactly 70% is not "less than 70%"
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
        story(1, max_x=1.5, avg_x=1.0, kx=500.0),  # extreme torsion + extreme soft story
        story(2),
        story(3, max_y=4.0, avg_y=4.0),  # drift 4.0 / 144 = 0.0278 > 0.020
    ]
    res = check_building(building(stories, drift_is_amplified=True, seismic_design_category="E"))
    s = res["summary"]
    assert s["building_name"] == "Test Tower"
    assert s["total_stories"] == 3
    assert s["overall_status"] == "FAIL"
    assert s["total_violations"] == 3
    statuses = {r["story_name"]: r["status"] for r in res["story_results"]}
    assert statuses == {"Story 1": "FAIL", "Story 2": "PASS", "Story 3": "FAIL"}
    assert s["max_dc_ratio"] == max(r["max_dc_ratio"] for r in res["story_results"])


def test_regular_building_passes_everything():
    res = check_building(building([story(n) for n in range(1, 6)]))
    assert res["summary"]["overall_status"] == "PASS"
    assert res["summary"]["total_violations"] == 0
    assert res["summary"]["total_warnings"] == 0


def test_output_matches_contract_keys():
    res = check_building(building([story(1), story(2)]))
    assert set(res) == {"summary", "story_results"}
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
    with pytest.raises(ValueError, match="stiffness"):
        check_building(building([story(1, kx=0.0)]))
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
