import { useState, useEffect } from "react";
import {
  Printer, BookOpen, Layers, ShoppingBag, ArrowRight,
  ArrowLeft, CheckCircle, Tag
} from "lucide-react";

const API = typeof window !== "undefined" && (window.location.hostname === "localhost" || window.location.hostname === "127.0.0.1")
  ? "/api"
  : (import.meta.env.VITE_API_URL || "https://campusprint-syv1.onrender.com/api");

const FALLBACK_PRICING = {
  bw_per_page: 2.0,
  color_per_page: 5.0,
  types: [
    { id: "regular", name: "Standard Document / Notes", extra_cost: 0.0 },
    { id: "assignment", name: "College Assignment / Lab Record", extra_cost: 0.0 },
    { id: "project_report", name: "Final Project Report", extra_cost: 15.0 },
    { id: "certificate", name: "Glossy / Certificate Print", extra_cost: 20.0 }
  ],
  bindings: [
    { id: "none", name: "No Binding (Loose Sheets / Stapled)", price: 0.0 },
    { id: "spiral", name: "Spiral Binding (Clear Cover)", price: 30.0 },
    { id: "soft_binding", name: "Soft Book Binding", price: 50.0 },
    { id: "hard_binding", name: "Hard Bound Golden Embossed", price: 160.0 }
  ]
};

const FALLBACK_STATIONERY = [
  { id: "black_pen", name: "Black Pen", price: 5.0, unit: "each", category: "Pens & Pencils" },
  { id: "blue_pen", name: "Blue Pen", price: 5.0, unit: "each", category: "Pens & Pencils" },
  { id: "red_pen", name: "Red Pen", price: 5.0, unit: "each", category: "Pens & Pencils" },
  { id: "pencil", name: "Pencil", price: 5.0, unit: "each", category: "Pens & Pencils" },
  { id: "eraser", name: "Eraser", price: 5.0, unit: "each", category: "Pens & Pencils" },
  { id: "sharpener", name: "Sharpener", price: 3.0, unit: "each", category: "Pens & Pencils" },
  { id: "plain_small_notebook", name: "Small Plain Notebook", price: 20.0, unit: "each", category: "Notebooks" },
  { id: "plain_long_notebook", name: "Long Plain Notebook", price: 50.0, unit: "each", category: "Notebooks" },
  { id: "ruled_long_notebook", name: "Long Ruled Notebook", price: 50.0, unit: "each", category: "Notebooks" },
  { id: "assignment_booklet", name: "Assignment Booklet", price: 15.0, unit: "each", category: "Papers, Booklets & Records" },
  { id: "record_book", name: "Record Book", price: 90.0, unit: "each", category: "Papers, Booklets & Records" },
  { id: "record_paper", name: "Record Paper", price: 1.0, unit: "per page", category: "Papers, Booklets & Records" },
  { id: "a4_sheet", name: "A4 Sheet", price: 1.0, unit: "per sheet", category: "Papers, Booklets & Records" },
  { id: "bee_record", name: "BEE Record", price: 150.0, unit: "each", category: "Papers, Booklets & Records" },
  { id: "aep_record", name: "AEP Record", price: 100.0, unit: "each", category: "Papers, Booklets & Records" },
  { id: "english_record", name: "English Record", price: 100.0, unit: "each", category: "Papers, Booklets & Records" }
];

export default function PricingView({ onOrderNow, onBack }) {
  const [pricing, setPricing] = useState(FALLBACK_PRICING);
  const [stationery, setStationery] = useState(FALLBACK_STATIONERY);
  const [activeCategory, setActiveCategory] = useState("all");

  useEffect(() => {
    let isMounted = true;
    fetch(`${API}/pricing`)
      .then((res) => res.json())
      .then((data) => {
        if (!isMounted) return;
        if (data.pricing) setPricing(data.pricing);
        if (data.stationery && data.stationery.length > 0) setStationery(data.stationery);
      })
      .catch(() => {
        // Fallbacks remain active if fetch fails
      });
    return () => {
      isMounted = false;
    };
  }, []);

  const categories = ["all", ...new Set(stationery.map((item) => item.category || "General"))];
  const filteredStationery = activeCategory === "all"
    ? stationery
    : stationery.filter((item) => item.category === activeCategory);

  return (
    <div className="container" style={{ padding: "40px 20px 80px", maxWidth: 1000, margin: "0 auto" }}>
      {/* Navigation Top Bar */}
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 24 }}>
        <button
          onClick={onBack}
          className="btn btn-outline btn-sm"
          style={{ display: "inline-flex", alignItems: "center", gap: 6 }}
        >
          <ArrowLeft size={16} /> Back to Home
        </button>
        <button
          onClick={onOrderNow}
          className="btn btn-primary btn-sm"
          style={{ display: "inline-flex", alignItems: "center", gap: 6 }}
        >
          <Printer size={16} /> Place Order Now <ArrowRight size={16} />
        </button>
      </div>

      {/* Header Banner */}
      <div style={{
        background: "linear-gradient(135deg, #0f172a 0%, #1e1b4b 60%, #1e293b 100%)",
        borderRadius: "var(--radius-xl)",
        padding: "36px 32px",
        color: "#fff",
        textAlign: "center",
        marginBottom: 36,
        position: "relative",
        overflow: "hidden",
        boxShadow: "var(--shadow-xl)"
      }}>
        <h1 style={{ fontSize: "2.3rem", fontWeight: 800, color: "#fff", marginBottom: 10 }}>
          Transparent, Student-Friendly Rates
        </h1>
        <p style={{ color: "#cbd5e1", fontSize: "1.05rem", maxWidth: 640, margin: "0 auto 20px", lineHeight: 1.6 }}>
          Review our exact Xerox and stationery prices below before ordering. All rates are inclusive of campus counter service.
        </p>
        <button
          onClick={onOrderNow}
          className="btn btn-primary"
          style={{ fontWeight: 700, padding: "12px 28px", fontSize: "1rem" }}
        >
          <Printer size={18} /> Start Your Order
        </button>
      </div>

      {/* ── Printing Rates Section ── */}
      <section style={{ marginBottom: 48 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 20 }}>
          <div style={{
            width: 36, height: 36, borderRadius: "var(--radius-md)",
            background: "var(--primary-light)", color: "var(--primary)",
            display: "flex", alignItems: "center", justifyContent: "center"
          }}>
            <Printer size={20} />
          </div>
          <div>
            <h2 style={{ fontSize: "1.45rem", fontWeight: 800 }}>Printing &amp; Xerox Rates</h2>
            <p style={{ color: "var(--text-muted)", fontSize: ".88rem" }}>
              Per-page and duplex sheet pricing for Black &amp; White and Full Color prints.
            </p>
          </div>
        </div>

        {/* 4 Core Printing Rates */}
        <div style={{
          display: "grid",
          gridTemplateColumns: "repeat(auto-fit, minmax(220px, 1fr))",
          gap: 16,
          marginBottom: 28
        }}>
          {/* B&W Single */}
          <div className="card" style={{
            border: "1.5px solid var(--border)",
            background: "var(--bg-card)",
            position: "relative",
            overflow: "hidden"
          }}>
            <div style={{ fontSize: ".8rem", fontWeight: 700, color: "var(--text-muted)", textTransform: "uppercase", letterSpacing: ".05em" }}>
              Black &amp; White
            </div>
            <div style={{ fontSize: "1.1rem", fontWeight: 800, color: "var(--text-main)", margin: "4px 0 10px" }}>
              Single-Sided
            </div>
            <div style={{ display: "flex", alignItems: "baseline", gap: 4, marginBottom: 8 }}>
              <span style={{ fontSize: "2rem", fontWeight: 800, color: "var(--primary)", fontFamily: "var(--font-heading)" }}>
                ₹{Number(pricing.bw_per_page).toFixed(0)}
              </span>
              <span style={{ color: "var(--text-muted)", fontSize: ".85rem" }}>/ page</span>
            </div>
            <div style={{ fontSize: ".82rem", color: "var(--text-muted)", lineHeight: 1.5 }}>
              Standard 75 GSM A4 paper. Crisp high-resolution monochrome print.
            </div>
          </div>

          {/* B&W Double */}
          <div className="card" style={{
            border: "2px solid #38bdf8",
            background: "linear-gradient(180deg, #f0f9ff 0%, #ffffff 100%)",
            position: "relative",
            overflow: "hidden"
          }}>
            <div style={{
              position: "absolute", top: 10, right: 10,
              background: "#0284c7", color: "#fff",
              fontSize: ".7rem", fontWeight: 800, padding: "2px 8px", borderRadius: 9999
            }}>
              POPULAR
            </div>
            <div style={{ fontSize: ".8rem", fontWeight: 700, color: "#0369a1", textTransform: "uppercase", letterSpacing: ".05em" }}>
              Black &amp; White
            </div>
            <div style={{ fontSize: "1.1rem", fontWeight: 800, color: "var(--text-main)", margin: "4px 0 10px" }}>
              Double-Sided
            </div>
            <div style={{ display: "flex", alignItems: "baseline", gap: 4, marginBottom: 8 }}>
              <span style={{ fontSize: "2rem", fontWeight: 800, color: "#0284c7", fontFamily: "var(--font-heading)" }}>
                ₹3
              </span>
              <span style={{ color: "var(--text-muted)", fontSize: ".85rem" }}>/ sheet (2 pages)</span>
            </div>
            <div style={{ fontSize: ".82rem", color: "var(--text-muted)", lineHeight: 1.5 }}>
              Effective rate of <strong>₹1.50 per page side</strong>. Saves paper and binder space.
            </div>
          </div>

          {/* Color Single */}
          <div className="card" style={{
            border: "1.5px solid var(--border)",
            background: "var(--bg-card)",
            position: "relative",
            overflow: "hidden"
          }}>
            <div style={{ fontSize: ".8rem", fontWeight: 700, color: "var(--text-muted)", textTransform: "uppercase", letterSpacing: ".05em" }}>
              Full Color
            </div>
            <div style={{ fontSize: "1.1rem", fontWeight: 800, color: "var(--text-main)", margin: "4px 0 10px" }}>
              Single-Sided
            </div>
            <div style={{ display: "flex", alignItems: "baseline", gap: 4, marginBottom: 8 }}>
              <span style={{ fontSize: "2rem", fontWeight: 800, color: "#7c3aed", fontFamily: "var(--font-heading)" }}>
                ₹{Number(pricing.color_per_page).toFixed(0)}
              </span>
              <span style={{ color: "var(--text-muted)", fontSize: ".85rem" }}>/ page</span>
            </div>
            <div style={{ fontSize: ".82rem", color: "var(--text-muted)", lineHeight: 1.5 }}>
              Vibrant, high-gamut color output for lab graphs, diagrams, and project slides.
            </div>
          </div>

          {/* Color Double */}
          <div className="card" style={{
            border: "1.5px solid #c4b5fd",
            background: "linear-gradient(180deg, #f5f3ff 0%, #ffffff 100%)",
            position: "relative",
            overflow: "hidden"
          }}>
            <div style={{ fontSize: ".8rem", fontWeight: 700, color: "#6d28d9", textTransform: "uppercase", letterSpacing: ".05em" }}>
              Full Color
            </div>
            <div style={{ fontSize: "1.1rem", fontWeight: 800, color: "var(--text-main)", margin: "4px 0 10px" }}>
              Double-Sided
            </div>
            <div style={{ display: "flex", alignItems: "baseline", gap: 4, marginBottom: 8 }}>
              <span style={{ fontSize: "2rem", fontWeight: 800, color: "#7c3aed", fontFamily: "var(--font-heading)" }}>
                ₹8
              </span>
              <span style={{ color: "var(--text-muted)", fontSize: ".85rem" }}>/ sheet (2 pages)</span>
            </div>
            <div style={{ fontSize: ".82rem", color: "var(--text-muted)", lineHeight: 1.5 }}>
              Effective rate of <strong>₹4.00 per page side</strong>. Ideal for rich reports and presentations.
            </div>
          </div>
        </div>

        {/* Document Types and Binding Surcharges Grid */}
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(320px, 1fr))", gap: 20 }}>
          {/* Document Types */}
          <div className="card">
            <div style={{ fontWeight: 700, fontSize: "1rem", marginBottom: 14, display: "flex", alignItems: "center", gap: 8 }}>
              <Layers size={18} color="var(--primary)" /> Document Types
            </div>
            <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
              {(pricing.types || []).map((t) => (
                <div
                  key={t.id}
                  style={{
                    display: "flex", justifyContent: "space-between", alignItems: "center",
                    fontSize: ".88rem", paddingBottom: 8, borderBottom: "1px solid var(--border)"
                  }}
                >
                  <span style={{ color: "var(--text-main)", fontWeight: 500 }}>{t.name}</span>
                  <span style={{
                    fontWeight: 700,
                    color: t.extra_cost > 0 ? "var(--primary)" : "#10b981",
                    background: t.extra_cost > 0 ? "var(--primary-light)" : "#ecfdf5",
                    padding: "2px 8px", borderRadius: 9999, fontSize: ".8rem"
                  }}>
                    {t.extra_cost > 0 ? `+₹${Number(t.extra_cost).toFixed(0)}` : "Free"}
                  </span>
                </div>
              ))}
            </div>
          </div>

          {/* Binding Options */}
          <div className="card">
            <div style={{ fontWeight: 700, fontSize: "1rem", marginBottom: 14, display: "flex", alignItems: "center", gap: 8 }}>
              <BookOpen size={18} color="var(--primary)" /> Binding Options
            </div>
            <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
              {(pricing.bindings || []).filter((b) => b.id !== "corner_staple").map((b) => (
                <div
                  key={b.id}
                  style={{
                    display: "flex", justifyContent: "space-between", alignItems: "center",
                    fontSize: ".88rem", paddingBottom: 8, borderBottom: "1px solid var(--border)"
                  }}
                >
                  <span style={{ color: "var(--text-main)", fontWeight: 500 }}>{b.name}</span>
                  <span style={{
                    fontWeight: 700,
                    color: b.price > 0 ? "#4338ca" : "#10b981",
                    background: b.price > 0 ? "#e0e7ff" : "#ecfdf5",
                    padding: "2px 8px", borderRadius: 9999, fontSize: ".8rem"
                  }}>
                    {b.price > 0 ? `+₹${Number(b.price).toFixed(0)}` : "Free"}
                  </span>
                </div>
              ))}
            </div>
          </div>
        </div>
      </section>

      {/* ── Stationery Catalog Section ── */}
      <section style={{ marginBottom: 40 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 20 }}>
          <div style={{
            width: 36, height: 36, borderRadius: "var(--radius-md)",
            background: "#ecfdf5", color: "#059669",
            display: "flex", alignItems: "center", justifyContent: "center"
          }}>
            <ShoppingBag size={20} />
          </div>
          <div>
            <h2 style={{ fontSize: "1.45rem", fontWeight: 800 }}>Campus Stationery Price List</h2>
            <p style={{ color: "var(--text-muted)", fontSize: ".88rem" }}>
              Official college stationery, notebooks, and lab record booklets in stock.
            </p>
          </div>
        </div>

        {/* Category Pills */}
        <div style={{ display: "flex", flexWrap: "wrap", gap: 8, marginBottom: 20 }}>
          {categories.map((cat) => (
            <button
              key={cat}
              onClick={() => setActiveCategory(cat)}
              className="btn btn-sm"
              style={{
                borderRadius: 9999,
                fontWeight: 600,
                textTransform: "capitalize",
                background: activeCategory === cat ? "var(--primary)" : "var(--bg-subtle)",
                color: activeCategory === cat ? "#fff" : "var(--text-muted)",
                border: "1px solid",
                borderColor: activeCategory === cat ? "var(--primary)" : "var(--border)"
              }}
            >
              {cat === "all" ? "All Stationery" : cat}
            </button>
          ))}
        </div>

        {/* Stationery Grid */}
        <div style={{
          display: "grid",
          gridTemplateColumns: "repeat(auto-fill, minmax(280px, 1fr))",
          gap: 14
        }}>
          {filteredStationery.map((item) => (
            <div
              key={item.id}
              className="card"
              style={{
                display: "flex",
                justifyContent: "space-between",
                alignItems: "center",
                padding: "16px 18px",
                borderRadius: "var(--radius-md)",
                border: "1px solid var(--border)"
              }}
            >
              <div>
                <div style={{ fontWeight: 700, fontSize: ".95rem", color: "var(--text-main)" }}>
                  {item.name}
                </div>
                <div style={{ fontSize: ".76rem", color: "var(--text-muted)", marginTop: 2 }}>
                  {item.category || "Stationery"} · {item.unit || "each"}
                </div>
              </div>
              <div style={{ textAlign: "right" }}>
                <div style={{
                  fontSize: "1.25rem", fontWeight: 800, color: "var(--primary)",
                  fontFamily: "var(--font-heading)"
                }}>
                  ₹{Number(item.price).toFixed(0)}
                </div>
                <div style={{ fontSize: ".72rem", color: "var(--text-muted)" }}>
                  {item.unit === "each" ? "per piece" : item.unit}
                </div>
              </div>
            </div>
          ))}
        </div>
      </section>

      {/* Bottom CTA Card */}
      <div style={{
        background: "var(--primary-light)",
        border: "1.5px solid var(--primary-border)",
        borderRadius: "var(--radius-xl)",
        padding: "32px",
        textAlign: "center"
      }}>
        <h3 style={{ fontSize: "1.35rem", fontWeight: 800, marginBottom: 8, color: "var(--text-main)" }}>
          Ready to Place Your Order?
        </h3>
        <p style={{ color: "var(--text-muted)", maxWidth: 520, margin: "0 auto 20px", fontSize: ".92rem" }}>
          Upload your documents, select your print or stationery options, and get your instant token number.
        </p>
        <div style={{ display: "flex", justifyContent: "center", gap: 12, flexWrap: "wrap" }}>
          <button onClick={onBack} className="btn btn-outline" style={{ background: "#fff" }}>
            <ArrowLeft size={16} /> Back to Home
          </button>
          <button onClick={onOrderNow} className="btn btn-primary" style={{ fontWeight: 700 }}>
            <Printer size={18} /> Place Order Now <ArrowRight size={18} />
          </button>
        </div>
      </div>
    </div>
  );
}
