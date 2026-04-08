import { BrowserRouter, Routes, Route, Link } from "react-router-dom";
import WorkflowListPage from "./pages/WorkflowListPage";
import WorkflowBuilderPage from "./pages/WorkflowBuilderPage";
import EntityRuntimePage from "./pages/EntityRuntimePage";
import JsonEditorPage from "./pages/JsonEditorPage";

export default function App() {
  return (
    <BrowserRouter>
      <div className="min-h-screen bg-slate-50">
        <nav className="bg-white border-b border-slate-200 px-6 py-3 flex items-center gap-6">
          <Link to="/" className="text-blue-600 font-semibold text-sm tracking-wide">
            SCSM Engine
          </Link>
          <Link to="/" className="text-slate-500 text-xs hover:text-slate-800">
            Workflows
          </Link>
        </nav>
        <main className="p-6">
          <Routes>
            <Route path="/" element={<WorkflowListPage />} />
            <Route path="/workflows/:id" element={<WorkflowBuilderPage />} />
            <Route path="/workflows/:id/run" element={<EntityRuntimePage />} />
            <Route path="/workflows/:id/json" element={<JsonEditorPage />} />
          </Routes>
        </main>
      </div>
    </BrowserRouter>
  );
}
