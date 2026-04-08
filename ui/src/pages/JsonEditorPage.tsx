import { useEffect, useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { api } from "../api/client";
import type { WorkflowDetail, TemplateSummary, ValidationResult } from "../types/workflow";

export default function JsonEditorPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const [json, setJson] = useState("");
  const [validation, setValidation] = useState<ValidationResult | null>(null);
  const [status, setStatus] = useState("");
  const [loading, setLoading] = useState(true);

  const loadTemplate = async () => {
    if (!id) return;
    setLoading(true);
    try {
      const data = await api<WorkflowDetail>("GET", `/templates/${id}`);
      const { id: _id, ...exportData } = data;
      setJson(JSON.stringify(exportData, null, 2));
    } catch (e) {
      setStatus(String(e));
    }
    setLoading(false);
  };

  useEffect(() => { loadTemplate(); }, [id]);

  const save = async () => {
    if (!id) return;
    try {
      const data = JSON.parse(json);
      if (!data.states || data.states.length === 0) {
        setStatus("Cannot save: workflow has no states");
        return;
      }
      await api("PUT", `/templates/${id}`, data);
      setStatus("Saved");
    } catch (e) {
      setStatus(`Error: ${e}`);
    }
  };

  const validate = async () => {
    if (!id) return;
    try {
      const data = JSON.parse(json);
      if (data.states && data.states.length > 0) {
        await api("PUT", `/templates/${id}`, data);
      }
      const result = await api<ValidationResult>("POST", `/templates/${id}/validate`);
      setValidation(result);
      setStatus(result.valid ? "Valid" : "Validation failed");
    } catch (e) {
      setStatus(`Error: ${e}`);
    }
  };

  const importNew = async () => {
    try {
      const data = JSON.parse(json);
      const t = await api<TemplateSummary>("POST", "/templates", data);
      navigate(`/workflows/${t.id}`);
    } catch (e) {
      setStatus(`Error: ${e}`);
    }
  };

  if (loading) return <p className="text-xs text-slate-400 p-4">Loading...</p>;

  return (
    <div className="max-w-4xl mx-auto">
      <div className="flex items-center gap-2 mb-4">
        <button onClick={() => navigate(`/workflows/${id}`)} className="text-xs text-slate-500 hover:text-slate-800">&larr; Builder</button>
        <h1 className="text-sm font-semibold text-slate-800">JSON Editor</h1>
        <div className="flex-1" />
        <button onClick={save} className="px-3 py-1 text-xs border border-slate-300 rounded hover:bg-slate-100">Save</button>
        <button onClick={validate} className="px-3 py-1 text-xs border border-slate-300 rounded hover:bg-slate-100">Validate</button>
        <button onClick={importNew} className="px-3 py-1 text-xs bg-blue-500 text-white rounded hover:bg-blue-600">Import as New</button>
        <span className="text-[10px] text-slate-500">{status}</span>
      </div>

      <textarea
        value={json}
        onChange={(e) => setJson(e.target.value)}
        className="w-full h-[60vh] p-4 text-xs font-mono bg-white border border-slate-200 rounded-lg focus:border-blue-400 focus:outline-none resize-none"
        spellCheck={false}
      />

      {validation && (
        <div className="mt-4 bg-white rounded-lg border border-slate-200 p-4">
          <div className={`text-xs font-semibold mb-2 ${validation.valid ? "text-green-600" : "text-red-600"}`}>
            {validation.valid ? "All checks passed" : "Validation failed"}
          </div>
          <div className="space-y-1">
            {validation.checks.map((c) => (
              <div key={c.check} className="text-[10px] flex gap-2">
                <span className={c.passed ? "text-green-500" : "text-red-500"}>{c.passed ? "PASS" : "FAIL"}</span>
                <span className="text-slate-600">{c.check}</span>
                {c.details && <span className="text-slate-400">{c.details}</span>}
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
