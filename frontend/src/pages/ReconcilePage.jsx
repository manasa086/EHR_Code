import { useState, useEffect } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { reconcileMedication, recordDecision, getDecision } from "../services/api";
import { useSSE } from "../hooks/useSSE";
import ConfidenceBar from "../components/ConfidenceBar";

// Parses Claude's numbered reasoning (e.g. "1. TITLE: body") into structured cards.
// Falls back to a single plain-text block for simple rule-based results.
function parseReasoningPoints(text) {
  const pattern = /(\d+)\.\s+([A-Z][A-Z\s\/]+?):\s+/g;
  const matches = [...text.matchAll(pattern)];
  if (matches.length < 2) return null;

  return matches.map((match, idx) => {
    const start = match.index + match[0].length;
    const end = matches[idx + 1]?.index ?? text.length;
    return {
      num: match[1],
      title: match[2].trim(),
      body: text.slice(start, end).trim(),
    };
  });
}

function ReasoningBlock({ text }) {
  const points = parseReasoningPoints(text);

  if (!points) {
    return (
      <div>
        <p className="text-sm font-semibold text-gray-600 mb-2">Reasoning</p>
        <p className="text-sm text-gray-700 bg-gray-50 rounded-lg p-4 leading-relaxed">{text}</p>
      </div>
    );
  }

  return (
    <div>
      <p className="text-sm font-semibold text-gray-600 mb-2">Reasoning</p>
      <div className="space-y-2">
        {points.map((p) => (
          <div key={p.num} className="bg-gray-50 rounded-lg px-4 py-3 border-l-4 border-teal-300">
            <div className="flex items-center gap-2 mb-1">
              <span className="text-xs font-bold text-teal-600 bg-teal-100 rounded-full w-5 h-5 flex items-center justify-center flex-shrink-0">
                {p.num}
              </span>
              <p className="text-xs font-semibold text-gray-500 uppercase tracking-wide">{p.title}</p>
            </div>
            <p className="text-sm text-gray-700 leading-relaxed pl-7">{p.body}</p>
          </div>
        ))}
      </div>
    </div>
  );
}

const RELIABILITY_STYLE = {
  high:   "bg-green-100 text-green-700",
  medium: "bg-yellow-100 text-yellow-700",
  low:    "bg-red-100 text-red-700",
};

const SAFETY_STYLE = {
  PASSED:       "bg-green-100 text-green-800",
  NEEDS_REVIEW: "bg-yellow-100 text-yellow-800",
  FAILED:       "bg-red-100 text-red-800",
};

export default function ReconcilePage() {
  const location = useLocation();
  const navigate = useNavigate();
  const selectedCase = location.state?.case ?? null;

  const [result, setResult]       = useState(null);
  const [loading, setLoading]     = useState(false);
  const [error, setError]         = useState(null);
  const [decision, setDecision]   = useState(null);
  const [liveNotice, setLiveNotice] = useState(null); // SSE activity from other tabs/users

  // On case load: reset UI and restore any previously recorded decision from the server
  useEffect(() => {
    setResult(null);
    setDecision(null);
    setError(null);
    setLiveNotice(null);
    if (!selectedCase?.id) return;
    getDecision(selectedCase.id, "medication_reconciliation").then((entry) => {
      if (!entry) return;
      setDecision(entry.decision);
      if (entry.data) setResult(entry.data);
    });
  }, [selectedCase?.id]);

  // Live SSE — show a notice when another tab/user runs reconciliation on this case
  useSSE({
    reconciliation_done: ({ case_id, label }) => {
      if (case_id && case_id !== selectedCase?.id) return; // different case — ignore
      setLiveNotice(`Reconciliation just completed for "${label ?? case_id}" in another session.`);
      setTimeout(() => setLiveNotice(null), 6000);
    },
  });

  async function runReconciliation() {
    if (!selectedCase) return;
    setError(null);
    setResult(null);
    setDecision(null);
    setLoading(true);
    try {
      const payload = {
        // Core reconciliation fields
        patient_context: selectedCase.patient_context,
        sources:         selectedCase.sources,
        // Full case metadata — ensures cache key covers every field
        id:           selectedCase.id,
        label:        selectedCase.label,
        description:  selectedCase.description,
        demographics: selectedCase.demographics  ?? null,
        allergies:    selectedCase.allergies     ?? null,
        vital_signs:  selectedCase.vital_signs   ?? null,
        last_updated: selectedCase.last_updated  ?? null,
      };
      setResult(await reconcileMedication(payload));
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }

  async function handleDecision(dec) {
    setDecision(dec);
    try {
      await recordDecision({ type: "medication_reconciliation", case_id: selectedCase.id, decision: dec, data: result });
    } catch {
      // UI already updated — swallow silently
    }
  }

  if (!selectedCase) {
    return (
      <div className="max-w-3xl mx-auto py-24 px-4 text-center space-y-4">
        <p className="text-lg font-semibold text-gray-700">No case selected</p>
        <p className="text-sm text-gray-500">Select a case from the Cases page, then click "Medication Reconciliation".</p>
        <button
          onClick={() => navigate("/cases")}
          className="bg-teal-600 text-white px-6 py-2.5 rounded-xl font-semibold hover:bg-teal-700 transition-colors">
          Go to Cases
        </button>
      </div>
    );
  }

  return (
    <div className="max-w-3xl mx-auto py-8 px-4 space-y-5">
      <div>
        <button
          onClick={() => navigate("/cases")}
          className="text-xs text-teal-600 hover:text-teal-700 font-semibold mb-2 inline-block">
          ← Back to Cases
        </button>
        <h1 className="text-2xl font-bold text-gray-800 mb-1">Medication Reconciliation</h1>
        <p className="text-sm text-gray-500">
          Review conflicting records and run reconciliation for the selected patient.
        </p>
      </div>

      {/* SSE live notice */}
      {liveNotice && (
        <div className="flex items-center gap-2 bg-teal-50 border border-teal-200 rounded-xl px-4 py-3 text-sm text-teal-700">
          <span className="w-2 h-2 rounded-full bg-teal-400 animate-pulse flex-shrink-0" />
          {liveNotice}
        </div>
      )}

      {/* Patient Case */}
      <section className="bg-white border border-gray-200 rounded-xl p-5">
        <div className="flex items-center justify-between mb-2">
          <h2 className="text-xs font-semibold text-gray-400 uppercase tracking-wide">Patient Case</h2>
          <span className="text-xs font-mono text-gray-400">{selectedCase.id}</span>
        </div>
        <p className="text-base font-semibold text-gray-800 mb-0.5">{selectedCase.label}</p>
        <p className="text-sm text-gray-500 mb-4">{selectedCase.description}</p>
        <div className="flex gap-6 flex-wrap">
          <div>
            <p className="text-xs text-gray-400">Age</p>
            <p className="text-sm font-semibold text-gray-800">{selectedCase.patient_context.age} yrs</p>
          </div>
          <div>
            <p className="text-xs text-gray-400">Conditions</p>
            <p className="text-sm font-semibold text-gray-800">
              {selectedCase.patient_context.conditions.join(", ")}
            </p>
          </div>
          {Object.entries(selectedCase.patient_context.recent_labs || {}).map(([lab, val]) => (
            <div key={lab}>
              <p className="text-xs text-gray-400">{lab}</p>
              <p className="text-sm font-semibold text-gray-800">{val}</p>
            </div>
          ))}
        </div>
      </section>

      {/* Conflicting Sources */}
      <section className="bg-white border border-gray-200 rounded-xl p-5">
        <h2 className="text-xs font-semibold text-gray-400 uppercase tracking-wide mb-3">
          Conflicting Records ({selectedCase.sources.length} sources)
        </h2>
        <div className="space-y-2">
          {selectedCase.sources.map((s, i) => (
            <div key={i} className="flex items-center justify-between bg-gray-50 rounded-lg px-4 py-3">
              <div>
                <p className="text-xs text-gray-400 mb-0.5">{s.system}</p>
                <p className="text-sm font-semibold text-gray-800">{s.medication}</p>
              </div>
              <div className="flex items-center gap-3 text-right">
                <div>
                  <p className="text-xs text-gray-400">Date</p>
                  <p className="text-xs text-gray-600">{s.last_updated || s.last_filled}</p>
                </div>
                <span className={`text-xs font-semibold px-2 py-1 rounded-full capitalize ${RELIABILITY_STYLE[s.source_reliability]}`}>
                  {s.source_reliability}
                </span>
              </div>
            </div>
          ))}
        </div>
      </section>

      {/* Run button */}
      <button
        onClick={runReconciliation}
        disabled={loading}
        className="w-full bg-teal-600 text-white py-2.5 rounded-xl font-semibold hover:bg-teal-700 disabled:opacity-50 transition-colors">
        {loading ? "Reconciling…" : "Run Reconciliation"}
      </button>

      {error && (
        <div className="p-4 bg-red-50 border border-red-200 rounded-xl text-red-700 text-sm">{error}</div>
      )}

      {/* Results */}
      {result && (
        <section className="bg-white border border-gray-200 rounded-xl p-5 space-y-5">
          <h2 className="font-semibold text-gray-800 text-lg">Reconciliation Result</h2>

          {/* Reconciled medication */}
          <div className="bg-teal-50 border border-teal-200 rounded-lg p-4">
            <p className="text-xs text-teal-600 uppercase font-semibold mb-1">Reconciled Medication</p>
            <p className="text-2xl font-bold text-teal-800">{result.reconciled_medication}</p>
          </div>

          <ConfidenceBar score={result.confidence_score} />

          {/* Safety badge */}
          <div>
            <p className="text-sm text-gray-500 mb-1.5">Clinical Safety Check</p>
            <span className={`inline-block px-3 py-1 rounded-full text-sm font-semibold ${SAFETY_STYLE[result.clinical_safety_check] || "bg-gray-100 text-gray-700"}`}>
              {result.clinical_safety_check}
            </span>
          </div>

          {/* Reasoning */}
          <ReasoningBlock text={result.reasoning} />

          {/* Actions */}
          <div>
            <p className="text-sm font-semibold text-gray-600 mb-2">Recommended Actions</p>
            <ol className="space-y-2">
              {result.recommended_actions.map((action, i) => (
                <li key={i} className="flex items-start gap-3 bg-gray-50 rounded-lg px-4 py-3">
                  <span className="flex-shrink-0 w-5 h-5 rounded-full bg-teal-100 text-teal-700 text-xs font-bold flex items-center justify-center mt-0.5">
                    {i + 1}
                  </span>
                  <span className="text-sm text-gray-700 leading-relaxed">{action}</span>
                </li>
              ))}
            </ol>
          </div>

          {/* Approve / Reject */}
          {decision ? (
            <div className={`text-center py-2.5 rounded-xl text-sm font-semibold ${decision === "approved" ? "bg-green-50 text-green-700" : "bg-red-50 text-red-700"}`}>
              Decision recorded: {decision === "approved" ? "Approved ✓" : "Rejected ✗"}
            </div>
          ) : (
            <div className="flex gap-3">
              <button onClick={() => handleDecision("approved")} className="flex-1 bg-green-600 text-white py-2.5 rounded-xl font-semibold hover:bg-green-700 transition-colors">
                Approve
              </button>
              <button onClick={() => handleDecision("rejected")} className="flex-1 bg-red-500 text-white py-2.5 rounded-xl font-semibold hover:bg-red-600 transition-colors">
                Reject
              </button>
            </div>
          )}
        </section>
      )}
    </div>
  );
}
