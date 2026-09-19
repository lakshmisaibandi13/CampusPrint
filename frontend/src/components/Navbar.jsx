import { Printer, ClipboardList, Search, ShieldCheck } from "lucide-react";

export default function Navbar({ activeTab, setActiveTab }) {
  return (
    <nav className="navbar">
      <div className="container">
        <div className="navbar-inner">
          <div className="brand-logo">
            <div className="logo-badge">
              <Printer size={22} />
            </div>
            <div className="brand-text">
              <span>CampusPrint</span>
              <span className="brand-tagline">Digital Xerox & Stationery</span>
            </div>
          </div>

          <div className="nav-links">
            <button
              className={`nav-btn${activeTab === "home" ? " active" : ""}`}
              onClick={() => setActiveTab("home")}
            >
              <Printer size={16} />
              Home
            </button>
            <button
              className={`nav-btn${activeTab === "order" ? " active" : ""}`}
              onClick={() => setActiveTab("order")}
            >
              <ClipboardList size={16} />
              Place Order
            </button>
            <button
              className={`nav-btn${activeTab === "track" ? " active" : ""}`}
              onClick={() => setActiveTab("track")}
            >
              <Search size={16} />
              Track Order
            </button>
            <button
              className={`nav-btn staff-portal-btn${activeTab === "staff" ? " active" : ""}`}
              onClick={() => setActiveTab("staff")}
            >
              <ShieldCheck size={16} />
              Staff Portal
            </button>
          </div>
        </div>
      </div>
    </nav>
  );
}
