import { Handle, Position, type NodeProps } from "@xyflow/react";

export interface StateNodeData {
  unique_identifier: string;
  display_label: string;
  description?: string | null;
  is_start: boolean;
  is_end: boolean;
  task_callback_url?: string | null;
  task_timeout_minutes?: number;
  max_retries?: number;
  retry_interval_seconds?: number;
  [key: string]: unknown;
}

const handleStyle = { background: "#94a3b8", width: 10, height: 10 };

export default function StateNode({ data, selected }: NodeProps) {
  const d = data as StateNodeData;
  const borderColor = d.is_start ? "border-green-400" : d.is_end ? "border-red-400" : "border-blue-300";
  const bgColor = selected ? "bg-blue-50" : "bg-white";

  return (
    <div className={`px-4 py-3 rounded-lg border-2 ${borderColor} ${bgColor} shadow-sm min-w-[140px] relative`}>
      <Handle type="target" position={Position.Top} style={handleStyle} />
      <Handle type="source" position={Position.Bottom} style={handleStyle} />

      <div className="text-xs font-semibold text-slate-700">{d.display_label}</div>
      <div className="text-[10px] text-slate-400 mt-0.5">{d.unique_identifier}</div>
      {d.task_callback_url && (
        <div className="text-[10px] text-blue-500 mt-1 flex items-center gap-1">
          <span>&#9889;</span> Task
        </div>
      )}
      {d.is_start && <div className="text-[10px] text-green-600 font-medium">START</div>}
      {d.is_end && <div className="text-[10px] text-red-600 font-medium">END</div>}
    </div>
  );
}
