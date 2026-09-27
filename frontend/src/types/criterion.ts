export interface Criterion {
  id: string;
  project_id: string;
  name: string;
  description: string;
  weight: number;
  scale_min: number;
  scale_max: number;
  enabled: boolean;
  created_at: string;
  updated_at: string;
}

export interface CriterionInput {
  name: string;
  description?: string;
  weight?: number;
  scale_min?: number;
  scale_max?: number;
  enabled?: boolean;
}
