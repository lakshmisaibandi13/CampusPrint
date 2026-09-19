import { useState } from "react";
import Navbar from "./components/Navbar";
import LandingHero from "./components/LandingHero";
import OrderForm from "./components/OrderForm";
import TrackOrder from "./components/TrackOrder";
import StaffPortal from "./components/StaffPortal";
import Footer from "./components/Footer";

export default function App() {
  const [activeTab, setActiveTab] = useState("home");

  return (
    <div className="app-container">
      <Navbar activeTab={activeTab} setActiveTab={setActiveTab} />

      <main className="main-content">
        {activeTab === "home" && (
          <LandingHero onOrderNow={() => setActiveTab("order")} />
        )}
        {activeTab === "order" && (
          <OrderForm onTabChange={setActiveTab} />
        )}
        {activeTab === "track" && (
          <TrackOrder />
        )}
        {activeTab === "staff" && (
          <StaffPortal />
        )}
      </main>

      <Footer />
    </div>
  );
}
