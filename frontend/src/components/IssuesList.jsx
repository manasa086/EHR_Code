const STYLES = {
  high:   "border-red-300    bg-red-50    text-red-800",
  medium: "border-yellow-300 bg-yellow-50 text-yellow-800",
  low:    "border-gray-200   bg-gray-50   text-gray-700",
};

export default function IssuesList({ issues }) {
  if (!issues.length) {
    return <p className="text-green-600 text-sm font-medium">No issues detected.</p>;
  }

  return (
    <ul className="space-y-2">
      {issues.map((issue, i) => (
        <li key={i} className={`border rounded px-3 py-2 text-sm ${STYLES[issue.severity]}`}>
          <span className="font-semibold">{issue.field}</span>
          <span className="mx-1">—</span>
          {issue.issue}
          <span className="ml-2 text-xs opacity-60 uppercase">[{issue.severity}]</span>
        </li>
      ))}
    </ul>
  );
}
