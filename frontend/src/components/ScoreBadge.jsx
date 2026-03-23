export default function ScoreBadge({ score }) {
  const style =
    score >= 70 ? "bg-green-100 text-green-800" :
    score >= 50 ? "bg-yellow-100 text-yellow-800" :
    "bg-red-100 text-red-800";

  return (
    <span className={`px-2.5 py-0.5 rounded-full text-xs font-semibold ${style}`}>
      {score}
    </span>
  );
}
