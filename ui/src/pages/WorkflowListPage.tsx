import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../api/client";
import type { TemplateSummary } from "../types/workflow";

export default function WorkflowListPage() {
  const [templates, setTemplates] = useState<TemplateSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [showCreate, setShowCreate] = useState(false);
  const [newName, setNewName] = useState("");
  const navigate = useNavigate();

  const load = async () => {
    setLoading(true);
    try {
      const data = await api<TemplateSummary[]>("GET", "/templates");
      setTemplates(data);
    } catch (e) {
      console.error(e);
    }
    setLoading(false);
  };

  useEffect(() => { load(); }, []);

  const createTemplate = async () => {
    if (!newName.trim()) return;
    try {
      const t = await api<TemplateSummary>("POST", "/templates", { name: newName.trim() });
      setShowCreate(false);
      setNewName("");
      navigate(`/workflows/${t.id}`);
    } catch (e) {
      alert(String(e));
    }
  };

  const importJson = async () => {
    const input = prompt("Paste workflow JSON:");
    if (!input) return;
    try {
      const t = await api<TemplateSummary>("POST", "/templates", JSON.parse(input));
      navigate(`/workflows/${t.id}`);
    } catch (e) {
      alert(String(e));
    }
  };

  return (
    <div className="max-w-4xl mx-auto">
      <div className="flex justify-between items-center mb-6">
        <h1 className="text-lg font-semibold text-slate-800">Workflows</h1>
        <div className="flex gap-2">
          <button
            onClick={importJson}
            className="px-3 py-1.5 text-xs border border-slate-300 rounded-md hover:bg-slate-100"
          >
            Import JSON
          </button>
          <button
            onClick={() => setShowCreate(true)}
            className="px-3 py-1.5 text-xs bg-blue-500 text-white rounded-md hover:bg-blue-600"
          >
            + New Workflow
          </button>
        </div>
      </div>

      {showCreate && (
        <div className="mb-4 p-4 bg-white rounded-lg border border-slate-200 flex gap-2">
          <input
            value={newName}
            onChange={(e) => setNewName(e.target.value)}
            placeholder="Workflow name"
            className="flex-1 px-3 py-1.5 text-xs border border-slate-300 rounded-md"
            onKeyDown={(e) => e.key === "Enter" && createTemplate()}
            autoFocus
          />
          <button onClick={createTemplate} className="px-3 py-1.5 text-xs bg-blue-500 text-white rounded-md">
            Create
          </button>
          <button onClick={() => setShowCreate(false)} className="px-3 py-1.5 text-xs border border-slate-300 rounded-md">
            Cancel
          </button>
        </div>
      )}

      {loading ? (
        <p className="text-xs text-slate-400">Loading...</p>
      ) : templates.length === 0 ? (
        <p className="text-xs text-slate-400">No workflows yet. Create one or import JSON.</p>
      ) : (
        <div className="space-y-2">
          {templates.map((t) => (
            <div
              key={t.id}
              className="bg-white rounded-lg border border-slate-200 p-4 flex justify-between items-center hover:border-blue-300 cursor-pointer"
              onClick={() => navigate(`/workflows/${t.id}`)}
            >
              <div>
                <div className="text-sm font-medium text-slate-800">{t.name}</div>
                <div className="text-xs text-slate-400 mt-1">
                  {t.description || "No description"}
                </div>
              </div>
              <div className="flex gap-2">
                <button
                  onClick={(e) => { e.stopPropagation(); navigate(`/workflows/${t.id}/run`); }}
                  className="px-2 py-0.5 text-xs bg-blue-100 text-blue-700 rounded hover:bg-blue-200"
                >
                  Run
                </button>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
