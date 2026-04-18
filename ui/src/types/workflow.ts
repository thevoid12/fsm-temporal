export interface TemplateSummary {
  id: string;
  name: string;
  description: string;
}

export interface StateDefinition {
  unique_identifier: string;
  display_label: string;
  description?: string | null;
  is_start?: boolean;
  is_end?: boolean;
  task_callback_url?: string | null;
  task_http_method?: string;
  task_timeout_minutes?: number;
  max_retries?: number;
  retry_interval_seconds?: number;
}

export type UiMetadata = Record<string, { x: number; y: number }>;

export interface TransitionCondition {
  field: string;
  operator: string;
  value?: string;
}

export const CONDITION_OPERATORS = [
  "equals",
  "not_equals",
  "contains",
  "exists",
  "not_exists",
  "status_code_range",
] as const;

export interface TransitionDefinition {
  unique_identifier: string;
  display_label?: string;
  source_state: string;
  target_state: string;
  auto_on_success?: boolean;
  condition?: TransitionCondition | null;
}

export interface WorkflowDetail {
  id: string;
  name: string;
  description?: string;
  states: StateDefinition[];
  transitions: TransitionDefinition[];
}

export interface WorkflowImport {
  name: string;
  description?: string | null;
  states: StateDefinition[];
  transitions: TransitionDefinition[];
}

export interface ValidationCheck {
  check: string;
  passed: boolean;
  details: string | null;
}

export interface ValidationResult {
  valid: boolean;
  checks: ValidationCheck[];
}
