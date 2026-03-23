export default function ConfidenceBar({ score }) {
  const percent = Math.round(score * 100);
  const color =
    score >= 0.8 ? "bg-green-500" :
    score >= 0.6 ? "bg-yellow-400" :
    "bg-red-500";
  const label =
    score >= 0.8 ? "High" :
    score >= 0.6 ? "Medium" :
    "Low";

  return (
    <div>
      <div className="flex justify-between text-sm text-gray-600 mb-1">
        <span>Confidence</span>
        <span className="font-medium">{percent}% — {label}</span>
      </div>
      <div className="h-2.5 bg-gray-200 rounded-full overflow-hidden">
        <div className={`h-full rounded-full transition-all ${color}`} style={{ width: `${percent}%` }} />
      </div>
    </div>
  );
}
