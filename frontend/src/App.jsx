import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import Navbar from "./components/Navbar";
import CasesPage from "./pages/CasesPage";
import ReconcilePage from "./pages/ReconcilePage";
import DataQualityPage from "./pages/DataQualityPage";

export default function App() {
  return (
    <BrowserRouter>
      <div className="min-h-screen bg-gray-50">
        <Navbar />
        <main>
          <Routes>
            <Route path="/" element={<Navigate to="/cases" replace />} />
            <Route path="/cases" element={<CasesPage />} />
            <Route path="/reconcile" element={<ReconcilePage />} />
            <Route path="/data-quality" element={<DataQualityPage />} />
          </Routes>
        </main>
      </div>
    </BrowserRouter>
  );
}
