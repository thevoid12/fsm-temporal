import type { Node, Edge } from "@xyflow/react";
import type { StateNodeData } from "./StateNode";

interface Props {
  selectedNode: Node | null;
  selectedEdge: Edge | null;
  onUpdateNode: (id: string, data: Partial<StateNodeData>) => void;
  onUpdateEdge: (id: string, data: { unique_identifier?: string; display_label?: string }) => void;
  onDeleteNode: (id: string) => void;
  onDeleteEdge: (id: string) => void;
}

export default function ConfigPanel({ selectedNode, selectedEdge, onUpdateNode, onUpdateEdge, onDeleteNode, onDeleteEdge }: Props) {
  if (!selectedNode && !selectedEdge) {
    return (
      <div className="p-4 text-xs text-slate-400">
        Select a state or transition to configure it.
      </div>
    );
  }

  if (selectedNode) {
    const d = selectedNode.data as StateNodeData;
    const update = (field: string, value: unknown) => onUpdateNode(selectedNode.id, { [field]: value });

    return (
      <div className="p-4 space-y-3">
        <div className="flex justify-between items-center">
          <h3 className="text-xs font-semibold text-slate-700">State Config</h3>
          <button onClick={() => onDeleteNode(selectedNode.id)} className="text-[10px] text-red-500 hover:text-red-700">Delete</button>
        </div>

        <Field label="Identifier" value={d.unique_identifier} onChange={(v) => update("unique_identifier", v)} />
        <Field label="Display Label" value={d.display_label} onChange={(v) => update("display_label", v)} />
        <Field label="Description" value={d.description || ""} onChange={(v) => update("description", v)} textarea />

        <div className="flex gap-4">
          <Checkbox label="Start" checked={d.is_start} onChange={(v) => update("is_start", v)} />
          <Checkbox label="End" checked={d.is_end} onChange={(v) => update("is_end", v)} />
        </div>

        <div className="border-t border-slate-200 pt-3 mt-3">
          <div className="text-[10px] text-slate-500 font-medium mb-2">Task Config (optional)</div>
          <Field label="Callback URL" value={d.task_callback_url || ""} onChange={(v) => update("task_callback_url", v || null)} />
          <NumberField label="Timeout (min)" value={d.task_timeout_minutes ?? 5} onChange={(v) => update("task_timeout_minutes", v)} />
          <NumberField label="Max Retries" value={d.max_retries ?? 0} onChange={(v) => update("max_retries", v)} />
          <NumberField label="Retry Interval (sec)" value={d.retry_interval_seconds ?? 60} onChange={(v) => update("retry_interval_seconds", v)} />
        </div>
      </div>
    );
  }

  if (selectedEdge) {
    return (
      <div className="p-4 space-y-3">
        <div className="flex justify-between items-center">
          <h3 className="text-xs font-semibold text-slate-700">Transition Config</h3>
          <button onClick={() => onDeleteEdge(selectedEdge.id)} className="text-[10px] text-red-500 hover:text-red-700">Delete</button>
        </div>
        <Field label="Identifier" value={selectedEdge.id} onChange={(v) => onUpdateEdge(selectedEdge.id, { unique_identifier: v })} />
        <Field label="Display Label" value={(selectedEdge.data as Record<string, string>)?.display_label || ""} onChange={(v) => onUpdateEdge(selectedEdge.id, { display_label: v })} />
        <div className="text-[10px] text-slate-400">
          {selectedEdge.source} &rarr; {selectedEdge.target}
        </div>
      </div>
    );
  }

  return null;
}

function Field({ label, value, onChange, textarea }: { label: string; value: string; onChange: (v: string) => void; textarea?: boolean }) {
  const cls = "w-full px-2 py-1 text-xs border border-slate-200 rounded focus:border-blue-400 focus:outline-none";
  return (
    <div>
      <label className="text-[10px] text-slate-500">{label}</label>
      {textarea ? (
        <textarea value={value} onChange={(e) => onChange(e.target.value)} className={cls} rows={2} />
      ) : (
        <input value={value} onChange={(e) => onChange(e.target.value)} className={cls} />
      )}
    </div>
  );
}

function NumberField({ label, value, onChange }: { label: string; value: number; onChange: (v: number) => void }) {
  return (
    <div>
      <label className="text-[10px] text-slate-500">{label}</label>
      <input type="number" value={value} onChange={(e) => onChange(Number(e.target.value))} className="w-full px-2 py-1 text-xs border border-slate-200 rounded focus:border-blue-400 focus:outline-none" />
    </div>
  );
}

function Checkbox({ label, checked, onChange }: { label: string; checked: boolean; onChange: (v: boolean) => void }) {
  return (
    <label className="flex items-center gap-1 text-[10px] text-slate-600 cursor-pointer">
      <input type="checkbox" checked={checked} onChange={(e) => onChange(e.target.checked)} className="rounded" />
      {label}
    </label>
  );
}
