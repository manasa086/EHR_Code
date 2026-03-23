import { useState, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { getCases, createCase, updateCase } from "../services/api";
import { useSSE } from "../hooks/useSSE";

const RELIABILITY_OPTIONS = ["high", "medium", "low"];

const EMPTY_FORM = {
  label: "",
  description: "",
  age: "",
  conditions: "",
  labs: [{ key: "", value: "" }],
  sources: [{ system: "", medication: "", date: "", reliability: "high" }],
  // Demographics
  name: "",
  dob: "",
  gender: "",
  // Clinical details
  allergies: "",
  blood_pressure: "",
  heart_rate: "",
  last_updated: "",
};

function caseToForm(c) {
  return {
    label:       c.label,
    description: c.description,
    age:         String(c.patient_context.age),
    conditions:  c.patient_context.conditions.join(", "),
    labs: Object.entries(c.patient_context.recent_labs || {}).map(([k, v]) => ({
      key: k, value: String(v),
    })),
    sources: c.sources.map((s) => ({
      system: s.system, medication: s.medication,
      date: s.last_updated || s.last_filled || "", reliability: s.source_reliability,
    })),
    // Demographics
    name:   c.demographics?.name   ?? "",
    dob:    c.demographics?.dob    ?? "",
    gender: c.demographics?.gender ?? "",
    // Clinical details
    allergies:      (c.allergies ?? []).join(", "),
    blood_pressure: String(c.vital_signs?.blood_pressure ?? ""),
    heart_rate:     String(c.vital_signs?.heart_rate     ?? ""),
    last_updated:   c.last_updated ?? "",
  };
}

function formToCase(form, existingId) {
  return {
    ...(existingId ? { id: existingId } : {}),
    label:       form.label,
    description: form.description,
    patient_context: {
      age: parseInt(form.age) || 0,
      conditions: form.conditions.split(",").map((c) => c.trim()).filter(Boolean),
      recent_labs: Object.fromEntries(
        form.labs
          .filter((l) => l.key.trim())
          .map((l) => [l.key.trim(), isNaN(parseFloat(l.value)) ? l.value : parseFloat(l.value)])
      ),
    },
    sources: form.sources.map((s) => ({
      system: s.system, medication: s.medication,
      last_updated: s.date || null, source_reliability: s.reliability,
    })),
    demographics: {
      name:   form.name   || null,
      dob:    form.dob    || null,
      gender: form.gender || null,
    },
    allergies: form.allergies.split(",").map((a) => a.trim()).filter(Boolean),
    vital_signs: {
      blood_pressure: form.blood_pressure || null,
      heart_rate:     form.heart_rate ? parseInt(form.heart_rate) : null,
    },
    last_updated: form.last_updated || null,
  };
}

// ── Validation ────────────────────────────────────────────────────────────────
const TODAY = new Date().toISOString().split("T")[0]; // "YYYY-MM-DD"

function validateForm(form) {
  const errors = {};

  // Label
  if (!form.label.trim()) errors.label = "Label is required";

  // Age — required, must be 0–150
  if (!form.dob) {
    const age = parseInt(form.age);
    if (!form.age.trim() || isNaN(age)) errors.age = "Age is required";
    else if (age < 0 || age > 150) errors.age = "Age must be between 0 and 150";
  }

  // DOB — must not be in the future
  if (form.dob && form.dob > TODAY) errors.dob = "Date of birth cannot be in the future";

  // Blood pressure — optional, but if entered must be "number/number"
  if (form.blood_pressure.trim()) {
    const bpValid = /^\d{1,3}\/\d{1,3}$/.test(form.blood_pressure.trim());
    if (!bpValid) errors.blood_pressure = "Use format 120/80";
  }

  // Heart rate — optional, but if entered must be 1–300
  if (form.heart_rate.trim()) {
    const hr = parseInt(form.heart_rate);
    if (isNaN(hr) || hr < 1 || hr > 300)
      errors.heart_rate = "Heart rate must be between 1 and 300 bpm";
  }

  // Sources
  if (form.sources.length === 0) {
    errors.sourcesGlobal = "At least one medication source is required";
  } else {
    const sourceErrors = form.sources.map((s) => {
      const e = {};
      if (!s.system.trim()) e.system = "System name is required";
      if (!s.medication.trim()) e.medication = "Medication is required";
      if (s.date && s.date > TODAY) e.date = "Source date cannot be in the future";
      return e;
    });
    if (sourceErrors.some((e) => Object.keys(e).length > 0)) errors.sources = sourceErrors;
  }

  // Record last updated — must not be in the future
  if (form.last_updated && form.last_updated > TODAY)
    errors.last_updated = "Record last updated cannot be in the future";

  // Labs — key and value must both be present or both absent
  const labErrors = form.labs.map((l) => {
    if (l.key.trim() && !l.value.trim()) return "Enter a value for this lab";
    if (!l.key.trim() && l.value.trim()) return "Enter a name for this lab";
    return null;
  });
  if (labErrors.some(Boolean)) errors.labs = labErrors;

  return errors;
}

// ── Edit Form ────────────────────────────────────────────────────────────────
function CaseEditForm({ initial, onSave, onCancel, saving }) {
  const [form, setForm] = useState(initial);
  const [attempted, setAttempted] = useState(false);

  const set = (field, value) => setForm((f) => ({ ...f, [field]: value }));

  function updateSource(i, field, value) {
    const next = [...form.sources];
    next[i] = { ...next[i], [field]: value };
    setForm((f) => ({ ...f, sources: next }));
  }

  function addSource() {
    setForm((f) => ({
      ...f,
      sources: [...f.sources, { system: "", medication: "", date: "", reliability: "high" }],
    }));
  }

  function removeSource(i) {
    setForm((f) => ({ ...f, sources: f.sources.filter((_, idx) => idx !== i) }));
  }

  const formErrors = attempted ? validateForm(form) : {};
  const hasErrors = Object.keys(formErrors).length > 0;

  function handleSaveClick() {
    setAttempted(true);
    const errs = validateForm(form);
    if (Object.keys(errs).length > 0 || hasDuplicates) return;
    onSave(form);
  }

  // Which system names appear more than once (case-insensitive)?
  const duplicateSystems = (() => {
    const seen = new Set();
    const dupes = new Set();
    for (const s of form.sources) {
      const name = (s.system || "").trim().toLowerCase();
      if (!name) continue;
      if (seen.has(name)) dupes.add(name);
      seen.add(name);
    }
    return dupes;
  })();
  const hasDuplicates = duplicateSystems.size > 0;

  function updateLab(i, field, value) {
    const next = [...form.labs];
    next[i] = { ...next[i], [field]: value };
    setForm((f) => ({ ...f, labs: next }));
  }

  function addLab() {
    setForm((f) => ({ ...f, labs: [...f.labs, { key: "", value: "" }] }));
  }

  function removeLab(i) {
    setForm((f) => ({ ...f, labs: f.labs.filter((_, idx) => idx !== i) }));
  }

  function handleDobChange(dob) {
    const updates = { dob };
    if (dob) {
      const today = new Date();
      const birth = new Date(dob);
      let age = today.getFullYear() - birth.getFullYear();
      const m = today.getMonth() - birth.getMonth();
      if (m < 0 || (m === 0 && today.getDate() < birth.getDate())) age--;
      updates.age = String(Math.max(0, age));
    }
    setForm((f) => ({ ...f, ...updates }));
  }

  const inputCls = "w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-teal-400";
  const inputErrCls = "w-full border border-red-400 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-red-400 bg-red-50";
  const readonlyCls = "w-full border border-gray-200 rounded-lg px-3 py-2 text-sm bg-gray-100 text-gray-500 cursor-not-allowed";
  const errMsg = (msg) => msg ? <p className="text-xs text-red-500 mt-1">{msg}</p> : null;

  return (
    <div className="space-y-4">
      {/* Basic Info */}
      <section className="bg-gray-50 rounded-xl p-4 space-y-3">
        <h3 className="text-xs font-semibold text-gray-400 uppercase tracking-wide">Basic Info</h3>
        <div>
          <label className="block text-xs text-gray-500 mb-1">Label <span className="text-red-400">*</span></label>
          <input value={form.label} onChange={(e) => set("label", e.target.value)}
            placeholder="e.g. Cardiac Patient — Warfarin Dose Conflict"
            className={formErrors.label ? inputErrCls : inputCls} />
          {errMsg(formErrors.label)}
        </div>
        <div>
          <label className="block text-xs text-gray-500 mb-1">Description</label>
          <textarea value={form.description} onChange={(e) => set("description", e.target.value)}
            rows={2} placeholder="Brief clinical summary…"
            className={inputCls + " resize-none"} />
        </div>
      </section>

      {/* Demographics */}
      <section className="bg-gray-50 rounded-xl p-4 space-y-3">
        <h3 className="text-xs font-semibold text-gray-400 uppercase tracking-wide">Demographics</h3>
        <div className="grid grid-cols-3 gap-3">
          <div>
            <label className="block text-xs text-gray-500 mb-1">Full Name</label>
            <input value={form.name} onChange={(e) => set("name", e.target.value)}
              placeholder="Patient A" className={inputCls} />
          </div>
          <div>
            <label className="block text-xs text-gray-500 mb-1">Date of Birth</label>
            <input type="date" value={form.dob} onChange={(e) => handleDobChange(e.target.value)}
              max={TODAY}
              className={formErrors.dob ? inputErrCls : inputCls} />
            {errMsg(formErrors.dob)}
          </div>
          <div>
            <label className="block text-xs text-gray-500 mb-1">Gender</label>
            <select value={form.gender} onChange={(e) => set("gender", e.target.value)}
              className={inputCls}>
              <option value="">Select</option>
              <option value="M">Male</option>
              <option value="F">Female</option>
              <option value="Other">Other</option>
            </select>
          </div>
        </div>
      </section>

      {/* Patient Context */}
      <section className="bg-gray-50 rounded-xl p-4 space-y-3">
        <h3 className="text-xs font-semibold text-gray-400 uppercase tracking-wide">Patient Context</h3>
        <div className="grid grid-cols-2 gap-3">
          <div>
            <label className="block text-xs text-gray-500 mb-1">
              Age <span className="text-red-400">*</span>{" "}
              {form.dob && <span className="text-teal-500">(auto-calculated)</span>}
            </label>
            <input type="number" value={form.age}
              onChange={(e) => !form.dob && set("age", e.target.value)}
              readOnly={!!form.dob}
              placeholder="65"
              className={form.dob ? readonlyCls : formErrors.age ? inputErrCls : inputCls} />
            {errMsg(formErrors.age)}
          </div>
          <div>
            <label className="block text-xs text-gray-500 mb-1">Conditions (comma-separated)</label>
            <input value={form.conditions} onChange={(e) => set("conditions", e.target.value)}
              placeholder="Atrial Fibrillation, Hypertension" className={inputCls} />
          </div>
        </div>

        {/* Labs */}
        <div>
          <div className="flex items-center justify-between mb-2">
            <label className="text-xs text-gray-500">Recent Labs</label>
            <button type="button" onClick={addLab}
              className="text-xs text-teal-600 hover:text-teal-700 font-semibold">
              + Add Lab
            </button>
          </div>
          <div className="space-y-2">
            {form.labs.map((lab, i) => (
              <div key={i}>
                <div className="flex gap-2 items-center">
                  <input value={lab.key} onChange={(e) => updateLab(i, "key", e.target.value)}
                    placeholder="e.g. INR"
                    className={formErrors.labs?.[i] && !lab.key.trim() ? inputErrCls : inputCls} />
                  <input value={lab.value} onChange={(e) => updateLab(i, "value", e.target.value)}
                    placeholder="e.g. 1.8"
                    className={formErrors.labs?.[i] && !lab.value.trim() ? inputErrCls : inputCls} />
                  <button type="button" onClick={() => removeLab(i)}
                    className="text-red-400 hover:text-red-600 text-lg leading-none flex-shrink-0">×</button>
                </div>
                {errMsg(formErrors.labs?.[i])}
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* Sources */}
      <section className="bg-gray-50 rounded-xl p-4 space-y-3">
        <div className="flex items-center justify-between">
          <h3 className="text-xs font-semibold text-gray-400 uppercase tracking-wide">
            Medication Sources <span className="text-red-400">*</span>
          </h3>
          <button type="button" onClick={addSource}
            className="text-xs text-teal-600 hover:text-teal-700 font-semibold">
            + Add Source
          </button>
        </div>
        {form.sources.map((s, i) => (
          <div key={i} className="bg-white border border-gray-200 rounded-lg p-3 space-y-2">
            <div className="flex justify-between items-center">
              <span className="text-xs font-semibold text-gray-400">Source {i + 1}</span>
              {form.sources.length > 1 && (
                <button type="button" onClick={() => removeSource(i)}
                  className="text-xs text-red-400 hover:text-red-600">Remove</button>
              )}
            </div>
            <div className="grid grid-cols-2 gap-2">
              <div>
                <input
                  value={s.system}
                  onChange={(e) => updateSource(i, "system", e.target.value)}
                  placeholder="System (e.g. Hospital EHR) *"
                  className={
                    duplicateSystems.has((s.system || "").trim().toLowerCase()) && s.system.trim()
                      ? "w-full border border-red-400 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-red-400 bg-red-50"
                      : formErrors.sources?.[i]?.system
                      ? inputErrCls
                      : inputCls
                  }
                />
                {duplicateSystems.has((s.system || "").trim().toLowerCase()) && s.system.trim()
                  ? <p className="text-xs text-red-500 mt-1">Duplicate source system</p>
                  : errMsg(formErrors.sources?.[i]?.system)
                }
              </div>
              <div>
                <input value={s.medication} onChange={(e) => updateSource(i, "medication", e.target.value)}
                  placeholder="Medication + dose *"
                  className={formErrors.sources?.[i]?.medication ? inputErrCls : inputCls} />
                {errMsg(formErrors.sources?.[i]?.medication)}
              </div>
            </div>
            <div className="grid grid-cols-2 gap-2">
              <div>
                <input type="date" value={s.date} onChange={(e) => updateSource(i, "date", e.target.value)}
                  max={TODAY}
                  className={formErrors.sources?.[i]?.date ? inputErrCls : inputCls} />
                {errMsg(formErrors.sources?.[i]?.date)}
              </div>
              <select value={s.reliability} onChange={(e) => updateSource(i, "reliability", e.target.value)}
                className={inputCls}>
                {RELIABILITY_OPTIONS.map((r) => (
                  <option key={r} value={r}>{r.charAt(0).toUpperCase() + r.slice(1)}</option>
                ))}
              </select>
            </div>
          </div>
        ))}
        {errMsg(formErrors.sourcesGlobal)}
      </section>

      {/* Clinical Details */}
      <section className="bg-gray-50 rounded-xl p-4 space-y-3">
        <h3 className="text-xs font-semibold text-gray-400 uppercase tracking-wide">Clinical Details</h3>
        <div>
          <label className="block text-xs text-gray-500 mb-1">Allergies (comma-separated)</label>
          <input value={form.allergies} onChange={(e) => set("allergies", e.target.value)}
            placeholder="Penicillin, Sulfonamides" className={inputCls} />
        </div>
        <div className="grid grid-cols-3 gap-3">
          <div>
            <label className="block text-xs text-gray-500 mb-1">Blood Pressure</label>
            <input value={form.blood_pressure} onChange={(e) => set("blood_pressure", e.target.value)}
              placeholder="120/80"
              className={formErrors.blood_pressure ? inputErrCls : inputCls} />
            {errMsg(formErrors.blood_pressure)}
          </div>
          <div>
            <label className="block text-xs text-gray-500 mb-1">Heart Rate (bpm)</label>
            <input type="number" value={form.heart_rate} onChange={(e) => set("heart_rate", e.target.value)}
              placeholder="72"
              className={formErrors.heart_rate ? inputErrCls : inputCls} />
            {errMsg(formErrors.heart_rate)}
          </div>
          <div>
            <label className="block text-xs text-gray-500 mb-1">Record Last Updated</label>
            <input type="date" value={form.last_updated} onChange={(e) => set("last_updated", e.target.value)}
              max={TODAY}
              className={formErrors.last_updated ? inputErrCls : inputCls} />
            {errMsg(formErrors.last_updated)}
          </div>
        </div>
      </section>

      {/* Actions */}
      {hasDuplicates && (
        <div className="px-3 py-2 bg-red-50 border border-red-200 rounded-lg text-xs text-red-600">
          Each source system must be unique. Remove or rename duplicate sources before saving.
        </div>
      )}
      {attempted && hasErrors && !hasDuplicates && (
        <div className="px-3 py-2 bg-red-50 border border-red-200 rounded-lg text-xs text-red-600">
          Please fill in all required fields before saving.
        </div>
      )}
      <div className="flex gap-3">
        <button onClick={handleSaveClick} disabled={saving}
          className="flex-1 bg-teal-600 text-white py-2.5 rounded-xl font-semibold hover:bg-teal-700 disabled:opacity-50 transition-colors">
          {saving ? "Saving…" : "Save Case"}
        </button>
        <button onClick={onCancel}
          className="flex-1 bg-gray-100 text-gray-600 py-2.5 rounded-xl font-semibold hover:bg-gray-200 transition-colors">
          Cancel
        </button>
      </div>
    </div>
  );
}

// ── Main Page ─────────────────────────────────────────────────────────────────
export default function CasesPage() {
  const navigate = useNavigate();
  const [cases, setCases]         = useState([]);
  const [loadError, setLoadError] = useState(null);
  const [selectedId, setSelectedId] = useState(null);
  const [editingId, setEditingId]   = useState(null);  // case id being edited, or "new"
  const [saving, setSaving]         = useState(false);
  const [saveError, setSaveError]   = useState(null);

  useEffect(() => {
    getCases()
      .then(setCases)
      .catch((e) => setLoadError(e.message));
  }, []);

  // Live updates — other users' edits/additions appear instantly
  useSSE({
    case_created: (data) => setCases((prev) =>
      prev.some((c) => c.id === data.id) ? prev : [...prev, data]
    ),
    case_updated: (data) => setCases((prev) =>
      prev.map((c) => (c.id === data.id ? data : c))
    ),
  });

  function startEdit(c) {
    setSaveError(null);
    setEditingId(c.id);
    setSelectedId(null);
  }

  function startAdd() {
    setSaveError(null);
    setEditingId("new");
    setSelectedId(null);
  }

  function cancelEdit() {
    setEditingId(null);
    setSaveError(null);
  }

  async function handleSave(form) {
    setSaving(true);
    setSaveError(null);
    try {
      const payload = formToCase(form, editingId === "new" ? null : editingId);
      let saved;
      if (editingId === "new") {
        saved = await createCase(payload);
        setCases((prev) => [...prev, saved]);
      } else {
        saved = await updateCase(editingId, payload);
        setCases((prev) => prev.map((c) => (c.id === editingId ? saved : c)));
      }
      setEditingId(null);
    } catch (e) {
      setSaveError(e.message);
    } finally {
      setSaving(false);
    }
  }

  function goTo(path, c) {
    navigate(path, { state: { case: c } });
  }

  const RELIABILITY_STYLE = {
    high:   "bg-green-100 text-green-700",
    medium: "bg-yellow-100 text-yellow-700",
    low:    "bg-red-100 text-red-700",
  };

  return (
    <div className="max-w-3xl mx-auto py-8 px-4 space-y-5">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-800">Patient Cases</h1>
          <p className="text-sm text-gray-500 mt-0.5">
            {cases.length} case{cases.length !== 1 ? "s" : ""} loaded
          </p>
        </div>
        <button onClick={startAdd}
          className="bg-teal-600 text-white px-4 py-2 rounded-xl font-semibold text-sm hover:bg-teal-700 transition-colors">
          + Add New Case
        </button>
      </div>

      {loadError && (
        <div className="p-4 bg-red-50 border border-red-200 rounded-xl text-red-700 text-sm">
          Failed to load cases: {loadError}
        </div>
      )}

      {saveError && (
        <div className="p-4 bg-red-50 border border-red-200 rounded-xl text-red-700 text-sm">
          Save failed: {saveError}
        </div>
      )}

      {/* Add New Case form */}
      {editingId === "new" && (
        <div className="bg-white border-2 border-teal-300 rounded-xl p-5">
          <h2 className="font-semibold text-gray-800 mb-4">New Case</h2>
          <CaseEditForm
            initial={EMPTY_FORM}
            onSave={handleSave}
            onCancel={cancelEdit}
            saving={saving}
          />
        </div>
      )}

      {/* Case list */}
      {cases.length === 0 && !loadError && editingId !== "new" && (
        <div className="text-center py-12 text-gray-400 text-sm">
          No cases found. Click "Add New Case" to create one.
        </div>
      )}

      <div className="space-y-3">
        {cases.map((c) => {
          const isSelected = selectedId === c.id;
          const isEditing  = editingId === c.id;

          return (
            <div key={c.id}
              className={`bg-white border rounded-xl transition-all ${
                isSelected ? "border-teal-400 shadow-md" : "border-gray-200 hover:border-gray-300"
              }`}>

              {/* Case header — always visible */}
              <div
                className="flex items-center justify-between px-5 py-4 cursor-pointer"
                onClick={() => !isEditing && setSelectedId(isSelected ? null : c.id)}
              >
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2">
                    <span className="text-xs font-mono text-gray-400">{c.id}</span>
                    <span className="text-sm font-semibold text-gray-800 truncate">{c.label}</span>
                  </div>
                  <p className="text-xs text-gray-500 mt-0.5 line-clamp-1">{c.description}</p>
                </div>
                <div className="flex items-center gap-2 ml-3 flex-shrink-0">
                  {c.editable && (
                    <button
                      onClick={(e) => { e.stopPropagation(); startEdit(c); }}
                      className="text-xs font-semibold text-gray-500 border border-gray-300 rounded-lg px-3 py-1.5 hover:border-teal-400 hover:text-teal-600 transition-colors">
                      Edit
                    </button>
                  )}
                  <span className={`text-xs ${isSelected ? "text-teal-500" : "text-gray-300"}`}>
                    {isSelected ? "▲" : "▼"}
                  </span>
                </div>
              </div>

              {/* Expanded: case detail + action buttons */}
              {isSelected && !isEditing && (
                <div className="border-t border-gray-100 px-5 py-4 space-y-4">
                  {/* Patient context */}
                  <div className="flex gap-6 flex-wrap">
                    <div>
                      <p className="text-xs text-gray-400">Age</p>
                      <p className="text-sm font-semibold text-gray-800">{c.patient_context.age} yrs</p>
                    </div>
                    <div>
                      <p className="text-xs text-gray-400">Conditions</p>
                      <p className="text-sm font-semibold text-gray-800">
                        {c.patient_context.conditions.join(", ")}
                      </p>
                    </div>
                    {Object.entries(c.patient_context.recent_labs || {}).map(([lab, val]) => (
                      <div key={lab}>
                        <p className="text-xs text-gray-400">{lab}</p>
                        <p className="text-sm font-semibold text-gray-800">{val}</p>
                      </div>
                    ))}
                  </div>

                  {/* Sources */}
                  <div className="space-y-1.5">
                    {c.sources.map((s, i) => (
                      <div key={i} className="flex items-center justify-between bg-gray-50 rounded-lg px-3 py-2">
                        <div>
                          <p className="text-xs text-gray-400">{s.system}</p>
                          <p className="text-sm font-semibold text-gray-700">{s.medication}</p>
                        </div>
                        <div className="flex items-center gap-2">
                          <span className="text-xs text-gray-400">{s.last_updated || s.last_filled}</span>
                          <span className={`text-xs font-semibold px-2 py-0.5 rounded-full capitalize ${RELIABILITY_STYLE[s.source_reliability]}`}>
                            {s.source_reliability}
                          </span>
                        </div>
                      </div>
                    ))}
                  </div>

                  {/* Action buttons */}
                  <div className="flex gap-3 pt-1">
                    <button
                      onClick={() => goTo("/reconcile", c)}
                      className="flex-1 bg-teal-600 text-white py-2.5 rounded-xl font-semibold text-sm hover:bg-teal-700 transition-colors">
                      Medication Reconciliation
                    </button>
                    <button
                      onClick={() => goTo("/data-quality", c)}
                      className="flex-1 bg-indigo-600 text-white py-2.5 rounded-xl font-semibold text-sm hover:bg-indigo-700 transition-colors">
                      Data Quality
                    </button>
                  </div>
                </div>
              )}

              {/* Inline edit form */}
              {isEditing && (
                <div className="border-t border-gray-100 px-5 py-4">
                  <CaseEditForm
                    initial={caseToForm(c)}
                    onSave={handleSave}
                    onCancel={cancelEdit}
                    saving={saving}
                  />
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
