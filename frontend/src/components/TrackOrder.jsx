import { useState, useEffect, useCallback } from "react";
import {
  Search, Loader, CheckCircle, Clock, Package, XCircle,
  ShoppingBag, FileText, Printer, ChevronDown, ChevronUp,
  AlertCircle, Calendar, CreditCard, ArrowRight, Sparkles
} from "lucide-react";

const API = typeof window !== "undefined" && (window.location.hostname === "localhost" || window.location.hostname === "127.0.0.1")
  ? "/api"
  : (import.meta.env.VITE_API_URL || "https://campusprint-syv1.onrender.com/api");

const PROGRESS_STAGES = [
  { key: "placed", label: "Placed" },
  { key: "payment_verified", label: "Payment Verified" },
  { key: "in_queue", label: "In Queue" },
  { key: "processing", label: "Processing" },
  { key: "ready", label: "Ready for Collection" },
  { key: "collected", label: "Collected" }
];

function getStageIndex(status, isPaid) {
  if (!status) return 0;
  const s = status.toLowerCase().trim();
  if (s === "cancelled" || s === "rejected") return -1;
  if (s === "collected" || s === "completed") return 5;
  if (s === "ready for collection" || s === "ready" || s === "stage ready") return 4;
  if (s === "processing" || s === "printing in progress" || s === "preparing stationery" || s === "printing") return 3;
  if (s === "in queue" || s === "queue") return 2;
  if (s === "payment verified" || s === "payment successful" || isPaid) return 1;
  return 0; // Placed / Received
}

function formatISTDateTime(dateInput) {
  if (!dateInput) return "";
  try {
    let s = String(dateInput).trim();
    if (!s.includes("Z") && !s.includes("+") && !/[+-]\d{2}:\d{2}$/.test(s)) {
      s = s.replace(" ", "T") + "+05:30";
    }
    const d = new Date(s);
    if (isNaN(d.getTime())) return String(dateInput);
    return d.toLocaleString("en-IN", {
      timeZone: "Asia/Kolkata",
      day: "numeric",
      month: "short",
      year: "numeric",
      hour: "2-digit",
      minute: "2-digit",
      hour12: true,
    });
  } catch {
    return String(dateInput);
  }
}

function formatISTTimeOnly(dateInput) {
  if (!dateInput) return "";
  try {
    let s = String(dateInput).trim();
    if (!s.includes("Z") && !s.includes("+") && !/[+-]\d{2}:\d{2}$/.test(s)) {
      s = s.replace(" ", "T") + "+05:30";
    }
    const d = new Date(s);
    if (isNaN(d.getTime())) return "";
    return d.toLocaleTimeString("en-IN", {
      timeZone: "Asia/Kolkata",
      hour: "numeric",
      minute: "2-digit",
      hour12: true,
    });
  } catch {
    return "";
  }
}

function isOrderActive(order) {
  const s = (order.order_status || "").toLowerCase().trim();
  return !(s === "collected" || s === "completed" || s === "cancelled" || s === "rejected");
}

function getCollectionMessage(order) {
  const timeStr = order.readable_collection_time || formatISTTimeOnly(order.estimated_collection_time) || "soon";
  const orderType = order.order_type || (
    ((order.has_files || (order.files && order.files.length > 0) || (order.items && order.items.length > 0) || order.document_name) &&
     ((order.stationery_items_list && order.stationery_items_list.length > 0) || (order.stationery_items && order.stationery_items.length > 0)))
      ? "printing_and_stationery"
      : ((order.stationery_items_list && order.stationery_items_list.length > 0) || (order.stationery_items && order.stationery_items.length > 0) || order.order_type === "stationery")
        ? "stationery_only"
        : "printing_only"
  );

  const isReady = ["ready for collection", "stage ready", "ready"].includes((order.order_status || "").toLowerCase().trim());
  if (isReady) {
    if (orderType === "stationery_only") {
      return "Your stationery is ready for collection!";
    } else if (orderType === "printing_and_stationery" || orderType === "mixed") {
      return "Your print and stationery are ready for collection!";
    } else {
      return "Your print is ready for collection!";
    }
  }

  if (orderType === "stationery_only" || orderType === "stationery") {
    return `Please collect your stationery at ${timeStr}.`;
  } else if (orderType === "printing_and_stationery" || orderType === "mixed") {
    return `Please collect your print and stationery at ${timeStr}.`;
  } else {
    return `Please collect your print at ${timeStr}.`;
  }
}

function getBadgeClass(status) {
  const map = {
    "payment successful": "badge-ready",
    "payment verified": "badge-ready",
    "received": "badge-received",
    "order received": "badge-received",
    "order placed": "badge-received",
    "in queue": "badge-received",
    "processing": "badge-processing",
    "printing in progress": "badge-processing",
    "preparing stationery": "badge-processing",
    "stage ready": "badge-ready",
    "ready for collection": "badge-ready",
    "ready": "badge-ready",
    "completed": "badge-completed",
    "collected": "badge-completed",
    "rejected": "badge-rejected",
    "cancelled": "badge-rejected",
  };
  return "badge " + (map[status?.toLowerCase()] || "badge-received");
}

function StatusBadge({ status }) {
  const s = (status || "").toLowerCase().trim();
  let icon = <Clock size={14} />;
  if (s === "completed" || s === "collected" || s === "payment verified" || s === "payment successful") {
    icon = <CheckCircle size={14} />;
  } else if (s === "processing" || s === "printing in progress" || s === "preparing stationery") {
    icon = <Loader size={14} className="spin-icon" />;
  } else if (s === "ready for collection" || s === "stage ready" || s === "ready") {
    icon = <Package size={14} />;
  } else if (s === "rejected" || s === "cancelled") {
    icon = <XCircle size={14} />;
  }

  return (
    <span className={getBadgeClass(status)}>
      {icon}
      {status}
    </span>
  );
}

// ── Live Countdown Component ──────────────────────────────────────────────────
function LiveCountdown({ estimatedCollectionTime, status }) {
  const isReady = ["ready for collection", "stage ready", "ready"].includes((status || "").toLowerCase().trim());

  const getRemainingSeconds = useCallback(() => {
    if (!estimatedCollectionTime) return 0;
    let s = String(estimatedCollectionTime).trim();
    if (!s.includes("Z") && !s.includes("+") && !/[+-]\d{2}:\d{2}$/.test(s)) {
      s = s.replace(" ", "T") + "+05:30";
    }
    const targetMs = new Date(s).getTime();
    if (isNaN(targetMs)) return 0;
    return Math.max(0, Math.floor((targetMs - Date.now()) / 1000));
  }, [estimatedCollectionTime]);

  const [secondsLeft, setSecondsLeft] = useState(getRemainingSeconds);

  useEffect(() => {
    setSecondsLeft(getRemainingSeconds());
    if (isReady || !estimatedCollectionTime) return;

    const interval = setInterval(() => {
      setSecondsLeft(getRemainingSeconds());
    }, 1000);

    return () => clearInterval(interval);
  }, [estimatedCollectionTime, isReady, getRemainingSeconds]);

  if (isReady) {
    return (
      <span className="order-token-badge" style={{ background: "#ecfdf5", color: "#065f46", borderColor: "#a7f3d0" }}>
        Ready at counter
      </span>
    );
  }

  const formatTimer = (totalSec) => {
    if (totalSec <= 0) return "00:00";
    const h = Math.floor(totalSec / 3600);
    const m = Math.floor((totalSec % 3600) / 60);
    const s = totalSec % 60;
    const pad = (n) => String(n).padStart(2, "0");
    if (h > 0) {
      return `${pad(h)}:${pad(m)}:${pad(s)}`;
    }
    return `${pad(m)}:${pad(s)}`;
  };

  return (
    <div className={`eta-countdown-pill ${secondsLeft === 0 ? "finishing" : ""}`}>
      <Clock size={16} />
      <span>{secondsLeft > 0 ? formatTimer(secondsLeft) : "00:00"}</span>
      {secondsLeft === 0 && (
        <span style={{ fontSize: ".72rem", color: "#fef08a", fontWeight: 600 }}>
          (Finishing up)
        </span>
      )}
    </div>
  );
}

// ── Progress Tracker Component ────────────────────────────────────────────────
function StageTracker({ status, isPaid }) {
  const currentStageIndex = getStageIndex(status, isPaid);
  const isCancelled = currentStageIndex === -1;

  if (isCancelled) {
    return (
      <div className="alert alert-error" style={{ margin: "16px 0", padding: "10px 16px" }}>
        <XCircle size={18} style={{ flexShrink: 0 }} />
        <div>
          <strong>Order Cancelled / Rejected</strong>
          <div style={{ fontSize: ".82rem", marginTop: 2 }}>This order has been cancelled and is no longer being processed.</div>
        </div>
      </div>
    );
  }

  // Progress percentage for background line
  const fillPct = Math.min(100, Math.max(0, (currentStageIndex / (PROGRESS_STAGES.length - 1)) * 100));

  return (
    <div className="order-stage-tracker">
      <div className="stage-steps-row">
        <div className="stage-progress-bar-bg" />
        <div className="stage-progress-bar-fill" style={{ width: `${fillPct}%` }} />
        {PROGRESS_STAGES.map((st, idx) => {
          const isDone = idx < currentStageIndex;
          const isActive = idx === currentStageIndex;
          return (
            <div
              key={st.key}
              className={`stage-step-item ${isDone ? "completed" : ""} ${isActive ? "active" : ""}`}
            >
              <div className="stage-step-circle">
                {isDone ? <CheckCircle size={15} /> : idx + 1}
              </div>
              <div className="stage-step-label">{st.label}</div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

// ── Active Order Card ─────────────────────────────────────────────────────────
function ActiveOrderCard({ order }) {
  const isPaid = (order.payment_status || "").toLowerCase() === "completed" ||
                 (order.payment_status || "").toLowerCase() === "verified" ||
                 (order.payment_status || "").toLowerCase() === "paid" ||
                 (order.payment_status || "").toLowerCase() === "demo_paid";

  const isReady = ["ready for collection", "stage ready", "ready"].includes((order.order_status || "").toLowerCase().trim());
  const collectionMessage = getCollectionMessage(order);
  const readableEta = order.readable_collection_time || formatISTTimeOnly(order.estimated_collection_time);

  // Extract items
  const documentList = (order.items && order.items.length > 0)
    ? order.items
    : (order.document_name ? [{
        document_name: order.document_name,
        pages: order.pages,
        copies: order.copies,
        color_mode: order.color_mode,
        side_mode: order.side_mode,
        calculated_sheets: order.calculated_sheets,
        item_total: order.printing_total || order.total_price
      }] : []);

  const stationeryList = order.stationery_items_list || order.stationery_items || [];

  const orderType = order.order_type === "stationery" || (!order.has_files && stationeryList.length > 0 && documentList.length === 0)
    ? "Stationery"
    : (stationeryList.length > 0 && documentList.length > 0) || order.order_type === "mixed"
    ? "Printing + Stationery"
    : "Printing";

  return (
    <div className="active-order-card animate-fade">
      {/* Top Bar: Order number, Token, Type, Placement Time, Status */}
      <div className="active-order-topbar">
        <div>
          <div className="order-num-tag">
            <span>Order #{order.display_order_number || order.id}</span>
            <span className="order-token-badge">Token: {order.token_number}</span>
            <span className="order-type-chip">{orderType}</span>
          </div>
          <div style={{ fontSize: ".82rem", color: "var(--text-muted)", marginTop: 4, display: "flex", alignItems: "center", gap: 6 }}>
            <Calendar size={13} /> Placed on {formatISTDateTime(order.created_at)}
          </div>
        </div>
        <StatusBadge status={order.order_status} />
      </div>

      {/* ETA & Countdown Banner */}
      <div className={`eta-countdown-card ${isReady ? "ready-state" : ""}`}>
        <div>
          <div className={`collection-instruction-text ${isReady ? "ready" : ""}`}>
            {isReady ? <CheckCircle size={18} /> : <Clock size={18} />}
            <span>{collectionMessage}</span>
          </div>
          {!isReady && (
            <div style={{ fontSize: ".8rem", color: "#64748b", marginTop: 4 }}>
              Live queue estimate updated based on counter workload.
            </div>
          )}
        </div>

        <div className="eta-timer-display">
          {!isReady && (
            <div className="eta-timer-sub">
              <span className="eta-timer-label">Estimated Collection</span>
              <span className="eta-timer-clock">{readableEta || "Calculating…"}</span>
            </div>
          )}
          <div>
            {!isReady && <span className="eta-timer-label" style={{ marginBottom: 4 }}>Time remaining</span>}
            <LiveCountdown estimatedCollectionTime={order.estimated_collection_time} status={order.order_status} />
          </div>
        </div>
      </div>

      {/* Progress Stages */}
      <StageTracker status={order.order_status} isPaid={isPaid} />

      {/* Items Ordered — Distinct Multi-PDF breakdown */}
      {documentList.length > 0 && (
        <div className="card-items-block">
          <div className="card-items-title">
            <FileText size={16} color="var(--primary)" />
            <span>Printing Documents ({documentList.length})</span>
          </div>
          {documentList.map((doc, idx) => (
            <div key={idx} className="file-entry-row">
              <div>
                <div className="file-entry-name">
                  <Printer size={14} color="var(--primary)" />
                  <span>{doc.document_name}</span>
                </div>
                <div className="file-entry-meta">
                  <span><strong>{doc.copies}</strong> {doc.copies === 1 ? "copy" : "copies"}</span>
                  <span>·</span>
                  <span>{doc.pages} pages ({doc.calculated_sheets || Math.ceil(doc.pages / (doc.side_mode === "double" ? 2 : 1))} sheets)</span>
                  <span>·</span>
                  <span>{doc.color_mode === "color" ? "Full Color" : "Black & White"}</span>
                  <span>·</span>
                  <span>{doc.side_mode === "double" ? "Double-sided" : "Single-sided"}</span>
                </div>
              </div>
              {doc.item_total != null && (
                <div style={{ fontWeight: 700, fontSize: ".9rem", color: "var(--text-main)" }}>
                  ₹{Number(doc.item_total).toFixed(2)}
                </div>
              )}
            </div>
          ))}
        </div>
      )}

      {/* Stationery Items */}
      {stationeryList.length > 0 && (
        <div className="card-items-block">
          <div className="card-items-title">
            <ShoppingBag size={16} color="var(--primary)" />
            <span>Stationery Items ({stationeryList.length})</span>
          </div>
          {stationeryList.map((st, idx) => (
            <div key={idx} className="file-entry-row">
              <div>
                <span style={{ fontWeight: 700, fontSize: ".88rem" }}>{st.quantity}x</span> {st.name}
                <span style={{ fontSize: ".76rem", color: "var(--text-muted)", marginLeft: 8 }}>
                  (₹{st.price} each)
                </span>
              </div>
              <div style={{ fontWeight: 700, fontSize: ".9rem", color: "var(--text-main)" }}>
                ₹{Number(st.subtotal).toFixed(2)}
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Order Summary & Payment Info */}
      <div style={{
        display: "flex", justifyContent: "space-between", alignItems: "center",
        flexWrap: "wrap", gap: 12, paddingTop: 14, borderTop: "1px solid var(--border)", fontSize: ".86rem"
      }}>
        <div style={{ display: "flex", gap: 14, flexWrap: "wrap", color: "var(--text-muted)" }}>
          <span>Student: <strong style={{ color: "var(--text-main)" }}>{order.student_name} ({order.roll_number})</strong></span>
          <span>Payment: <strong style={{ color: isPaid ? "#047857" : "#b45309" }}>{isPaid ? "Paid (UPI)" : "Pending"}</strong></span>
        </div>
        <div style={{ fontSize: "1.05rem", fontWeight: 800, color: "var(--primary)" }}>
          Total: ₹{Number(order.total_price).toFixed(2)}
        </div>
      </div>
    </div>
  );
}

// ── Collapsible Previous Order Row ────────────────────────────────────────────
function PreviousOrderRow({ order }) {
  const [isExpanded, setIsExpanded] = useState(false);

  const documentList = (order.items && order.items.length > 0)
    ? order.items
    : (order.document_name ? [{
        document_name: order.document_name,
        pages: order.pages,
        copies: order.copies,
        color_mode: order.color_mode,
        side_mode: order.side_mode,
        calculated_sheets: order.calculated_sheets,
        item_total: order.printing_total || order.total_price
      }] : []);

  const stationeryList = order.stationery_items_list || order.stationery_items || [];

  // Summary label
  const summaryParts = [];
  if (documentList.length > 0) {
    summaryParts.push(`${documentList.length} print ${documentList.length === 1 ? "file" : "files"} (${documentList.map(d => d.document_name).join(", ")})`);
  }
  if (stationeryList.length > 0) {
    summaryParts.push(`${stationeryList.reduce((acc, s) => acc + (s.quantity || 1), 0)} stationery items`);
  }
  const summaryText = summaryParts.join(" + ") || "CampusPrint Order";

  const isCollected = (order.order_status || "").toLowerCase() === "collected" || (order.order_status || "").toLowerCase() === "completed";
  const isCancelled = (order.order_status || "").toLowerCase() === "cancelled" || (order.order_status || "").toLowerCase() === "rejected";

  return (
    <div className="history-order-accordion">
      <div className="history-accordion-header" onClick={() => setIsExpanded(!isExpanded)}>
        <div className="history-header-left">
          <div className="history-header-title">
            <span>Order #{order.display_order_number || order.id}</span>
            <span style={{ fontSize: ".82rem", color: "var(--text-muted)", fontWeight: 500 }}>
              (Token: {order.token_number})
            </span>
            <span style={{ fontSize: ".8rem", color: "#64748b", fontWeight: 400 }}>
              · {formatISTDateTime(order.created_at)}
            </span>
          </div>
          <div className="history-header-summary">
            {summaryText} · <strong>₹{Number(order.total_price).toFixed(2)}</strong>
          </div>
        </div>
        <div className="history-header-right">
          {isCollected && (
            <span className="badge badge-completed">
              <CheckCircle size={13} /> Collected
            </span>
          )}
          {isCancelled && (
            <span className="badge badge-rejected">
              <XCircle size={13} /> Cancelled
            </span>
          )}
          {!isCollected && !isCancelled && (
            <StatusBadge status={order.order_status} />
          )}
          {isExpanded ? <ChevronUp size={18} color="var(--text-muted)" /> : <ChevronDown size={18} color="var(--text-muted)" />}
        </div>
      </div>

      {isExpanded && (
        <div className="history-accordion-body animate-fade">
          {/* Print items */}
          {documentList.length > 0 && (
            <div style={{ marginBottom: 14 }}>
              <div style={{ fontWeight: 700, fontSize: ".86rem", color: "var(--text-main)", marginBottom: 8, display: "flex", alignItems: "center", gap: 6 }}>
                <Printer size={15} color="var(--primary)" /> Printed Documents ({documentList.length})
              </div>
              <div style={{ background: "#fff", border: "1px solid var(--border)", borderRadius: "var(--radius-sm)", padding: "10px 14px" }}>
                {documentList.map((doc, idx) => (
                  <div key={idx} style={{
                    padding: "6px 0",
                    borderBottom: idx < documentList.length - 1 ? "1px solid var(--border)" : "none",
                    display: "flex", justifyContent: "space-between", alignItems: "center", fontSize: ".84rem"
                  }}>
                    <div>
                      <div style={{ fontWeight: 700, color: "var(--text-main)" }}>{doc.document_name}</div>
                      <div style={{ fontSize: ".76rem", color: "var(--text-muted)", marginTop: 2 }}>
                        {doc.copies} {doc.copies === 1 ? "copy" : "copies"} · {doc.pages} pages · {doc.color_mode === "color" ? "Color" : "B&W"} · {doc.side_mode === "double" ? "Double-sided" : "Single-sided"}
                      </div>
                    </div>
                    {doc.item_total != null && (
                      <span style={{ fontWeight: 700 }}>₹{Number(doc.item_total).toFixed(2)}</span>
                    )}
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Stationery items */}
          {stationeryList.length > 0 && (
            <div style={{ marginBottom: 14 }}>
              <div style={{ fontWeight: 700, fontSize: ".86rem", color: "var(--text-main)", marginBottom: 8, display: "flex", alignItems: "center", gap: 6 }}>
                <ShoppingBag size={15} color="var(--primary)" /> Stationery Items ({stationeryList.length})
              </div>
              <div style={{ background: "#fff", border: "1px solid var(--border)", borderRadius: "var(--radius-sm)", padding: "10px 14px" }}>
                {stationeryList.map((st, idx) => (
                  <div key={idx} style={{
                    padding: "6px 0",
                    borderBottom: idx < stationeryList.length - 1 ? "1px solid var(--border)" : "none",
                    display: "flex", justifyContent: "space-between", alignItems: "center", fontSize: ".84rem"
                  }}>
                    <div>
                      <span style={{ fontWeight: 700 }}>{st.quantity}x</span> {st.name}
                      <span style={{ fontSize: ".76rem", color: "var(--text-muted)", marginLeft: 6 }}>(₹{st.price} each)</span>
                    </div>
                    <span style={{ fontWeight: 700 }}>₹{Number(st.subtotal).toFixed(2)}</span>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Details summary footer */}
          <div style={{
            display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(140px, 1fr))",
            gap: 12, padding: "10px 14px", background: "#fff", border: "1px solid var(--border)",
            borderRadius: "var(--radius-sm)", fontSize: ".82rem"
          }}>
            <div>
              <span style={{ color: "var(--text-muted)", display: "block" }}>Order ID</span>
              <strong style={{ color: "var(--text-main)" }}>{order.order_id}</strong>
            </div>
            <div>
              <span style={{ color: "var(--text-muted)", display: "block" }}>Payment</span>
              <strong style={{ color: "var(--text-main)" }}>
                {order.payment_status ? `UPI (${order.payment_status})` : "UPI"}
              </strong>
            </div>
            <div>
              <span style={{ color: "var(--text-muted)", display: "block" }}>Final Status</span>
              <strong style={{ color: "var(--text-main)" }}>{order.order_status}</strong>
            </div>
            <div>
              <span style={{ color: "var(--text-muted)", display: "block" }}>Total Paid</span>
              <strong style={{ color: "var(--primary)", fontSize: ".95rem" }}>
                ₹{Number(order.total_price).toFixed(2)}
              </strong>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

// ── Main TrackOrder Page ──────────────────────────────────────────────────────
export default function TrackOrder() {
  const [query, setQuery] = useState("");
  const [loading, setLoading] = useState(false);
  const [searchedCustomer, setSearchedCustomer] = useState(null);
  const [orders, setOrders] = useState(null);
  const [error, setError] = useState(null);

  const fetchOrders = useCallback(async (q, isBackground = false) => {
    if (!q) return;
    if (!isBackground) {
      setLoading(true);
      setError(null);
    }
    try {
      const res = await fetch(`${API}/orders/track/${encodeURIComponent(q)}`);
      const data = await res.json();
      if (data.success) {
        setOrders(data.orders || []);
        setSearchedCustomer(q);
      } else {
        if (!isBackground) {
          setError(data.message || "No orders found.");
          setOrders([]);
        }
      }
    } catch {
      if (!isBackground) {
        setError("Could not reach server. Please check your connection.");
      }
    } finally {
      if (!isBackground) {
        setLoading(false);
      }
    }
  }, []);

  function handleSearch(e) {
    e.preventDefault();
    const q = query.trim();
    if (!q) return;
    fetchOrders(q, false);
  }

  // Active orders polling: synchronize ETAs if queue changes
  useEffect(() => {
    if (!searchedCustomer || !orders) return;
    const hasActive = orders.some(isOrderActive);
    if (!hasActive) return;

    const interval = setInterval(() => {
      fetchOrders(searchedCustomer, true);
    }, 12000); // Poll every 12 seconds

    return () => clearInterval(interval);
  }, [searchedCustomer, orders, fetchOrders]);

  // Partition customer orders
  const activeOrders = orders ? orders.filter(isOrderActive) : [];
  const historyOrders = orders ? orders.filter(o => !isOrderActive(o)) : [];

  return (
    <div className="container" style={{ padding: "40px 20px 60px", maxWidth: 840, margin: "0 auto" }}>
      {/* Header */}
      <div className="track-page-header">
        <h1 className="track-page-title">Track My Order</h1>
        <p className="track-page-subtitle">
          Enter your Roll Number or Token Number to view live order progress and collection timings.
        </p>
      </div>

      {/* Search Input Box */}
      <form onSubmit={handleSearch} className="track-search-box">
        <Search size={20} color="var(--primary)" />
        <input
          className="track-search-input"
          placeholder="Enter Token (e.g. TK-101), Roll Number, or Order ID…"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
        />
        <button
          className="btn btn-primary"
          type="submit"
          disabled={loading || !query.trim()}
          style={{ borderRadius: "var(--radius-lg)", padding: "10px 22px", flexShrink: 0 }}
        >
          {loading ? <Loader size={18} className="spin-icon" /> : "Track Order"}
        </button>
      </form>

      {/* Error state */}
      {error && (
        <div className="alert alert-error animate-fade" style={{ marginBottom: 24 }}>
          <AlertCircle size={18} style={{ flexShrink: 0 }} />
          <div>{error}</div>
        </div>
      )}

      {/* Empty result state */}
      {orders && orders.length === 0 && !error && (
        <div className="card text-center animate-fade" style={{ padding: "48px 24px", marginBottom: 32 }}>
          <Package size={44} color="#94a3b8" style={{ margin: "0 auto 16px" }} />
          <h3 style={{ fontSize: "1.2rem", fontWeight: 700, marginBottom: 8 }}>No orders found</h3>
          <p style={{ color: "var(--text-muted)", fontSize: ".92rem", maxWidth: 420, margin: "0 auto" }}>
            We could not find any orders matching <strong>"{searchedCustomer}"</strong>. Please verify your token or roll number and try again.
          </p>
        </div>
      )}

      {/* Prominent Active Orders Section */}
      {activeOrders.length > 0 && (
        <div className="active-orders-section">
          <div className="section-title-row">
            <h2 className="section-title">
              <span>Active Orders</span>
              <span className="count-badge-active">{activeOrders.length}</span>
            </h2>
            <span style={{ fontSize: ".82rem", color: "var(--text-muted)", display: "flex", alignItems: "center", gap: 5 }}>
              <Sparkles size={14} color="var(--primary)" /> Live updates enabled
            </span>
          </div>

          {activeOrders.map((order) => (
            <ActiveOrderCard key={order.order_id || order.id} order={order} />
          ))}
        </div>
      )}

      {/* When no active orders exist, but history exists */}
      {orders && orders.length > 0 && activeOrders.length === 0 && (
        <div className="alert alert-success animate-fade" style={{ marginBottom: 28, padding: "16px 20px" }}>
          <CheckCircle size={20} style={{ flexShrink: 0, marginTop: 2 }} />
          <div>
            <strong>You have no active orders in queue!</strong>
            <div style={{ fontSize: ".88rem", marginTop: 4 }}>
              All your previous orders have been completed or collected. You can inspect your past orders below.
            </div>
          </div>
        </div>
      )}

      {/* Compact Collapsible Previous Orders / Order History */}
      {historyOrders.length > 0 && (
        <div className="previous-orders-container">
          <div className="section-title-row">
            <h2 className="section-title">
              <span>Order History</span>
              <span className="count-badge-muted">{historyOrders.length}</span>
            </h2>
            <span style={{ fontSize: ".82rem", color: "var(--text-muted)" }}>
              Click an order to view full details
            </span>
          </div>

          {historyOrders.map((order) => (
            <PreviousOrderRow key={order.order_id || order.id} order={order} />
          ))}
        </div>
      )}
    </div>
  );
}
