import { useCallback, useEffect, useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import {
  ReactFlow,
  Background,
  Controls,
  addEdge,
  useNodesState,
  useEdgesState,
  type Connection,
  type Node,
  type Edge,
  MarkerType,
} from "@xyflow/react";
import { api } from "../api/client";
import type { WorkflowDetail, WorkflowImport, ValidationResult, UiMetadata } from "../types/workflow";
import StateNode, { type StateNodeData } from "../components/StateNode";
import ConfigPanel from "../components/ConfigPanel";

const nodeTypes = { stateNode: StateNode };

export default function WorkflowBuilderPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const [workflow, setWorkflow] = useState<WorkflowDetail | null>(null);
  const [nodes, setNodes, onNodesChange] = useNodesState<Node>([]);
  const [edges, setEdges, onEdgesChange] = useEdgesState<Edge>([]);
  const [selectedNode, setSelectedNode] = useState<Node | null>(null);
  const [selectedEdge, setSelectedEdge] = useState<Edge | null>(null);
  const [validation, setValidation] = useState<ValidationResult | null>(null);
  const [status, setStatus] = useState("");

  const load = useCallback(async () => {
    if (!id) return;
    try {
      const [wf, meta] = await Promise.all([
        api<WorkflowDetail>("GET", `/templates/${id}`),
        api<UiMetadata>("GET", `/templates/${id}/ui-metadata`),
      ]);
      setWorkflow(wf);
      buildCanvasFromWorkflow(wf, meta);
      setStatus("");
    } catch (e) {
      setStatus(String(e));
    }
  }, [id]);

  useEffect(() => { load(); }, [load]);

  const buildCanvasFromWorkflow = (wf: WorkflowDetail, meta: UiMetadata) => {
    const newNodes: Node[] = wf.states.map((s, i) => {
      let x = 200 + (i % 3) * 250;
      let y = 100 + Math.floor(i / 3) * 180;
      const pos = meta[s.unique_identifier];
      if (pos) { x = pos.x; y = pos.y; }
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
          task_timeout_minutes: s.task_timeout_minutes,
          max_retries: s.max_retries,
          retry_interval_seconds: s.retry_interval_seconds,
        } satisfies StateNodeData,
      };
    });

    const newEdges: Edge[] = wf.transitions.map((t) => ({
      id: t.unique_identifier,
      source: t.source_state,
      target: t.target_state,
      label: t.display_label || t.unique_identifier,
      data: { display_label: t.display_label || "", unique_identifier: t.unique_identifier },
      markerEnd: { type: MarkerType.ArrowClosed, width: 15, height: 15 },
      style: { strokeWidth: 1.5 },
    }));

    setNodes(newNodes);
    setEdges(newEdges);
  };

  const onConnect = useCallback((conn: Connection) => {
    const edgeId = `${conn.source}_to_${conn.target}`;
    setEdges((eds) =>
      addEdge(
        {
          ...conn,
          id: edgeId,
          label: edgeId,
          data: { unique_identifier: edgeId, display_label: "" },
          markerEnd: { type: MarkerType.ArrowClosed, width: 15, height: 15 },
        },
        eds
      )
    );
  }, [setEdges]);

  const addState = () => {
    const num = nodes.length + 1;
    const uid = `state-${num}`;
    setNodes((nds) => [
      ...nds,
      {
        id: uid,
        type: "stateNode",
        position: { x: 200 + Math.random() * 200, y: 200 + Math.random() * 200 },
        data: {
          unique_identifier: uid,
          display_label: `State ${num}`,
          is_start: false,
          is_end: false,
        } satisfies StateNodeData,
      },
    ]);
  };

  const buildImportJson = (): WorkflowImport => ({
    name: workflow?.name || "Untitled",
    description: workflow?.description,
    states: nodes.map((n) => {
      const d = n.data as StateNodeData;
      return {
        unique_identifier: d.unique_identifier,
        display_label: d.display_label,
        description: d.description,
        is_start: !!d.is_start,
        is_end: !!d.is_end,
        task_callback_url: d.task_callback_url || undefined,
        task_timeout_minutes: d.task_timeout_minutes ?? 5,
        max_retries: d.max_retries ?? 0,
        retry_interval_seconds: d.retry_interval_seconds ?? 60,
      };
    }),
    transitions: edges.map((e) => ({
      unique_identifier: e.id,
      display_label: (e.data as Record<string, string>)?.display_label || undefined,
      source_state: e.source,
      target_state: e.target,
    })),
  });

  const buildUiMetadata = (): UiMetadata => {
    const meta: UiMetadata = {};
    for (const n of nodes) {
      const d = n.data as StateNodeData;
      meta[d.unique_identifier] = { x: Math.round(n.position.x), y: Math.round(n.position.y) };
    }
    return meta;
  };

  const autoSave = async () => {
    if (!id || nodes.length === 0) return;
    try {
      await Promise.all([
        api("PUT", `/templates/${id}`, buildImportJson()),
        api("PUT", `/templates/${id}/ui-metadata`, buildUiMetadata()),
      ]);
    } catch { /* silent auto-save */ }
  };

  const save = async () => {
    if (!id || nodes.length === 0) return;
    try {
      setStatus("Saving...");
      await Promise.all([
        api("PUT", `/templates/${id}`, buildImportJson()),
        api("PUT", `/templates/${id}/ui-metadata`, buildUiMetadata()),
      ]);
      setStatus("Saved");
      await load();
    } catch (e) {
      setStatus(`Save failed: ${e}`);
    }
  };

  const navigateTo = async (path: string) => {
    await autoSave();
    navigate(path);
  };

  const validate = async () => {
    if (!id) return;
    if (nodes.length === 0) {
      setStatus("Add states first");
      return;
    }
    try {
      await Promise.all([
        api("PUT", `/templates/${id}`, buildImportJson()),
        api("PUT", `/templates/${id}/ui-metadata`, buildUiMetadata()),
      ]);
      const result = await api<ValidationResult>("POST", `/templates/${id}/validate`);
      setValidation(result);
      setStatus(result.valid ? "Valid" : "Validation failed");
    } catch (e) {
      setStatus(`Validation error: ${e}`);
    }
  };

  const exportJson = () => {
    const json = JSON.stringify(buildImportJson(), null, 2);
    navigator.clipboard.writeText(json);
    setStatus("JSON copied to clipboard");
  };

  const onNodeClick = (_: React.MouseEvent, node: Node) => { setSelectedNode(node); setSelectedEdge(null); };
  const onEdgeClick = (_: React.MouseEvent, edge: Edge) => { setSelectedEdge(edge); setSelectedNode(null); };
  const onPaneClick = () => { setSelectedNode(null); setSelectedEdge(null); };

  const updateNodeData = (nodeId: string, data: Partial<StateNodeData>) => {
    setNodes((nds) => nds.map((n) => n.id === nodeId ? { ...n, data: { ...n.data, ...data } } : n));
    if (selectedNode?.id === nodeId) setSelectedNode((prev) => prev ? { ...prev, data: { ...prev.data, ...data } } : null);
  };

  const updateEdgeData = (edgeId: string, data: { unique_identifier?: string; display_label?: string }) => {
    setEdges((eds) => eds.map((e) => {
      if (e.id !== edgeId) return e;
      const newId = data.unique_identifier || e.id;
      return { ...e, id: newId, label: data.display_label || newId, data: { ...e.data, ...data } };
    }));
  };

  const deleteNode = (nodeId: string) => {
    setNodes((nds) => nds.filter((n) => n.id !== nodeId));
    setEdges((eds) => eds.filter((e) => e.source !== nodeId && e.target !== nodeId));
    setSelectedNode(null);
  };

  const deleteEdge = (edgeId: string) => {
    setEdges((eds) => eds.filter((e) => e.id !== edgeId));
    setSelectedEdge(null);
  };

  return (
    <div className="flex gap-4 h-[calc(100vh-100px)]">
      <div className="flex-1 bg-white rounded-lg border border-slate-200 overflow-hidden relative">
        <div className="flex items-center gap-2 px-4 py-2 border-b border-slate-200 bg-slate-50">
          <button onClick={() => navigateTo("/")} className="text-[10px] text-slate-500 hover:text-slate-800">&larr;</button>
          <span className="text-xs font-semibold text-slate-700">{workflow?.name || "Loading..."}</span>
          <div className="flex-1" />
          <button onClick={addState} className="px-2 py-1 text-[10px] bg-blue-500 text-white rounded hover:bg-blue-600">+ State</button>
          <button onClick={save} className="px-2 py-1 text-[10px] border border-slate-300 rounded hover:bg-slate-100">Save</button>
          <button onClick={validate} className="px-2 py-1 text-[10px] border border-slate-300 rounded hover:bg-slate-100">Validate</button>
          <button onClick={exportJson} className="px-2 py-1 text-[10px] border border-slate-300 rounded hover:bg-slate-100">Export</button>
          <button onClick={() => navigateTo(`/workflows/${id}/json`)} className="px-2 py-1 text-[10px] border border-slate-300 rounded hover:bg-slate-100">JSON</button>
          <button onClick={() => navigateTo(`/workflows/${id}/run`)} className="px-2 py-1 text-[10px] bg-blue-100 text-blue-700 rounded hover:bg-blue-200">Run</button>
          <span className="text-[10px] text-slate-500 max-w-[150px] truncate">{status}</span>
        </div>

        <ReactFlow
          nodes={nodes}
          edges={edges}
          onNodesChange={onNodesChange}
          onEdgesChange={onEdgesChange}
          onConnect={onConnect}
          onNodeClick={onNodeClick}
          onEdgeClick={onEdgeClick}
          onPaneClick={onPaneClick}
          nodeTypes={nodeTypes}
          fitView
          className="bg-slate-50"
        >
          <Background gap={20} size={1} color="#e2e8f0" />
          <Controls />
        </ReactFlow>

        {validation && (
          <div className="absolute bottom-4 left-4 bg-white rounded-lg border border-slate-200 p-3 shadow-lg max-w-md max-h-48 overflow-auto z-10">
            <div className="flex justify-between items-center mb-2">
              <span className={`text-xs font-semibold ${validation.valid ? "text-green-600" : "text-red-600"}`}>
                {validation.valid ? "All checks passed" : "Validation failed"}
              </span>
              <button onClick={() => setValidation(null)} className="text-[10px] text-slate-400 hover:text-slate-700">close</button>
            </div>
            {validation.checks.map((c) => (
              <div key={c.check} className="text-[10px] flex gap-2">
                <span className={c.passed ? "text-green-500" : "text-red-500"}>{c.passed ? "PASS" : "FAIL"}</span>
                <span className="text-slate-600">{c.check}</span>
                {c.details && <span className="text-red-400">{c.details}</span>}
              </div>
            ))}
          </div>
        )}
      </div>

      <div className="w-72 bg-white rounded-lg border border-slate-200 overflow-auto">
        <ConfigPanel
          selectedNode={selectedNode}
          selectedEdge={selectedEdge}
          onUpdateNode={updateNodeData}
          onUpdateEdge={updateEdgeData}
          onDeleteNode={deleteNode}
          onDeleteEdge={deleteEdge}
        />
      </div>
    </div>
  );
}
