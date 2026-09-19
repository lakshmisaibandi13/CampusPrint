import { useState } from "react";
import { Search, Loader, CheckCircle, Clock, Package, XCircle, ShoppingBag, FileText, Printer } from "lucide-react";

const PRINT_STEPS = ["Payment Successful", "Order Received", "Printing in Progress", "Ready for Collection", "Collected"];
const STATIONERY_STEPS = ["Payment Successful", "Order Received", "Preparing Stationery", "Ready for Collection", "Collected"];

function normalizeStatus(st, isStationeryOnly) {
  if (!st) return "Order Received";
  const s = st.toLowerCase().trim();
  if (s === "rejected") return "Rejected";
  if (s === "payment successful" || s === "payment verified") return "Payment Successful";
  if (s === "received" || s === "order received" || s === "order placed") return "Order Received";
  if (s === "processing" || s === "printing in progress" || s === "preparing stationery" || s === "printing") {
    return isStationeryOnly ? "Preparing Stationery" : "Printing in Progress";
  }
  if (s === "ready for collection" || s === "ready" || s === "stage ready") return "Ready for Collection";
  if (s === "completed" || s === "collected") return "Collected";
  return st;
}

function getStepIndex(status, steps, isStationeryOnly) {
  if (status === "Rejected") return -1;
  const norm = normalizeStatus(status, isStationeryOnly);
  const idx = steps.indexOf(norm);
  return idx >= 0 ? idx : 1;
}

function getBadgeClass(status) {
  const map = {
    "payment successful": "badge-ready",
    "payment verified": "badge-ready",
    received: "badge-received",
    "order received": "badge-received",
    "order placed": "badge-received",
    processing: "badge-processing",
    "printing in progress": "badge-processing",
    "preparing stationery": "badge-processing",
    "stage ready": "badge-ready",
    "ready for collection": "badge-ready",
    ready: "badge-ready",
    completed: "badge-completed",
    collected: "badge-completed",
    rejected: "badge-rejected",
  };
  return "badge " + (map[status?.toLowerCase()] || "badge-received");
}

function StatusIcon({ status }) {
  switch (status?.toLowerCase()) {
    case "payment successful":
    case "payment verified": return <CheckCircle size={16} />;
    case "received":
    case "order received":
    case "order placed": return <Clock size={16} />;
    case "processing":
    case "printing in progress":
    case "preparing stationery": return <Loader size={16} className="spin-icon" />;
    case "stage ready":
    case "ready for collection":
    case "ready": return <Package size={16} />;
    case "completed":
    case "collected": return <CheckCircle size={16} />;
    case "rejected": return <XCircle size={16} />;
    default: return <Clock size={16} />;
  }
}

function OrderCard({ order }) {
  const isStationeryOnly = order.order_type === "stationery" || (!order.document_name && (!order.items || order.items.length === 0));
  const steps = isStationeryOnly ? STATIONERY_STEPS : PRINT_STEPS;
  const stepIndex = getStepIndex(order.order_status, steps, isStationeryOnly);
  const isRejected = order.order_status === "Rejected";
  const progressPct = isRejected ? 0 : Math.min(100, (stepIndex / (steps.length - 1)) * 100);

  const stationeryList = order.stationery_items_list || order.stationery_items || [];
  const documentList = (order.items && order.items.length > 0)
    ? order.items
    : (order.document_name ? [{
        document_name: order.document_name,
        pages: order.pages,
        copies: order.copies,
        color_mode: order.color_mode,
        side_mode: order.side_mode,
        calculated_sheets: order.calculated_sheets,
      }] : []);

  const orderTypeLabel = order.order_type === "stationery"
    ? "Stationery"
    : order.order_type === "mixed"
    ? "Printing + Stationery"
    : "Printing";

  return (
    <div className="card animate-fade" style={{ marginBottom: 24 }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: 16, flexWrap: "wrap", gap: 10 }}>
        <div>
          <div style={{ fontWeight: 800, fontSize: "1.15rem", marginBottom: 4, display: "flex", alignItems: "center", gap: 8 }}>
            <span>Order #{order.display_order_number || order.id}</span>
            <span style={{ color: "var(--primary)", fontSize: ".92rem", fontWeight: 700 }}>({order.token_number})</span>
            <span style={{
              background: "var(--primary-light)", color: "var(--primary)",
              fontSize: ".75rem", fontWeight: 700, padding: "2px 8px", borderRadius: "9999px"
            }}>
              {orderTypeLabel}
            </span>
          </div>
          <div style={{ fontSize: ".82rem", color: "var(--text-muted)" }}>
            {order.order_id} · {new Date(order.created_at).toLocaleString("en-IN")}
          </div>
        </div>
        <span className={getBadgeClass(order.order_status)}>
          <StatusIcon status={order.order_status} />
          {order.order_status}
        </span>
      </div>

      {/* Smart Collection Time Banner */}
      {!isRejected && order.order_status !== "Collected" && order.order_status !== "Completed" && (
        <div style={{
          background: "linear-gradient(135deg, #0f172a, #1e293b)",
          border: "1.5px solid #38bdf8",
          borderRadius: "var(--radius-lg)",
          padding: "16px 20px",
          marginBottom: 20,
          textAlign: "center",
          boxShadow: "0 4px 18px rgba(56, 189, 248, 0.12)",
        }}>
          <div style={{
            fontSize: ".78rem", color: "#94a3b8", textTransform: "uppercase",
            letterSpacing: "0.08em", fontWeight: 700, marginBottom: 4,
            display: "flex", alignItems: "center", justifyContent: "center", gap: 6
          }}>
            <Clock size={15} color="#38bdf8" /> Smart Collection Time
          </div>
          <div style={{ fontSize: "1.45rem", fontWeight: 800, color: "#38bdf8" }}>
            {order.readable_collection_time
              ? `Collect at approximately ${order.readable_collection_time}`
              : "Ready for immediate collection"}
          </div>
        </div>
      )}

      {/* Timeline */}
      {!isRejected && (
        <div className="timeline" style={{ marginBottom: 24 }}>
          <div className="timeline-steps">
            <div className="timeline-line" />
            <div
              className="timeline-progress"
              style={{ width: `${progressPct}%` }}
            />
            {steps.map((step, i) => (
              <div
                key={step}
                className={`timeline-step ${i < stepIndex ? "completed" : i === stepIndex ? "active" : ""}`}
              >
                <div className="timeline-circle">
                  {i < stepIndex ? <CheckCircle size={16} /> : i + 1}
                </div>
                <div className="timeline-label">{step}</div>
              </div>
            ))}
          </div>
        </div>
      )}

      {isRejected && order.rejection_reason && (
        <div className="alert alert-error" style={{ marginBottom: 16 }}>
          <XCircle size={16} style={{ flexShrink: 0 }} />
          <div>
            <strong>Rejected:</strong> {order.rejection_reason}
          </div>
        </div>
      )}

      {/* Stationery Items Breakdown */}
      {stationeryList.length > 0 && (
        <div style={{ marginBottom: 16 }}>
          <div style={{
            fontWeight: 700, fontSize: ".92rem", marginBottom: 8,
            display: "flex", alignItems: "center", gap: 6, color: "var(--text-main)"
          }}>
            <ShoppingBag size={16} color="var(--primary)" /> Stationery Items ({stationeryList.length})
          </div>
          <div style={{
            background: "var(--bg-subtle)", borderRadius: "var(--radius-md)",
            padding: "10px 14px", border: "1px solid var(--border)"
          }}>
            {stationeryList.map((s, idx) => (
              <div key={idx} style={{
                display: "flex", justifyContent: "space-between", alignItems: "center",
                padding: "6px 0", fontSize: ".84rem",
                borderBottom: idx < stationeryList.length - 1 ? "1px solid var(--border)" : "none"
              }}>
                <div>
                  <span style={{ fontWeight: 700 }}>{s.quantity}x</span> {s.name}
                  <span style={{ fontSize: ".76rem", color: "var(--text-muted)", marginLeft: 6 }}>
                    (₹{s.price} each)
                  </span>
                </div>
                <span style={{ fontWeight: 700, color: "var(--text-main)" }}>
                  ₹{Number(s.subtotal).toFixed(2)}
                </span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Printing Documents Breakdown */}
      {documentList.length > 0 && (
        <div style={{ marginBottom: 16 }}>
          <div style={{
            fontWeight: 700, fontSize: ".92rem", marginBottom: 8,
            display: "flex", alignItems: "center", gap: 6, color: "var(--text-main)"
          }}>
            <FileText size={16} color="var(--primary)" /> Printing Documents ({documentList.length})
          </div>
          <div style={{
            background: "var(--bg-subtle)", borderRadius: "var(--radius-md)",
            padding: "10px 14px", border: "1px solid var(--border)"
          }}>
            {documentList.map((doc, idx) => (
              <div key={idx} style={{
                padding: "6px 0",
                borderBottom: idx < documentList.length - 1 ? "1px solid var(--border)" : "none"
              }}>
                <div style={{ fontWeight: 700, fontSize: ".84rem", color: "var(--text-main)" }}>
                  {doc.document_name}
                </div>
                <div style={{ fontSize: ".78rem", color: "var(--text-muted)", display: "flex", gap: 12, marginTop: 2, flexWrap: "wrap" }}>
                  <span>{doc.pages} pages × {doc.copies} {doc.copies === 1 ? "copy" : "copies"}</span>
                  <span>{doc.color_mode === "color" ? "Color" : "B&W"}</span>
                  <span>{doc.side_mode === "double" ? "Duplex" : "Single"}</span>
                  {doc.item_total && <span style={{ marginLeft: "auto", fontWeight: 700, color: "var(--primary)" }}>₹{doc.item_total}</span>}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Details Grid */}
      <div className="summary-divider" style={{ margin: "14px 0" }} />
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "8px 16px", fontSize: ".88rem" }}>
        {[
          ["Order #", `#${order.display_order_number || order.id}`],
          ["Token", order.token_number],
          ["Student", order.student_name],
          ["Roll Number", order.roll_number],
          ["Phone", order.phone_number],
          order.printing_total > 0 ? ["Printing Cost", `₹${Number(order.printing_total).toFixed(2)}`] : null,
          order.stationery_total > 0 ? ["Stationery Cost", `₹${Number(order.stationery_total).toFixed(2)}`] : null,
          ["Total Amount", `₹${Number(order.total_price).toFixed(2)}`],
        ].filter(Boolean).map(([k, v]) => (
          <div key={k} className="summary-row" style={{ marginBottom: 0 }}>
            <span>{k}</span>
            <span style={{ fontWeight: 600, color: "var(--text-main)" }}>{v}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

export default function TrackOrder() {
  const [query, setQuery] = useState("");
  const [loading, setLoading] = useState(false);
  const [results, setResults] = useState(null);
  const [error, setError] = useState(null);

  async function handleSearch(e) {
    e.preventDefault();
    const q = query.trim();
    if (!q) return;
    setLoading(true);
    setError(null);
    setResults(null);
    try {
      const res = await fetch(`/api/orders/track/${encodeURIComponent(q)}`);
      const data = await res.json();
      if (data.success) {
        setResults(data.orders);
      } else {
        setError(data.message || "No orders found.");
      }
    } catch {
      setError("Could not reach server. Please check your connection.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="container" style={{ padding: "40px 20px 60px", maxWidth: 760, margin: "0 auto" }}>
      <div style={{ textAlign: "center", marginBottom: 32 }}>
        <h2 style={{ fontSize: "1.8rem", fontWeight: 800, marginBottom: 8 }}>Track Your Order</h2>
        <p style={{ color: "var(--text-muted)" }}>
          Enter your Token Number, Order ID, Roll Number, or Phone Number.
        </p>
      </div>

      <form onSubmit={handleSearch} style={{ display: "flex", gap: 12, marginBottom: 32 }}>
        <input
          className="form-input"
          style={{ flex: 1, fontSize: "1rem" }}
          placeholder="TK-101 or ORD-20260912-XXXX or Roll Number…"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
        />
        <button className="btn btn-primary" type="submit" disabled={loading}>
          {loading ? <Loader size={18} className="spin-icon" /> : <Search size={18} />}
          Track
        </button>
      </form>

      {error && (
        <div className="alert alert-error animate-fade">{error}</div>
      )}

      {results && results.length === 0 && (
        <div className="alert alert-info animate-fade">No orders found for this query.</div>
      )}

      {results && results.map((order) => (
        <OrderCard key={order.order_id} order={order} />
      ))}
    </div>
  );
}
