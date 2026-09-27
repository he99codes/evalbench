export interface Project {
  id: string;
  name: string;
  description: string | null;
  created_at: string;
  updated_at: string;
}

export interface ProjectInput {
  name: string;
  description?: string | null;
}

export interface CriterionFailureStat {
  criterion_id: string;
  name: string;
  evaluated: number;
  failed: number;
  pass_rate: number;
}

export interface ProjectAnalytics {
  project_id: string;
  total_evaluations: number;
  completed_evaluations: number;
  preference: { A: number; B: number; TIE: number };
  average_score_a: number | null;
  average_score_b: number | null;
  average_quality: number | null;
  constraint_compliance_rate: number | null;
  mandatory_checks_total: number;
  mandatory_checks_satisfied: number;
  reward_mismatch_count: number;
  most_common_failing_criterion: CriterionFailureStat | null;
  criteria: CriterionFailureStat[];
  preference_over_time: { date: string; A: number; B: number; TIE: number }[];
}
