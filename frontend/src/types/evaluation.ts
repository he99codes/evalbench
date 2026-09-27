import type { Criterion } from "./criterion.ts";

export type EvaluationStatus = "DRAFT" | "READY" | "RUNNING" | "COMPLETED" | "FAILED";
export type PreferredResponse = "A" | "B" | "TIE";
export type ResponseLabel = "A" | "B";
export type RequirementType = "REQUEST" | "CONSTRAINT" | "FORMAT" | "AUDIENCE" | "LENGTH" | "OTHER";

export interface EvaluationSummary {
  id: string;
  project_id: string;
  title: string;
  status: EvaluationStatus;
  preferred_response: PreferredResponse | null;
  overall_score_a: number | null;
  overall_score_b: number | null;
  created_at: string;
  updated_at: string;
}

export interface EvaluationCriterion {
  id: string;
  criterion_id: string;
  weight: number;
  criterion: Criterion;
}

export interface PromptRequirement {
  id: string;
  evaluation_id: string;
  type: RequirementType;
  description: string;
  mandatory: boolean;
  source_text: string | null;
  created_at: string;
}

export interface Evaluation extends EvaluationSummary {
  prompt: string;
  response_a: string;
  response_b: string;
  final_reasoning: string | null;
  improvement: string | null;
  criteria: EvaluationCriterion[];
  requirements: PromptRequirement[];
}

export interface EvaluationCriterionInput {
  criterion_id: string;
  weight?: number;
}

export interface EvaluationCreateInput {
  project_id: string;
  title: string;
  prompt: string;
  response_a: string;
  response_b: string;
  criteria: EvaluationCriterionInput[];
}

export type EvaluationUpdateInput = Partial<Omit<EvaluationCreateInput, "project_id">>;

export interface EvaluationFilters {
  project_id?: string;
  status?: EvaluationStatus;
}

export interface AnalyzePromptResponse {
  evaluation_id: string;
  status: EvaluationStatus;
  requirements: PromptRequirement[];
  ambiguities: string[];
}

// --- Runs ------------------------------------------------------------------

export type RunStatus = "PENDING" | "RUNNING" | "COMPLETED" | "FAILED";

export interface RunProgress {
  stage: string | null;
  completed_steps: number;
  total_steps: number;
}

export interface RunError {
  stage: string | null;
  type: string;
  message: string;
}

export interface EvaluationRun {
  id: string;
  evaluation_id: string;
  evaluator_model: string;
  provider: string;
  rubric_version: string;
  prompt_version: string;
  status: RunStatus;
  candidate_order: string | null;
  latency_ms: number | null;
  input_tokens: number | null;
  output_tokens: number | null;
  created_at: string;
  completed_at: string | null;
  progress: RunProgress;
  error: RunError | null;
  outcome: RunOutcome | null;
}

// --- Report (every value is computed by the backend) -------------------------

export interface EvidenceItem {
  id: string;
  evaluation_result_id: string;
  response: ResponseLabel;
  quote: string;
  location: string | null;
  supports: string;
  created_at: string;
}

export interface RequirementCheck {
  satisfied: boolean;
  explanation: string;
  quote: string | null;
}

export interface ReportRequirement {
  id: string;
  ref: string;
  type: RequirementType;
  description: string;
  mandatory: boolean;
  source_text: string | null;
  compliance_a: RequirementCheck | null;
  compliance_b: RequirementCheck | null;
}

export interface CriterionSide {
  result_id: string;
  score: number;
  normalized_score: number;
  passed: boolean;
  reasoning: string;
  evidence: EvidenceItem[];
}

export interface ReportCriterionRow {
  criterion_id: string;
  name: string;
  description: string;
  weight: number;
  weight_share: number;
  scale_min: number;
  scale_max: number;
  a: CriterionSide;
  b: CriterionSide;
  leader: PreferredResponse;
  decisive: boolean;
}

export interface ResponseSummary {
  label: ResponseLabel;
  overall_score: number;
  criteria_passed: number;
  criteria_total: number;
  mandatory_satisfied: number;
  mandatory_total: number;
  compliance_rate: number | null;
}

export interface ResponseMismatch {
  overall_score: number;
  compliance_rate: number | null;
  gap: number | null;
  flagged: boolean;
}

export interface RewardMismatch {
  flagged: boolean;
  threshold: number;
  a: ResponseMismatch;
  b: ResponseMismatch;
  preferred_less_compliant: boolean;
  score_leader_less_compliant: boolean;
  reasons: string[];
}

export interface EvidenceEntry {
  criterion_id: string;
  criterion_name: string;
  score: number;
  scale_max: number;
  passed: boolean;
  quote: string;
  supports: string;
  location: string | null;
}

export interface Report {
  evaluation: {
    id: string;
    project_id: string;
    title: string;
    status: EvaluationStatus;
    prompt: string;
    response_a: string;
    response_b: string;
    created_at: string;
  };
  run: EvaluationRun;
  requirements: ReportRequirement[];
  ambiguities: string[];
  criteria: ReportCriterionRow[];
  summary_a: ResponseSummary;
  summary_b: ResponseSummary;
  preference: {
    preferred_response: PreferredResponse;
    reasoning: string;
    decisive_criteria: string[];
    candidate_order: string | null;
    score_leader: PreferredResponse;
    agrees_with_scores: boolean;
  };
  improvement: { target_response: ResponseLabel; improvement: string };
  reward_mismatch: RewardMismatch;
  evidence_a: EvidenceEntry[];
  evidence_b: EvidenceEntry[];
}

export interface RunOutcome {
  overall_score_a: number;
  overall_score_b: number;
  preferred_response: PreferredResponse;
}

// Declaration merging: every run from the API carries its computed outcome (null unless COMPLETED).
export interface EvaluationRun {
  outcome: RunOutcome | null;
}

export interface AgreementRunInfo {
  run_id: string;
  run_number: number;
  provider: string;
  evaluator_model: string;
  rubric_version: string;
  prompt_version: string;
  candidate_order: string | null;
  preferred_response: PreferredResponse;
  overall_score_a: number;
  overall_score_b: number;
}

export interface CriterionAgreement {
  criterion_id: string;
  name: string;
  response: ResponseLabel;
  score_1: number;
  score_2: number;
  scale_min: number;
  scale_max: number;
  normalized_difference: number;
  passed_1: boolean;
  passed_2: boolean;
  pass_agrees: boolean;
}

export interface Agreement {
  evaluation_id: string;
  run_1: AgreementRunInfo;
  run_2: AgreementRunInfo;
  same_rubric: boolean;
  same_prompt_version: boolean;
  same_evaluator: boolean;
  preference_agrees: boolean;
  criteria: CriterionAgreement[];
  criteria_only_in_one_run: string[];
  pass_fail_agreement: number | null;
  mean_abs_score_difference: number | null;
  overall_score_difference_a: number;
  overall_score_difference_b: number;
  overall_agreement: number;
}

export interface RunOutcome {
  overall_score_a: number;
  overall_score_b: number;
  preferred_response: PreferredResponse;
}

export interface AgreementRunInfo {
  run_id: string;
  run_number: number;
  provider: string;
  evaluator_model: string;
  rubric_version: string;
  prompt_version: string;
  candidate_order: string | null;
  preferred_response: PreferredResponse;
  overall_score_a: number;
  overall_score_b: number;
}

export interface CriterionAgreement {
  criterion_id: string;
  name: string;
  response: ResponseLabel;
  score_1: number;
  score_2: number;
  scale_min: number;
  scale_max: number;
  normalized_difference: number;
  passed_1: boolean;
  passed_2: boolean;
  pass_agrees: boolean;
}

export interface Agreement {
  evaluation_id: string;
  run_1: AgreementRunInfo;
  run_2: AgreementRunInfo;
  same_rubric: boolean;
  same_prompt_version: boolean;
  same_evaluator: boolean;
  preference_agrees: boolean;
  criteria: CriterionAgreement[];
  criteria_only_in_one_run: string[];
  pass_fail_agreement: number | null;
  mean_abs_score_difference: number | null;
  overall_score_difference_a: number;
  overall_score_difference_b: number;
  overall_agreement: number;
}
