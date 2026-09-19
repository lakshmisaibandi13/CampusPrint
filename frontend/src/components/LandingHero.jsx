import { Printer, Zap, Shield, Clock, Upload, CheckCircle } from "lucide-react";

export default function LandingHero({ onOrderNow }) {
  const features = [
    {
      icon: <Upload size={24} />,
      title: "Upload Anywhere",
      text: "Submit your assignment, lab record, or project report from your phone or laptop — no queues.",
    },
    {
      icon: <Zap size={24} />,
      title: "Instant Price Quote",
      text: "Live price calculation as you choose print options — B&W, Color, Single/Double-sided, Binding.",
    },
    {
      icon: <CheckCircle size={24} />,
      title: "Digital Token",
      text: "Get a unique token number instantly. Track your order status in real time.",
    },
    {
      icon: <Shield size={24} />,
      title: "Secure UPI Payment",
      text: "Pay via UPI and upload your payment screenshot for instant verification.",
    },
  ];

  return (
    <>
      {/* ── Hero Section ── */}
      <section className="hero-section">
        <div className="container">
          <div className="hero-grid">
            <div>
              <div className="hero-badge">
                <span className="pulse-dot" />
                Counter Open · Instant Processing
              </div>
              <h1 className="hero-title">
                Skip the Queue at the{" "}
                <span className="hero-highlight">Campus Xerox Counter</span>
              </h1>
              <p className="hero-desc">
                Upload your documents, choose your print settings, pay via UPI,
                and collect your prints — all without waiting in line.
              </p>
              <div className="hero-cta-group">
                <button className="btn btn-primary" onClick={onOrderNow}>
                  <Printer size={18} />
                  Place Order Now
                </button>
                <button className="btn btn-secondary" onClick={onOrderNow}>
                  View Pricing
                </button>
              </div>
            </div>

            <div className="hero-stats-card">
              <div className="hero-stats-header">
                <span style={{ color: "#fff", fontWeight: 700, fontSize: ".95rem" }}>
                  Print Rates 2026
                </span>
                <span className="shop-status-badge">
                  <span className="pulse-dot" />
                  Open Now
                </span>
              </div>

              <div className="rate-cards-grid">
                <div className="rate-box">
                  <div className="rate-box-title">Black &amp; White</div>
                  <div className="rate-box-price">₹2</div>
                  <div className="rate-box-unit">per page</div>
                </div>
                <div className="rate-box">
                  <div className="rate-box-title">Full Color</div>
                  <div className="rate-box-price">₹5</div>
                  <div className="rate-box-unit">per page</div>
                </div>
              </div>

              <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                {[
                  ["Spiral Binding", "+₹30"],
                  ["Soft Book Binding", "+₹50"],
                  ["Hard Bound Embossed", "+₹160"],
                ].map(([label, price]) => (
                  <div
                    key={label}
                    style={{
                      display: "flex",
                      justifyContent: "space-between",
                      fontSize: ".82rem",
                      color: "#94a3b8",
                      borderBottom: "1px solid rgba(255,255,255,.08)",
                      paddingBottom: 6,
                    }}
                  >
                    <span>{label}</span>
                    <span style={{ color: "#38bdf8", fontWeight: 700 }}>{price}</span>
                  </div>
                ))}
              </div>

              <div style={{ marginTop: 16, display: "flex", alignItems: "center", gap: 8 }}>
                <Clock size={14} style={{ color: "#94a3b8" }} />
                <span style={{ fontSize: ".78rem", color: "#94a3b8" }}>
                  Mon–Sat · 8 AM – 7 PM · Block A Ground Floor
                </span>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* ── Features Section ── */}
      <section className="features-section">
        <div className="container">
          <div className="section-header">
            <div className="section-subtitle">Why CampusPrint?</div>
            <h2 className="section-title">Everything You Need, In One Place</h2>
            <p className="section-desc">
              From upload to collection — streamlined for every college student.
            </p>
          </div>
          <div className="feature-cards">
            {features.map((f) => (
              <div className="card" key={f.title}>
                <div className="feature-icon-wrapper">{f.icon}</div>
                <h3 className="feature-title">{f.title}</h3>
                <p className="feature-text">{f.text}</p>
              </div>
            ))}
          </div>
        </div>
      </section>
    </>
  );
}
