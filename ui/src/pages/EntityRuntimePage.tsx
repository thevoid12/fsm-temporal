import { useEffect, useState, useRef, useCallback } from "react";
import { useParams, useNavigate } from "react-router-dom";
import {
  ReactFlow,
  Background,
  Controls,
  useNodesState,
  useEdgesState,
  MarkerType,
  type Node,
  type Edge,
} from "@xyflow/react";
import { api } from "../api/client";
import type { WorkflowDetail, UiMetadata } from "../types/workflow";
import type { CurrentState, AvailableTransition, AuditEntry, StartWorkflowResponse } from "../types/entity";
import StateNode from "../components/StateNode";

const nodeTypes = { stateNode: StateNode };

export default function EntityRuntimePage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const [workflow, setWorkflow] = useState<WorkflowDetail | null>(null);
  const [workflowId, setWorkflowId] = useState<string | null>(null);
  const [currentState, setCurrentState] = useState<CurrentState | null>(null);
  const [available, setAvailable] = useState<AvailableTransition[]>([]);
  const [auditTrail, setAuditTrail] = useState<AuditEntry[]>([]);
  const [nodes, setNodes, onNodesChange] = useNodesState<Node>([]);
  const [edges, setEdges] = useEdgesState<Edge>([]);
  const [status, setStatus] = useState("");
  const [polling, setPolling] = useState(false);
  const [uiMeta, setUiMeta] = useState<UiMetadata>({});
  const intervalRef = useRef<number | null>(null);
  const expectedStateRef = useRef<string | null>(null);

  const loadTemplate = async () => {
    if (!id) return;
    const [wf, meta] = await Promise.all([
      api<WorkflowDetail>("GET", `/templates/${id}`),
      api<UiMetadata>("GET", `/templates/${id}/ui-metadata`),
    ]);
    setWorkflow(wf);
    setUiMeta(meta);
    buildCanvas(wf, meta, null);
  };

  useEffect(() => { loadTemplate(); }, [id]);

  useEffect(() => {
    return () => { if (intervalRef.current) clearInterval(intervalRef.current); };
  }, []);

  const buildCanvas = useCallback((wf: WorkflowDetail, meta: UiMetadata, activeStateId: string | null) => {
    const newNodes: Node[] = wf.states.map((s, i) => {
      let x = 200 + (i % 3) * 250;
      let y = 100 + Math.floor(i / 3) * 180;
      const pos = meta[s.unique_identifier];
      if (pos) { x = pos.x; y = pos.y; }
      const isActive = s.unique_identifier === activeStateId;
      return {
        id: s.unique_identifier,
        type: "stateNode",
        position: { x, y },
        data: {
          unique_identifier: s.unique_identifier,
          display_label: s.display_label,
          description: s.description,
          is_start: !!s.is_start,
          is_end: !!s.is_end,
          task_callback_url: s.task_callback_url,
        },
        className: isActive ? "ring-3 ring-blue-500 ring-offset-2 rounded-lg" : "",
      };
    });

    const newEdges = wf.transitions.map((t) => ({
      id: t.unique_identifier,
      source: t.source_state,
      target: t.target_state,
      label: t.display_label || t.unique_identifier,
      markerEnd: { type: MarkerType.ArrowClosed, width: 15, height: 15 },
      style: { strokeWidth: 1.5 },
    }));

    setNodes(newNodes);
    setEdges(newEdges);
  }, [setNodes, setEdges]);


  const stopPolling = useCallback(() => {
    if (intervalRef.current) clearInterval(intervalRef.current);
    intervalRef.current = null;
    setPolling(false);
  }, []);

  const pollUntilStateChanges = useCallback((wfId: string, fromStateId: string) => {
    if (intervalRef.current) clearInterval(intervalRef.current);
    setPolling(true);
    expectedStateRef.current = fromStateId;
    setAvailable([]);

    intervalRef.current = window.setInterval(async () => {
      try {
        const state = await api<CurrentState>("GET", `/workflows/${wfId}/state`);
        const transitions = await api<AvailableTransition[]>("GET", `/workflows/${wfId}/transitions`);
        const audit = await api<AuditEntry[]>("GET", `/workflows/${wfId}/audit`);

        setCurrentState(state);
        setAuditTrail(audit);
        if (workflow) buildCanvas(workflow, uiMeta, state.state_id);

        // State has changed from what we started with -- transition processed
        if (state.state_id !== expectedStateRef.current) {
          setAvailable(transitions);
          setStatus("Running");
          stopPolling();

          // Check end state
          if (workflow) {
            const endState = workflow.states.find(
              (s) => s.unique_identifier === state.state_id && s.is_end
            );
            if (endState) setStatus("Completed");
          }
        }
      } catch { /* ignore polling errors */ }
    }, 2000);
  }, [workflow, buildCanvas, stopPolling]);

  const startWorkflow = async () => {
    if (!id) return;
    try {
      setStatus("Starting...");
      const result = await api<StartWorkflowResponse>("POST", "/workflows", { template_id: id });
      setWorkflowId(result.workflow_id);
      setCurrentState(result.current_state);
      setAvailable(result.available_transitions);
      setStatus("Running");

      if (workflow) buildCanvas(workflow, uiMeta, result.current_state.state_id);

      const audit = await api<AuditEntry[]>("GET", `/workflows/${result.workflow_id}/audit`);
      setAuditTrail(audit);

      // Check end state
      if (workflow) {
        const endState = workflow.states.find(
          (s) => s.unique_identifier === result.current_state.state_id && s.is_end
        );
        if (endState) {
          setStatus("Completed");
          return;
        }
      }
    } catch (e) {
      setStatus(String(e));
    }
  };

  const triggerTransition = async (transitionId: string) => {
    if (!workflowId || !currentState?.state_id) return;
    try {
      setStatus("Transitioning...");
      const beforeStateId = currentState.state_id;

      // Just send the signal -- don't trust the immediate response for state
      await api("POST", `/workflows/${workflowId}/transition`, {
        transition_id: transitionId,
      });

      // Poll until we see the state actually change
      pollUntilStateChanges(workflowId, beforeStateId);
    } catch (e) {
      setStatus(String(e));
    }
  };

  const currentStateName = () => currentState?.display_label || currentState?.state_id || "---";

  return (
    <div className="flex gap-4 h-[calc(100vh-100px)]">
      <div className="flex-1 bg-white rounded-lg border border-slate-200 overflow-hidden">
        <div className="px-4 py-2 border-b border-slate-200 bg-slate-50 flex items-center gap-2">
          <button onClick={() => navigate(`/workflows/${id}`)} className="text-[10px] text-slate-500 hover:text-slate-800">&larr; Builder</button>
          <span className="text-xs font-semibold text-slate-700">{workflow?.name}</span>
          {currentState && (
            <span className="px-2 py-0.5 text-[10px] bg-blue-500 text-white rounded">{currentStateName()}</span>
          )}
          {polling && <span className="text-[10px] text-yellow-600 animate-pulse">task running...</span>}
          <div className="flex-1" />
          <span className="text-[10px] text-slate-500 max-w-[200px] truncate">{status}</span>
        </div>
        <ReactFlow nodes={nodes} edges={edges} onNodesChange={onNodesChange} nodeTypes={nodeTypes}
          fitView nodesDraggable={false} nodesConnectable={false} className="bg-slate-50">
          <Background gap={20} size={1} color="#e2e8f0" />
          <Controls />
        </ReactFlow>
      </div>

      <div className="w-80 flex flex-col gap-3">
        {/* Start / State */}
        <div className="bg-white rounded-lg border border-slate-200 p-4">
          {!workflowId ? (
            <>
              <p className="text-[10px] text-slate-400 mb-3">Start a new workflow instance.</p>
              <button onClick={startWorkflow} className="w-full px-3 py-2 text-xs bg-blue-500 text-white rounded-md hover:bg-blue-600">
                Start Workflow
              </button>
            </>
          ) : (
            <div className="space-y-2">
              <div className="flex justify-between items-center">
                <span className="text-xs font-semibold text-slate-700">{currentStateName()}</span>
                <span className="px-1.5 py-0.5 text-[10px] rounded bg-blue-100 text-blue-700">
                  {workflowId.slice(0, 20)}...
                </span>
              </div>
              {polling && (
                <p className="text-[10px] text-yellow-600">Exit task executing... waiting for state change.</p>
              )}
            </div>
          )}
        </div>

        {/* Transitions */}
        {workflowId && available.length > 0 && !polling && (
          <div className="bg-white rounded-lg border border-slate-200 p-4">
            <h3 className="text-xs font-semibold text-slate-700 mb-2">Next Steps</h3>
            <div className="space-y-1">
              {available.map((t) => (
                <button key={t.transition_id} onClick={() => triggerTransition(t.transition_id)}
                  className="w-full px-3 py-2 text-xs text-left border border-slate-200 rounded hover:bg-blue-50 hover:border-blue-300">
                  {t.display_label || t.transition_id}
                </button>
              ))}
            </div>
          </div>
        )}

        {/* Audit Trail */}
        <div className="bg-white rounded-lg border border-slate-200 p-4 flex-1 overflow-auto">
          <h3 className="text-xs font-semibold text-slate-700 mb-2">Audit Trail</h3>
          {auditTrail.length === 0 ? (
            <p className="text-[10px] text-slate-400">Start a workflow to see activity.</p>
          ) : (
            <div className="space-y-1">
              {[...auditTrail].reverse().map((entry, i) => (
                <div key={i} className="text-[10px] font-mono text-slate-600 leading-relaxed border-b border-slate-100 pb-1">
                  <span className="text-slate-300">{entry.timestamp.slice(11, 19)} </span>
                  {entry.from_state ? (
                    <span className="text-blue-600">
                      {entry.from_state} &rarr; {entry.to_state}
                      {entry.transition_id && <span className="text-slate-400"> ({entry.transition_id})</span>}
                    </span>
                  ) : (
                    <span className="text-green-600">Entered {entry.to_state}</span>
                  )}
                  {entry.task_result && (
                    <div className="text-slate-400 ml-16 truncate">task: {entry.task_result}</div>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
