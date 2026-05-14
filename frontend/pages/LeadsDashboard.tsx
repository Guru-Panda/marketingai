import Navbar from "../components/Navbar";
import Sidebar from "../components/Sidebar";
import LeadsTable from "../components/LeadsTable";

export default function LeadsDashboard() {
  return (
    <div className="flex flex-col h-screen">
      <Navbar />
      <div className="flex flex-1 overflow-hidden">
        <Sidebar />
        <main className="flex-1 overflow-y-auto bg-gray-50 p-8">
          <div className="mb-6">
            <h2 className="text-xl font-semibold text-gray-900">Leads</h2>
            <p className="text-sm text-gray-500 mt-0.5">
              Inbound signals scored by AI. High-intent leads from your monitored channels.
            </p>
          </div>
          <LeadsTable />
        </main>
      </div>
    </div>
  );
}
