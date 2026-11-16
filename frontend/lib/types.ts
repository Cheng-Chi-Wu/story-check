export type Status = "PASS" | "WARNING" | "FAIL";

export interface Check {
  check_type: string;
  code_reference: string;
  demand_value: number;
  capacity_limit: number;
  dc_ratio: number;
  status: Status;
  formula_breakdown: string;
}

export interface StoryResult {
  story_name: string;
  elevation_in: number;
  height_in: number;
  status: Status;
  max_dc_ratio: number;
  deformations: {
    max_drift_x_in: number;
    avg_drift_x_in: number;
    max_drift_y_in: number;
    avg_drift_y_in: number;
  };
  checks: Check[];
}

export interface CodeCheckResult {
  summary: {
    building_name: string;
    total_stories: number;
    overall_status: Status;
    total_violations: number;
    total_warnings?: number;
    max_dc_ratio: number;
  };
  story_results: StoryResult[];
  project_info?: Record<string, unknown>;
}

/** Form state for the project settings; numbers stay strings until submit. */
export interface ProjectForm {
  building_name: string;
  risk_category: "I" | "II" | "III" | "IV";
  seismic_design_category: "B" | "C" | "D" | "E" | "F";
  structure_type: string;
  diaphragm: "rigid" | "semirigid" | "flexible";
  cd: string;
  ie: string;
  drift_is_amplified: boolean;
  moment_frame_rho: string;
  length_unit: string;
  force_unit: string;
  project_number: string;
  company: string;
  engineer: string;
  checked_by: string;
}

export const STATUS_COLOR: Record<Status, string> = {
  PASS: "#2e7d54",
  WARNING: "#b87a00",
  FAIL: "#c2261d",
};

export const STATUS_LABEL: Record<Status, string> = {
  PASS: "Pass",
  WARNING: "Irregular",
  FAIL: "Fail",
};
