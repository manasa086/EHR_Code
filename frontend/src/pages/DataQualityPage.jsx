import { useState, useEffect } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { useSSE } from "../hooks/useSSE";
import { validateDataQuality, recordDecision, getDecision } from "../services/api";
import ScoreBadge from "../components/ScoreBadge";
import IssuesList from "../components/IssuesList";

const DIMENSION_LABELS = {
  completeness:          "Completeness",
  accuracy:              "Accuracy",
  timeliness:            "Timeliness",
  clinical_plausibility: "Clinical Plausibility",
};

const RELIABILITY_STYLE = {
  high:   "bg-green-100 text-green-700",
  medium: "bg-yellow-100 text-yellow-700",
  low:    "bg-red-100 text-red-700",
};

const GENDER_LABEL = { M: "Male", F: "Female", Other: "Other" };

function ScoreCircle({ score }) {
  const color = score >= 70 ? "#22c55e" : score >= 50 ? "#eab308" : "#ef4444";
  const label = score >= 70 ? "Good"    : score >= 50 ? "Fair"    : "Poor";
  return (
    <div className="flex items-center gap-5">
      <div className="relative w-20 h-20">
        <svg viewBox="0 0 36 36" className="w-20 h-20 -rotate-90">
          <circle cx="18" cy="18" r="15.9" fill="none" stroke="#e5e7eb" strokeWidth="3.5" />
          <circle
            cx="18" cy="18" r="15.9" fill="none"
            stroke={color} strokeWidth="3.5"
            strokeDasharray={`${score} 100`}
            strokeLinecap="round"
          />
        </svg>
        <div className="absolute inset-0 flex items-center justify-center">
          <span className="text-base font-bold" style={{ color }}>{score}</span>
        </div>
      </div>
      <div>
        <p className="text-xs text-gray-400 uppercase font-semibold mb-0.5">Overall Score</p>
        <p className="text-2xl font-bold" style={{ color }}>{label}</p>
      </div>
    </div>
  );
}

function Field({ label, value }) {
  return (
    <div>
      <p className="text-xs text-gray-400">{label}</p>
      <p className="text-sm font-semibold text-gray-800">{value || "—"}</p>
    </div>
  );
}

export default function DataQualityPage() {
  const location = useLocation();
  const navigate = useNavigate();
  const selectedCase = location.state?.case ?? null;

  const [result, setResult]         = useState(null);
  const [loading, setLoading]       = useState(false);
  const [error, setError]           = useState(null);
  const [decision, setDecision]     = useState(null);
  const [liveNotice, setLiveNotice] = useState(null);

  // On case load: reset UI and restore any previously recorded decision from the server
  useEffect(() => {
    setResult(null);
    setDecision(null);
    setError(null);
    setLiveNotice(null);
    if (!selectedCase?.id) return;
    getDecision(selectedCase.id, "data_quality").then((entry) => {
      if (!entry) return;
      setDecision(entry.decision);
      if (entry.data) setResult(entry.data);
    });
  }, [selectedCase?.id]);

  // Live SSE — notice when another tab/user validates this case
  useSSE({
    data_quality_done: ({ case_id, label }) => {
      if (case_id && case_id !== selectedCase?.id) return;
      setLiveNotice(`Data quality check just completed for "${label ?? case_id}" in another session.`);
      setTimeout(() => setLiveNotice(null), 6000);
    },
  });

  async function runValidation() {
    if (!selectedCase) return;
    setError(null);
    setResult(null);
    setDecision(null);
    setLoading(true);
    try {
      const payload = {
        // Core quality fields
        demographics:  selectedCase.demographics               ?? {},
        medications:   [...new Set((selectedCase.sources ?? []).map((s) => s.medication))],
        allergies:     selectedCase.allergies                  ?? [],
        conditions:    selectedCase.patient_context?.conditions ?? [],
        vital_signs:   selectedCase.vital_signs                ?? {},
        last_updated:  selectedCase.last_updated               ?? null,
        // Full case metadata — ensures cache key covers every field
        id:             selectedCase.id,
        label:          selectedCase.label,
        description:    selectedCase.description,
        patient_context: selectedCase.patient_context ?? null,
        sources:         selectedCase.sources         ?? null,
      };
      setResult(await validateDataQuality(payload));
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }

  async function handleDecision(dec) {
    setDecision(dec);
    try {
      await recordDecision({ type: "data_quality", case_id: selectedCase.id, decision: dec, data: result });
    } catch {
      // silently swallow
    }
  }

  if (!selectedCase) {
    return (
      <div className="max-w-3xl mx-auto py-24 px-4 text-center space-y-4">
        <p className="text-lg font-semibold text-gray-700">No case selected</p>
        <p className="text-sm text-gray-500">Select a case from the Cases page, then click "Data Quality".</p>
        <button
          onClick={() => navigate("/cases")}
          className="bg-teal-600 text-white px-6 py-2.5 rounded-xl font-semibold hover:bg-teal-700 transition-colors">
          Go to Cases
        </button>
      </div>
    );
  }

  const demo   = selectedCase.demographics  ?? {};
  const vitals = selectedCase.vital_signs   ?? {};
  const labs   = selectedCase.patient_context?.recent_labs ?? {};
  const uniqueMeds = [...new Set((selectedCase.sources ?? []).map((s) => s.medication))];

  return (
    <div className="max-w-3xl mx-auto py-8 px-4 space-y-5">
      <div>
        <button
          onClick={() => navigate("/cases")}
          className="text-xs text-teal-600 hover:text-teal-700 font-semibold mb-2 inline-block">
          ← Back to Cases
        </button>
        <h1 className="text-2xl font-bold text-gray-800 mb-1">Data Quality Validator</h1>
        <p className="text-sm text-gray-500">
          Review patient record completeness and run quality validation.
        </p>
      </div>

      {/* SSE live notice */}
      {liveNotice && (
        <div className="flex items-center gap-2 bg-indigo-50 border border-indigo-200 rounded-xl px-4 py-3 text-sm text-indigo-700">
          <span className="w-2 h-2 rounded-full bg-indigo-400 animate-pulse flex-shrink-0" />
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
          <Field label="Age" value={`${selectedCase.patient_context?.age} yrs`} />
          <Field label="Conditions" value={selectedCase.patient_context?.conditions?.join(", ")} />
          {Object.entries(labs).map(([k, v]) => (
            <Field key={k} label={k} value={String(v)} />
          ))}
        </div>
      </section>

      {/* Demographics */}
      <section className="bg-white border border-gray-200 rounded-xl p-5">
        <h2 className="text-xs font-semibold text-gray-400 uppercase tracking-wide mb-3">Demographics</h2>
        <div className="flex gap-6 flex-wrap">
          <Field label="Name"          value={demo.name} />
          <Field label="Date of Birth" value={demo.dob} />
          <Field label="Gender"        value={GENDER_LABEL[demo.gender] ?? demo.gender} />
          <Field label="Record Updated" value={selectedCase.last_updated} />
        </div>
      </section>

      {/* Clinical */}
      <section className="bg-white border border-gray-200 rounded-xl p-5 space-y-4">
        <h2 className="text-xs font-semibold text-gray-400 uppercase tracking-wide">Clinical Information</h2>

        {/* Allergies */}
        <div>
          <p className="text-xs text-gray-400 mb-1.5">Allergies</p>
          {selectedCase.allergies?.length ? (
            <div className="flex flex-wrap gap-2">
              {selectedCase.allergies.map((a) => (
                <span key={a} className="text-xs font-semibold bg-red-50 text-red-700 border border-red-200 rounded-full px-3 py-1">
                  {a}
                </span>
              ))}
            </div>
          ) : (
            <p className="text-sm text-gray-400 italic">None documented</p>
          )}
        </div>

        {/* Vital signs */}
        <div className="flex gap-6 flex-wrap">
          <Field label="Blood Pressure" value={vitals.blood_pressure} />
          <Field label="Heart Rate"     value={vitals.heart_rate ? `${vitals.heart_rate} bpm` : null} />
        </div>

        {/* Medications (unique across sources) */}
        <div>
          <p className="text-xs text-gray-400 mb-1.5">Medications (from all sources)</p>
          <div className="flex flex-wrap gap-2">
            {uniqueMeds.map((m) => (
              <span key={m} className="text-xs font-semibold bg-teal-50 text-teal-700 border border-teal-200 rounded-full px-3 py-1">
                {m}
              </span>
            ))}
          </div>
        </div>
      </section>

      {/* Medication Sources */}
      <section className="bg-white border border-gray-200 rounded-xl p-5">
        <h2 className="text-xs font-semibold text-gray-400 uppercase tracking-wide mb-3">
          Medication Sources ({selectedCase.sources?.length ?? 0})
        </h2>
        <div className="space-y-2">
          {(selectedCase.sources ?? []).map((s, i) => (
            <div key={i} className="flex items-center justify-between bg-gray-50 rounded-lg px-4 py-3">
              <div>
                <p className="text-xs text-gray-400 mb-0.5">{s.system}</p>
                <p className="text-sm font-semibold text-gray-800">{s.medication}</p>
              </div>
              <div className="flex items-center gap-3">
                <div className="text-right">
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
        onClick={runValidation}
        disabled={loading}
        className="w-full bg-indigo-600 text-white py-2.5 rounded-xl font-semibold hover:bg-indigo-700 disabled:opacity-50 transition-colors">
        {loading ? "Validating…" : "Validate Data Quality"}
      </button>

      {error && (
        <div className="p-4 bg-red-50 border border-red-200 rounded-xl text-red-700 text-sm">{error}</div>
      )}

      {/* Results */}
      {result && (
        <section className="bg-white border border-gray-200 rounded-xl p-5 space-y-5">
          <h2 className="font-semibold text-gray-800 text-lg">Quality Report</h2>

          <ScoreCircle score={result.overall_score} />

          {/* Dimension breakdown */}
          <div>
            <p className="text-sm text-gray-500 mb-2">Score Breakdown</p>
            <div className="grid grid-cols-2 gap-2">
              {Object.entries(result.breakdown).map(([key, val]) => (
                <div key={key} className="flex items-center justify-between bg-gray-50 rounded-lg px-3 py-2">
                  <span className="text-sm text-gray-600">{DIMENSION_LABELS[key] || key}</span>
                  <ScoreBadge score={val} />
                </div>
              ))}
            </div>
          </div>

          {/* Issues */}
          <div>
            <p className="text-sm text-gray-500 mb-2">
              Issues Detected
              <span className="ml-1 text-xs font-semibold bg-gray-100 text-gray-600 rounded-full px-2 py-0.5">
                {result.issues_detected.length}
              </span>
            </p>
            <IssuesList issues={result.issues_detected} />
          </div>

          {/* Approve / Reject */}
          {decision ? (
            <div className={`text-center py-2.5 rounded-xl text-sm font-semibold ${decision === "approved" ? "bg-green-50 text-green-700" : "bg-red-50 text-red-700"}`}>
              Decision recorded: {decision === "approved" ? "Approved ✓" : "Rejected ✗"}
            </div>
          ) : (
            <div className="flex gap-3 pt-1">
              <button onClick={() => handleDecision("approved")} className="flex-1 bg-green-600 text-white py-2.5 rounded-xl font-semibold hover:bg-green-700 transition-colors">
                Approve Report
              </button>
              <button onClick={() => handleDecision("rejected")} className="flex-1 bg-red-500 text-white py-2.5 rounded-xl font-semibold hover:bg-red-600 transition-colors">
                Reject Report
              </button>
            </div>
          )}
        </section>
      )}
    </div>
  );
}
