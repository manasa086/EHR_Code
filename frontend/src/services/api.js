const BASE = import.meta.env.VITE_API_BASE || "http://localhost:8000/api";
const API_KEY = import.meta.env.VITE_API_KEY || "dev-secret-key";

const headers = {
  "Content-Type": "application/json",
  "X-API-Key": API_KEY,
};

async function post(path, body) {
  const res = await fetch(`${BASE}${path}`, { method: "POST", headers, body: JSON.stringify(body) });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(text || `Request failed: ${res.status}`);
  }
  return res.json();
}

export const reconcileMedication = (data) => post("/reconcile/medication", data);
export const validateDataQuality  = (data) => post("/validate/data-quality", data);
export const recordDecision       = (data) => post("/decisions", data);

export async function getCases() {
  const res = await fetch(`${BASE}/cases`, { headers });
  if (!res.ok) throw new Error("Failed to load cases");
  return res.json();
}

export async function createCase(data) {
  return post("/cases", data);
}

export async function updateCase(id, data) {
  const res = await fetch(`${BASE}/cases/${id}`, {
    method: "PUT",
    headers,
    body: JSON.stringify(data),
  });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(text || `Request failed: ${res.status}`);
  }
  return res.json();
}

// Returns the most recent decision for a given case+type, or null if none recorded.
export async function getDecision(caseId, type) {
  const res = await fetch(`${BASE}/decisions?case_id=${caseId}&type=${type}`, { headers });
  if (!res.ok) return null;
  const list = await res.json();
  // Most recent is last in the list
  return list.length > 0 ? list[list.length - 1] : null;
}
