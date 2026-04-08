export interface CurrentState {
  state_id: string | null;
  display_label: string | null;
}

export interface AvailableTransition {
  transition_id: string;
  display_label: string;
  target_state: string;
}

export interface AuditEntry {
  timestamp: string;
  from_state: string | null;
  to_state: string;
  transition_id: string | null;
  task_result: string | null;
}

export interface StartWorkflowResponse {
  workflow_id: string;
  template_id: string;
  current_state: CurrentState;
  available_transitions: AvailableTransition[];
}

