import { Printer, Clock, MapPin, Phone } from "lucide-react";

export default function Footer() {
  return (
    <footer className="footer">
      <div className="container">
        <div className="footer-grid">
          <div>
            <div className="footer-brand">
              <Printer size={18} style={{ display: "inline", marginRight: 8 }} />
              CampusPrint
            </div>
            <p className="footer-text">
              Digital Xerox &amp; Stationery Ordering System for college students. Skip the queue,
              upload anywhere, collect on time.
            </p>
          </div>

          <div>
            <div className="footer-heading">Pricing</div>
            {[
              ["Black &amp; White", "₹2 / page"],
              ["Full Color", "₹5 / page"],
              ["Spiral Binding", "+₹30"],
              ["Soft Book Binding", "+₹50"],
              ["Hard Bound Embossed", "+₹160"],
            ].map(([k, v]) => (
              <div key={k} className="footer-item" style={{ justifyContent: "space-between" }}>
                <span dangerouslySetInnerHTML={{ __html: k }} />
                <span style={{ color: "#38bdf8", fontWeight: 600 }}>{v}</span>
              </div>
            ))}
          </div>

          <div>
            <div className="footer-heading">Contact</div>
            <div className="footer-item">
              <MapPin size={14} /> Block A, Ground Floor, Main Campus
            </div>
            <div className="footer-item">
              <Clock size={14} /> Mon–Sat · 8:00 AM – 7:00 PM
            </div>
            <div className="footer-item">
              <Phone size={14} /> +91 98765 43210
            </div>
          </div>
        </div>

        <div className="footer-bottom">
          <span>© 2026 CampusPrint · Digital Xerox &amp; Stationery · All rights reserved.</span>
        </div>
      </div>
    </footer>
  );
}
