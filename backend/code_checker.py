"""Deterministic ASCE 7-22 Chapter 12 code checks.

Input:  BuildingAnalysisInput dict (see blueprint section 5.1)
Output: CodeCheckResult dict       (see blueprint section 5.2)

Checks implemented
  * Horizontal torsional irregularity  - Table 12.3-1, Type 1a / 1b
  * Vertical soft story irregularity   - Table 12.3-2, Type 1a / 1b, with the Section 12.3.2.2 exceptions
  * Allowable story drift              - Section 12.12.1, Table 12.12-1

Status convention
  PASS    - regular / within limit
  WARNING - irregularity exists and is permitted, but triggers extra requirements
  FAIL    - prohibited by Section 12.3.3.1, or drift exceeds the allowable

This is a checking aid. Every limit below must be verified against the
published ASCE 7-22 text by a licensed engineer before use on a real project.
"""

from __future__ import annotations

PASS, WARNING, FAIL = "PASS", "WARNING", "FAIL"
_SEVERITY = {PASS: 0, WARNING: 1, FAIL: 2}

# Table 12.3-1
TORSION_1A = 1.2
TORSION_1B = 1.4

# Table 12.3-2: (ratio to story above, ratio to average of three stories above)
SOFT_1A = (0.70, 0.80)
SOFT_1B = (0.60, 0.70)

# Table 12.12-1: allowable story drift / h_sx, keyed by structure type then risk category
DRIFT_LIMITS = {
    "four_story_or_less_drift_tolerant": {"I": 0.025, "II": 0.025, "III": 0.020, "IV": 0.015},
    "masonry_cantilever_shear_wall": {"I": 0.010, "II": 0.010, "III": 0.010, "IV": 0.010},
    "other_masonry_shear_wall": {"I": 0.007, "II": 0.007, "III": 0.007, "IV": 0.007},
    "other": {"I": 0.020, "II": 0.020, "III": 0.015, "IV": 0.010},
}

# Table 1.5-2 seismic importance factor
IMPORTANCE_FACTOR = {"I": 1.0, "II": 1.0, "III": 1.25, "IV": 1.5}

SDC_VALUES = ("A", "B", "C", "D", "E", "F")
PROHIBITED_1B_SDC = ("E", "F")  # Section 12.3.3.1
AX_SDC = ("C", "D", "E", "F")  # Section 12.8.4.3

# Section 12.3.2.2
SOFT_EXCEPTION_DRIFT_RATIO = 1.30  # Exception 1
SOFT_EXCEPTION_2_SDC = ("B", "C", "D")  # Exception 2, two-story buildings

_EPS = 1e-9  # guards threshold comparisons against float noise


def _worst(statuses):
    return max(statuses, key=_SEVERITY.__getitem__, default=PASS)


class _Settings:
    """Validated project-level parameters."""

    def __init__(self, info: dict):
        self.risk = str(info.get("risk_category", "")).upper()
        if self.risk not in IMPORTANCE_FACTOR:
            raise ValueError(f"risk_category must be I, II, III or IV, got {info.get('risk_category')!r}")

        self.sdc = str(info.get("seismic_design_category") or "D").upper()
        if self.sdc not in SDC_VALUES:
            raise ValueError(f"seismic_design_category must be A-F, got {self.sdc!r}")

        self.structure_type = info.get("structure_type") or "other"
        if self.structure_type not in DRIFT_LIMITS:
            raise ValueError(f"unknown structure_type {self.structure_type!r}")

        self.diaphragm = (info.get("diaphragm") or "rigid").lower()
        if self.diaphragm not in ("rigid", "semirigid", "flexible"):
            raise ValueError(f"unknown diaphragm {self.diaphragm!r}")

        self.soft_exception = bool(info.get("apply_soft_story_exception", True))

        # Drift amplification, Section 12.8.6: Delta = Cd * Delta_e / Ie
        self.amplified = bool(info.get("drift_is_amplified", False))
        self.ie = float(info.get("ie") or IMPORTANCE_FACTOR[self.risk])
        self.cd = info.get("cd")
        if not self.amplified:
            if self.cd is None:
                raise ValueError("cd is required when drift_is_amplified is false (ASCE 7-22 Section 12.8.6)")
            self.cd = float(self.cd)
            if self.cd <= 0 or self.ie <= 0:
                raise ValueError("cd and ie must be positive")

        # Allowable drift ratio: Table 12.12-1, optionally overridden, optionally / rho
        override = info.get("drift_limit_ratio")
        if override is not None:
            self.drift_limit = float(override)
            self.drift_limit_note = "user-specified"
        else:
            self.drift_limit = DRIFT_LIMITS[self.structure_type][self.risk]
            self.drift_limit_note = f"Table 12.12-1, Risk Category {self.risk}"
        self.drift_ref = "ASCE 7-22 Table 12.12-1"

        rho = info.get("moment_frame_rho")
        if rho is not None and self.sdc in ("D", "E", "F"):
            rho = float(rho)
            if rho <= 0:
                raise ValueError("moment_frame_rho must be positive")
            self.drift_limit /= rho
            self.drift_limit_note += f", divided by rho = {rho:g} per 12.12.1.1"
            self.drift_ref = "ASCE 7-22 Table 12.12-1, Section 12.12.1.1"
        if self.drift_limit <= 0:
            raise ValueError("drift limit must be positive")


def _check_torsion(story: dict, d: str, s: _Settings):
    """Table 12.3-1 Type 1a/1b. Returns (check or None, torsionally_irregular)."""
    if s.diaphragm == "flexible":
        return None, False
    d_max = float(story[f"max_drift_{d}_in"])
    d_avg = float(story[f"avg_drift_{d}_in"])
    if d_avg <= 0:
        return None, False

    ratio = d_max / d_avg
    head = f"Delta_max / Delta_avg = {d_max:.3f} in / {d_avg:.3f} in = {ratio:.3f}"
    ax_note = "; amplify accidental torsion by A_x per 12.8.4.3" if s.sdc in AX_SDC else ""

    if ratio > TORSION_1B + _EPS:
        ref = "ASCE 7-22 Table 12.3-1, Type 1b"
        if s.sdc in PROHIBITED_1B_SDC:
            status = FAIL
            text = f"{head} > {TORSION_1B:.2f} (Extreme Torsional Irregularity - not permitted in SDC {s.sdc} per 12.3.3.1)"
        else:
            status = WARNING
            text = f"{head} > {TORSION_1B:.2f} (Extreme Torsional Irregularity{ax_note})"
    elif ratio > TORSION_1A + _EPS:
        ref = "ASCE 7-22 Table 12.3-1, Type 1a"
        status = WARNING
        text = f"{head} > {TORSION_1A:.2f} (Torsional Irregularity{ax_note})"
    else:
        ref = "ASCE 7-22 Table 12.3-1, Type 1a"
        status = PASS
        text = f"{head} <= {TORSION_1A:.2f} (No Torsional Irregularity)"

    check = {
        "check_type": f"Torsional Irregularity ({d.upper()}-Dir)",
        "code_reference": ref,
        "demand_value": round(ratio, 4),
        "capacity_limit": TORSION_1A,
        "dc_ratio": round(ratio / TORSION_1A, 3),
        "status": status,
        "formula_breakdown": text,
    }
    return check, status != PASS


def _soft_story_exception(stories: list, d: str, s: _Settings):
    """Section 12.3.2.2: returns (exemption note or None, why-not text, governing drift-ratio factor).

    Exception 1: no story drift ratio exceeds 130% of that of the story above. Torsion is not
    considered (average drift is used) and the top two stories are not compared with each other.
    Exception 2: one-story buildings, and two-story buildings in SDC B, C or D.
    """
    if not s.soft_exception:
        return None, "", 0.0
    n = len(stories)
    if n == 1 or (n == 2 and s.sdc in SOFT_EXCEPTION_2_SDC):
        return f"not required for a {n}-story building in SDC {s.sdc} per 12.3.2.2 Exception 2", "", 0.0
    if n < 3:
        return None, "", 0.0

    def drift_ratio(st):
        return float(st[f"avg_drift_{d}_in"]) / float(st["height_in"])

    worst, worst_name = 0.0, ""
    for lower, upper in zip(stories[: n - 2], stories[1 : n - 1]):
        above = drift_ratio(upper)
        if above <= 0:
            return None, "", 0.0  # cannot form the ratio; do not claim the exception
        r = drift_ratio(lower) / above
        if r > worst:
            worst, worst_name = r, lower["story_name"]
    if worst <= SOFT_EXCEPTION_DRIFT_RATIO + _EPS:
        return (
            f"does not apply per 12.3.2.2 Exception 1: largest story drift ratio is {worst:.2f} x "
            f"that of the story above (at {worst_name}) <= {SOFT_EXCEPTION_DRIFT_RATIO:.2f}"
        ), "", worst
    return None, (
        f"; 12.3.2.2 Exception 1 not met: drift ratio at {worst_name} is {worst:.2f} x "
        f"that of the story above > {SOFT_EXCEPTION_DRIFT_RATIO:.2f}"
    ), worst


def _check_soft_story(stories: list, i: int, d: str, s: _Settings, exception=(None, "", 0.0)):
    """Table 12.3-2 Type 1a/1b for stories[i]; stories are sorted bottom-up."""
    above = stories[i + 1 : i + 4]
    if not above:
        return None  # top story has nothing above to compare with

    key = f"stiffness_{d}_kip_in"
    k = float(stories[i][key])
    k_above = float(above[0][key])
    k_avg3 = sum(float(a[key]) for a in above) / 3 if len(above) == 3 else None

    r1 = k / k_above
    r3 = k / k_avg3 if k_avg3 else None

    def below(limits):
        return r1 < limits[0] - _EPS or (r3 is not None and r3 < limits[1] - _EPS)

    parts = [f"K_i / K_(i+1) = {k:.1f} / {k_above:.1f} = {r1:.3f} (limit {SOFT_1A[0]:.2f})"]
    required = SOFT_1A[0] * k_above
    if r3 is not None:
        parts.append(f"K_i / K_avg,3 above = {k:.1f} / {k_avg3:.1f} = {r3:.3f} (limit {SOFT_1A[1]:.2f})")
        required = max(required, SOFT_1A[1] * k_avg3)
    head = "; ".join(parts)

    exempt, not_met, factor = exception
    if exempt and below(SOFT_1A):
        # Report the exception's own criterion, so a passing check never shows D/C > 1.
        return {
            "check_type": f"Soft Story Irregularity ({d.upper()}-Dir)",
            "code_reference": "ASCE 7-22 Table 12.3-2; Section 12.3.2.2",
            "demand_value": round(factor, 4),
            "capacity_limit": SOFT_EXCEPTION_DRIFT_RATIO,
            "dc_ratio": round(factor / SOFT_EXCEPTION_DRIFT_RATIO, 3),
            "status": PASS,
            "formula_breakdown": f"{head} -> stiffness criterion triggered, but the irregularity {exempt}",
        }
    if below(SOFT_1B):
        ref = "ASCE 7-22 Table 12.3-2, Type 1b"
        if s.sdc in PROHIBITED_1B_SDC:
            status = FAIL
            text = f"{head} -> below {SOFT_1B[0]:.2f} / {SOFT_1B[1]:.2f} (Extreme Soft Story - not permitted in SDC {s.sdc} per 12.3.3.1{not_met})"
        else:
            status = WARNING
            text = f"{head} -> below {SOFT_1B[0]:.2f} / {SOFT_1B[1]:.2f} (Extreme Soft Story{not_met})"
    elif below(SOFT_1A):
        ref = "ASCE 7-22 Table 12.3-2, Type 1a"
        status = WARNING
        text = f"{head} -> Soft Story{not_met}"
    else:
        ref = "ASCE 7-22 Table 12.3-2, Type 1a"
        status = PASS
        text = f"{head} -> No Soft Story"

    return {
        "check_type": f"Soft Story Irregularity ({d.upper()}-Dir)",
        "code_reference": ref,
        "demand_value": round(k, 4),
        "capacity_limit": round(required, 4),  # minimum stiffness to avoid Type 1a
        "dc_ratio": round(required / k, 3),
        "status": status,
        "formula_breakdown": text,
    }


def _check_drift(story: dict, d: str, s: _Settings, torsion_irregular: bool):
    """Section 12.12.1 / Table 12.12-1, with Section 12.8.6 amplification."""
    h = float(story["height_in"])
    # 12.8.6: edge (max) drift governs for torsionally irregular structures in SDC C-F;
    # otherwise drift at the center of mass, approximated here by the average of the two ends.
    use_max = torsion_irregular and s.sdc in AX_SDC
    raw = float(story[f"max_drift_{d}_in" if use_max else f"avg_drift_{d}_in"])
    where = "edge (max), torsionally irregular per 12.8.6" if use_max else "center of mass (avg)"

    if s.amplified:
        design = raw
        steps = f"Delta = {design:.3f} in [{where}]"
    else:
        design = s.cd * raw / s.ie
        steps = f"Delta = C_d * Delta_e / I_e = {s.cd:g} * {raw:.3f} in / {s.ie:g} = {design:.3f} in [{where}]"

    ratio = design / h
    ok = ratio <= s.drift_limit + _EPS
    text = (
        f"{steps}; Delta / h_sx = {design:.3f} in / {h:.1f} in = {ratio:.4f} "
        f"{'<=' if ok else '>'} {s.drift_limit:.4f} ({s.drift_limit_note})"
    )
    return {
        "check_type": f"Allowable Story Drift ({d.upper()}-Dir)",
        "code_reference": s.drift_ref,
        "demand_value": round(ratio, 5),
        "capacity_limit": round(s.drift_limit, 5),
        "dc_ratio": round(ratio / s.drift_limit, 3),
        "status": PASS if ok else FAIL,
        "formula_breakdown": text,
    }


def _validate_story(story: dict):
    name = story.get("story_name", "?")
    if float(story["height_in"]) <= 0:
        raise ValueError(f"{name}: height_in must be positive")
    for d in ("x", "y"):
        if float(story[f"stiffness_{d}_kip_in"]) <= 0:
            raise ValueError(f"{name}: stiffness_{d}_kip_in must be positive")
        d_max, d_avg = float(story[f"max_drift_{d}_in"]), float(story[f"avg_drift_{d}_in"])
        if d_max < 0 or d_avg < 0:
            raise ValueError(f"{name}: drifts must be non-negative (use absolute values)")
        if d_max < d_avg - _EPS:
            raise ValueError(f"{name}: max_drift_{d}_in is smaller than avg_drift_{d}_in")


def check_building(data: dict) -> dict:
    """Run all checks on a BuildingAnalysisInput dict and return a CodeCheckResult dict."""
    info = data["project_info"]
    settings = _Settings(info)
    stories = sorted(data["stories"], key=lambda st: float(st["elevation_in"]))
    if not stories:
        raise ValueError("stories must not be empty")
    for story in stories:
        _validate_story(story)

    exceptions = {d: _soft_story_exception(stories, d, settings) for d in ("x", "y")}

    story_results = []
    for i, story in enumerate(stories):
        checks = []
        for d in ("x", "y"):
            torsion, irregular = _check_torsion(story, d, settings)
            soft = _check_soft_story(stories, i, d, settings, exceptions[d])
            drift = _check_drift(story, d, settings, irregular)
            checks += [c for c in (torsion, soft, drift) if c]

        story_results.append(
            {
                "story_name": story["story_name"],
                "elevation_in": story["elevation_in"],
                "height_in": story["height_in"],
                "status": _worst(c["status"] for c in checks),
                "max_dc_ratio": max(c["dc_ratio"] for c in checks),
                "deformations": {
                    k: story[k]
                    for k in ("max_drift_x_in", "avg_drift_x_in", "max_drift_y_in", "avg_drift_y_in")
                },
                "checks": checks,
            }
        )

    all_checks = [c for r in story_results for c in r["checks"]]
    return {
        "summary": {
            "building_name": info.get("building_name", ""),
            "total_stories": len(story_results),
            "overall_status": _worst(r["status"] for r in story_results),
            "total_violations": sum(c["status"] == FAIL for c in all_checks),
            "total_warnings": sum(c["status"] == WARNING for c in all_checks),
            "max_dc_ratio": max(r["max_dc_ratio"] for r in story_results),
        },
        "story_results": story_results,
    }
