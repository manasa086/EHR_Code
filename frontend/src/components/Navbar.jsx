import { NavLink } from "react-router-dom";

export default function Navbar() {
  const linkClass = ({ isActive }) =>
    isActive
      ? "text-teal-600 font-semibold border-b-2 border-teal-600 pb-1"
      : "text-gray-500 hover:text-gray-800 pb-1";

  return (
    <nav className="bg-white border-b border-gray-200 px-6 py-4">
      <div className="max-w-4xl mx-auto flex items-center gap-8">
        <span className="font-bold text-teal-600 text-lg tracking-tight">EHR Reconcile</span>
        <NavLink to="/cases" className={linkClass}>Cases</NavLink>
        <NavLink to="/reconcile" className={linkClass}>Medication Reconciliation</NavLink>
        <NavLink to="/data-quality" className={linkClass}>Data Quality</NavLink>
      </div>
    </nav>
  );
}
