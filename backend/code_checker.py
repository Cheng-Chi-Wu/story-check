"""Deterministic ASCE 7-22 Chapter 12 code checks.

Input:  BuildingAnalysisInput dict (see blueprint section 5.1)
Output: CodeCheckResult dict       (see blueprint section 5.2)

Checks implemented
  * Horizontal torsional irregularity  - Table 12.3-1, Type 1, Torsional Irregularity Ratio (TIR)
                                          per Section 12.3.2.1.1. ASCE 7-22 has a single torsional
                                          type; the 7-16 "extreme" Type 1b no longer exists.
  * Vertical soft story irregularity   - Table 12.3-2, Type 1a / 1b, with the Section 12.3.2.2 exceptions
  * Allowable story drift              - Section 12.12.1, Table 12.12-1

Status convention
  PASS    - regular / within limit
  WARNING - irregularity exists and is permitted, but triggers extra requirements (listed in "actions")
  FAIL    - prohibited by Section 12.3.3.1, or drift exceeds the allowable
  N/A     - not applicable or not computable from the data; the reason is in formula_breakdown

This is a checking aid. Every limit below must be verified against the
published ASCE 7-22 text by a licensed engineer before use on a real project.
"""

from __future__ import annotations

PASS, WARNING, FAIL, NA = "PASS", "WARNING", "FAIL", "N/A"
_SEVERITY = {NA: -1, PASS: 0, WARNING: 1, FAIL: 2}

# Table 12.3-1 / Section 12.3.2.1.1
TIR_IRREGULAR = 1.2
TIR_RHO = 1.4  # above this, rho = 1.3 is required in SDC D-F (Section 12.3.4.2)

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
MAX_STORIES = {"four_story_or_less_drift_tolerant": 4}

# Table 1.5-2 seismic importance factor
IMPORTANCE_FACTOR = {"I": 1.0, "II": 1.0, "III": 1.25, "IV": 1.5}

SDC_VALUES = ("A", "B", "C", "D", "E", "F")
PROHIBITED_1B_SDC = ("E", "F")  # Section 12.3.3.1, vertical Type 1b
EDGE_DRIFT_SDC = ("C", "D", "E", "F")  # Section 12.12.1 / 12.8.4.3
RHO_SDC = ("D", "E", "F")
RHO_VALUES = (1.0, 1.3)  # Section 12.3.4

# Section 12.3.2.2
SOFT_EXCEPTION_DRIFT_RATIO = 1.30  # Exception 1
SOFT_EXCEPTION_2_SDC = ("B", "C", "D")  # Exception 2, two-story buildings

_EPS = 1e-9  # guards threshold comparisons against float noise


def _worst(statuses):
    return max(statuses, key=_SEVERITY.__getitem__, default=NA)


def _check(check_type, ref, demand, limit, dc, status, text, case=None, actions=()):
    return {
        "check_type": check_type,
        "code_reference": ref,
        "demand_value": demand,
        "capacity_limit": limit,
        "dc_ratio": dc,
        "status": status,
        "formula_breakdown": text,
        "output_case": case,
        "actions": list(actions),
    }


class _Settings:
    """Validated project-level parameters."""

    def __init__(self, info: dict, n_stories: int):
        self.risk = str(info.get("risk_category", "")).upper()
        if self.risk not in IMPORTANCE_FACTOR:
            raise ValueError(f"risk_category must be I, II, III or IV, got {info.get('risk_category')!r}")

        self.sdc = str(info.get("seismic_design_category") or "D").upper()
        if self.sdc not in SDC_VALUES:
            raise ValueError(f"seismic_design_category must be A-F, got {self.sdc!r}")

        self.structure_type = info.get("structure_type") or "other"
        if self.structure_type not in DRIFT_LIMITS:
            raise ValueError(f"unknown structure_type {self.structure_type!r}")
        limit = MAX_STORIES.get(self.structure_type)
        if limit and n_stories > limit:
            raise ValueError(
                f"structure_type {self.structure_type!r} applies to buildings of {limit} stories or fewer "
                f"(Table 12.12-1); this building has {n_stories}"
            )

        self.diaphragm = (info.get("diaphragm") or "rigid").lower()
        if self.diaphragm not in ("rigid", "semirigid", "flexible"):
            raise ValueError(f"unknown diaphragm {self.diaphragm!r}")

        self.soft_exception = bool(info.get("apply_soft_story_exception", True))

        # Section 12.3.2.1.1 strength criterion: more than 75 % of the story's lateral strength on one
        # side of the center of mass. ETABS story tables do not carry it, so the engineer states it.
        strength = info.get("torsion_strength_irregular")
        self.torsion_strength = None if strength is None else bool(strength)

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

        self.rho = None
        rho = info.get("moment_frame_rho")
        if rho is not None:
            rho = float(rho)
            if not any(abs(rho - v) < 1e-6 for v in RHO_VALUES):
                raise ValueError(f"moment_frame_rho must be 1.0 or 1.3 (Section 12.3.4), got {rho:g}")
            if self.sdc in RHO_SDC:
                self.rho = rho
                self.drift_limit /= rho
                self.drift_limit_note += f", divided by rho = {rho:g} per 12.12.1.1"
                self.drift_ref = "ASCE 7-22 Table 12.12-1, Section 12.12.1.1"
        if self.drift_limit <= 0:
            raise ValueError("drift limit must be positive")

    def basis(self) -> dict:
        """The parameters actually used, defaults included, for the report."""
        return {
            "risk_category": self.risk,
            "seismic_design_category": self.sdc,
            "structure_type": self.structure_type,
            "diaphragm": self.diaphragm,
            "drift_is_amplified": self.amplified,
            "cd": None if self.amplified else self.cd,
            "ie": None if self.amplified else self.ie,
            "rho_applied_to_drift": self.rho,
            "drift_limit": round(self.drift_limit, 5),
            "drift_limit_basis": self.drift_limit_note,
            "apply_soft_story_exception": self.soft_exception,
            "torsion_strength_irregular": self.torsion_strength,
        }


def _torsion_actions(tir: float, s: _Settings) -> list[str]:
    """Follow-up requirements for a Type 1 torsional irregularity (verify against the published text)."""
    actions = []
    if s.sdc in EDGE_DRIFT_SDC:
        actions.append("Amplify accidental torsion by A_x per 12.8.4.3 and confirm the exported drifts include it")
    elif s.sdc == "B" and tir > TIR_RHO + _EPS:
        actions.append("Include accidental torsion per 12.8.4.2 (SDC B with TIR > 1.4)")
    if s.sdc in RHO_SDC:
        actions.append("Increase design forces for diaphragm connections and collectors by 25% per 12.3.3.4")
        actions.append("Confirm the analysis procedure is permitted for this irregularity per Table 12.6-1")
        if tir > TIR_RHO + _EPS:
            actions.append("Use rho = 1.3 per 12.3.4.2 (TIR > 1.4)")
    if s.sdc in ("E", "F"):
        actions.append("Apply orthogonal load combination per 12.5")
    return actions


def _check_torsion(story: dict, d: str, s: _Settings):
    """Table 12.3-1 Type 1 via Section 12.3.2.1.1. Returns (check, torsionally_irregular)."""
    check_type = f"Torsional Irregularity ({d.upper()}-Dir)"
    ref = "ASCE 7-22 Table 12.3-1, Type 1; Section 12.3.2.1.1"
    if s.diaphragm == "flexible":
        return _check(check_type, "ASCE 7-22 Table 12.3-1", None, TIR_IRREGULAR, None, NA,
                      "Not applicable: Table 12.3-1 Type 1 applies only to rigid or semirigid diaphragms"), False

    d_max = float(story[f"max_drift_{d}_in"])
    d_avg = float(story[f"avg_drift_{d}_in"])
    tir = story.get(f"tir_{d}")
    case = story.get(f"tir_{d}_case") or story.get(f"drift_{d}_case")
    if tir is None:
        if d_avg <= 0:
            return _check(check_type, ref, None, TIR_IRREGULAR, None, NA,
                          "Not computable: average drift is zero in this direction"), False
        tir = d_max / d_avg
        head = f"TIR = Delta_max / Delta_avg = {d_max:.3f} in / {d_avg:.3f} in = {tir:.3f}"
    else:
        tir = float(tir)
        head = f"TIR = Delta_max / Delta_avg = {tir:.3f} (largest over the output cases, governing: {case})"

    by_ratio = tir > TIR_IRREGULAR + _EPS
    by_strength = s.torsion_strength is True
    if by_ratio or by_strength:
        reasons = []
        if by_ratio:
            reasons.append(f"TIR > {TIR_IRREGULAR:.2f}")
        if by_strength:
            reasons.append("more than 75% of the lateral strength is on one side of the center of mass (engineer input)")
        level = f"; TIR > {TIR_RHO:.2f}" if tir > TIR_RHO + _EPS else ""
        text = f"{head} -> Torsional Irregularity, Type 1 ({' and '.join(reasons)}{level})"
        return _check(check_type, ref, round(tir, 4), TIR_IRREGULAR, round(tir / TIR_IRREGULAR, 3), WARNING,
                      text, case, _torsion_actions(tir, s)), True

    text = f"{head} <= {TIR_IRREGULAR:.2f} -> No Torsional Irregularity"
    if s.torsion_strength is None:
        text += ("; strength criterion (more than 75% of lateral strength on one side of the center of mass) "
                 "not evaluated, confirm separately")
    return _check(check_type, ref, round(tir, 4), TIR_IRREGULAR, round(tir / TIR_IRREGULAR, 3), PASS,
                  text, case), False


def _soft_story_exception(stories: list, d: str, s: _Settings):
    """Section 12.3.2.2: returns (exemption note or None, why-not text, governing drift-ratio factor).

    Exception 1: no story drift ratio exceeds 130% of that of the story above; the top two stories
    are not compared with each other. Drifts come from one output case for the whole building
    (exc_drift_*), so neighbouring stories are compared under the same loading.
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
        return float(st.get(f"exc_drift_{d}_in", st[f"avg_drift_{d}_in"])) / float(st["height_in"])

    case = stories[0].get(f"exc_drift_{d}_case")
    src = f" (average drifts from output case {case}; 12.3.2.2 permits ignoring torsional effects)" if case else ""
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
            f"that of the story above (at {worst_name}) <= {SOFT_EXCEPTION_DRIFT_RATIO:.2f}{src}"
        ), "", worst
    return None, (
        f"; 12.3.2.2 Exception 1 not met: drift ratio at {worst_name} is {worst:.2f} x "
        f"that of the story above > {SOFT_EXCEPTION_DRIFT_RATIO:.2f}{src}"
    ), worst


def _soft_actions(s: _Settings) -> list[str]:
    if s.sdc in RHO_SDC:
        return ["Confirm the analysis procedure is permitted for this irregularity per Table 12.6-1"]
    return []


def _check_soft_story(stories: list, i: int, d: str, s: _Settings, exception=(None, "", 0.0)):
    """Table 12.3-2 Type 1a/1b for stories[i]; stories are sorted bottom-up."""
    above = stories[i + 1 : i + 4]
    if not above:
        return None  # top story has nothing above to compare with

    check_type = f"Soft Story Irregularity ({d.upper()}-Dir)"
    key = f"stiffness_{d}_kip_in"
    case = stories[i].get(f"stiffness_{d}_case")
    exempt, not_met, factor = exception
    k = float(stories[i][key])
    ks_above = [float(a[key]) for a in above]

    if k <= 0 or min(ks_above) <= 0:
        bad = [st["story_name"] for st in [stories[i], *above] if float(st[key]) <= 0]
        reason = (f"story stiffness <= 0 at {', '.join(bad)} (often a story-shear reversal under "
                  "higher-mode response)")
        if exempt:
            return _check(check_type, "ASCE 7-22 Table 12.3-2; Section 12.3.2.2", round(factor, 4),
                          SOFT_EXCEPTION_DRIFT_RATIO, round(factor / SOFT_EXCEPTION_DRIFT_RATIO, 3), PASS,
                          f"Stiffness ratio not computable: {reason}; the irregularity {exempt}", case)
        return _check(check_type, "ASCE 7-22 Table 12.3-2", None, None, None, NA,
                      f"Not computable: {reason}. Evaluate with a unit-load stiffness or the 12.3.2.2 "
                      "drift-ratio exception", case)

    k_above = ks_above[0]
    k_avg3 = sum(ks_above) / 3 if len(ks_above) == 3 else None
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

    if exempt and below(SOFT_1A):
        # Report the exception's own criterion, so a passing check never shows D/C > 1.
        return _check(check_type, "ASCE 7-22 Table 12.3-2; Section 12.3.2.2", round(factor, 4),
                      SOFT_EXCEPTION_DRIFT_RATIO, round(factor / SOFT_EXCEPTION_DRIFT_RATIO, 3), PASS,
                      f"{head} -> stiffness criterion triggered, but the irregularity {exempt}", case)
    actions = ()
    if below(SOFT_1B):
        ref = "ASCE 7-22 Table 12.3-2, Type 1b"
        if s.sdc in PROHIBITED_1B_SDC:
            status = FAIL
            text = f"{head} -> below {SOFT_1B[0]:.2f} / {SOFT_1B[1]:.2f} (Extreme Soft Story - not permitted in SDC {s.sdc} per 12.3.3.1{not_met})"
            actions = ["Revise the structure: an extreme soft story is not permitted in SDC E or F (12.3.3.1)"]
        else:
            status = WARNING
            text = f"{head} -> below {SOFT_1B[0]:.2f} / {SOFT_1B[1]:.2f} (Extreme Soft Story{not_met})"
            actions = _soft_actions(s)
    elif below(SOFT_1A):
        ref = "ASCE 7-22 Table 12.3-2, Type 1a"
        status = WARNING
        text = f"{head} -> Soft Story{not_met}"
        actions = _soft_actions(s)
    else:
        ref = "ASCE 7-22 Table 12.3-2"
        status = PASS
        text = f"{head} -> No Soft Story"

    return _check(check_type, ref, round(k, 4), round(required, 4), round(required / k, 3), status, text,
                  case, actions)


def _check_drift(story: dict, d: str, s: _Settings, torsion_irregular: bool):
    """Section 12.12.1 / Table 12.12-1, with Section 12.8.6 amplification."""
    h = float(story["height_in"])
    # Edge (max) drift governs for torsionally irregular structures in SDC C-F; otherwise drift at
    # the center of mass, approximated here by the average of the two ends.
    use_max = torsion_irregular and s.sdc in EDGE_DRIFT_SDC
    raw = float(story[f"max_drift_{d}_in" if use_max else f"avg_drift_{d}_in"])
    where = "edge (max), torsionally irregular" if use_max else "center of mass, approximated by avg of ends"

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
    actions = () if ok else ["Stiffen the structure or revise the design until the story drift is within the limit"]
    return _check(f"Allowable Story Drift ({d.upper()}-Dir)", s.drift_ref, round(ratio, 5), round(s.drift_limit, 5),
                  round(ratio / s.drift_limit, 3), PASS if ok else FAIL, text, story.get(f"drift_{d}_case"), actions)


def _has(story: dict, d: str) -> bool:
    return story.get(f"max_drift_{d}_in") is not None


def _validate_story(story: dict, directions):
    name = story.get("story_name", "?")
    if float(story["height_in"]) <= 0:
        raise ValueError(f"{name}: height_in must be positive")
    for d in directions:
        d_max, d_avg = float(story[f"max_drift_{d}_in"]), float(story[f"avg_drift_{d}_in"])
        if d_max < 0 or d_avg < 0:
            raise ValueError(f"{name}: drifts must be non-negative (use absolute values)")
        if d_max < d_avg - _EPS:
            raise ValueError(f"{name}: max_drift_{d}_in is smaller than avg_drift_{d}_in")
        if d_avg <= 0 < d_max:
            raise ValueError(
                f"{name}: avg_drift_{d}_in is zero while max_drift_{d}_in is {d_max:g}; check the drift export"
            )


def check_building(data: dict) -> dict:
    """Run all checks on a BuildingAnalysisInput dict and return a CodeCheckResult dict."""
    info = data["project_info"]
    stories = sorted(data["stories"], key=lambda st: float(st["elevation_in"]))
    if not stories:
        raise ValueError("stories must not be empty")
    settings = _Settings(info, len(stories))
    # A direction is checked when every story has drift data for it; one-direction input is allowed.
    directions = [d for d in ("x", "y") if all(_has(st, d) for st in stories)]
    partial = [d.upper() for d in ("x", "y") if d not in directions and any(_has(st, d) for st in stories)]
    if partial:
        lacking = [st["story_name"] for st in stories if not all(_has(st, d.lower()) for d in partial)]
        raise ValueError(f"{'/'.join(partial)}-direction drifts are missing for: {', '.join(lacking)}")
    if not directions:
        raise ValueError("stories have no drift data in either direction")
    for story in stories:
        _validate_story(story, directions)

    exceptions = {d: _soft_story_exception(stories, d, settings) for d in directions}

    story_results = []
    for i, story in enumerate(stories):
        checks = []
        for d in ("x", "y"):
            if d not in directions:
                checks.append(_check(f"{d.upper()}-Direction Checks", "-", None, None, None, NA,
                                     f"Not checked: no {d.upper()}-direction drift data was provided "
                                     "(torsion, soft story and drift)"))
                continue
            torsion, irregular = _check_torsion(story, d, settings)
            soft = _check_soft_story(stories, i, d, settings, exceptions[d])
            drift = _check_drift(story, d, settings, irregular)
            checks += [c for c in (torsion, soft, drift) if c]

        rated = [c["dc_ratio"] for c in checks if c["dc_ratio"] is not None]
        story_results.append(
            {
                "story_name": story["story_name"],
                "elevation_in": story["elevation_in"],
                "height_in": story["height_in"],
                "status": _worst(c["status"] for c in checks),
                "max_dc_ratio": max(rated, default=0.0),
                # 0.0 for a direction without data, so the 3D view still draws
                "deformations": {
                    k: story.get(k) or 0.0
                    for k in ("max_drift_x_in", "avg_drift_x_in", "max_drift_y_in", "avg_drift_y_in")
                },
                "checks": checks,
            }
        )

    all_checks = [c for r in story_results for c in r["checks"]]
    drift_dc = [c["dc_ratio"] for c in all_checks if c["check_type"].startswith("Allowable Story Drift")]
    triggered: dict[str, list[str]] = {}  # action -> stories that triggered it, in first-seen order
    for r in story_results:
        for c in r["checks"]:
            for a in c["actions"]:
                names = triggered.setdefault(a, [])
                if r["story_name"] not in names:
                    names.append(r["story_name"])
    action_items = [{"action": a, "stories": names} for a, names in triggered.items()]
    return {
        "summary": {
            "building_name": info.get("building_name", ""),
            "total_stories": len(story_results),
            "overall_status": _worst(r["status"] for r in story_results),
            "total_violations": sum(c["status"] == FAIL for c in all_checks),
            "total_warnings": sum(c["status"] == WARNING for c in all_checks),
            "total_not_applicable": sum(c["status"] == NA for c in all_checks),
            # Drift checks only: the one ratio that is a true demand / capacity.
            "max_dc_ratio": max(drift_dc, default=0.0),
            "action_items": action_items,
        },
        "basis": {**settings.basis(), "directions_checked": [d.upper() for d in directions]},
        "story_results": story_results,
    }
