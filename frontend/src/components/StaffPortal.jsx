import { useState, useEffect, useCallback, Fragment } from "react";
import {
  ShieldCheck, LogOut, RefreshCw, Search, ExternalLink,
  CheckCircle, Clock, Loader, Package, XCircle, AlertTriangle, ShoppingBag, FileText
} from "lucide-react";

const STATUSES = ["All", "Order Received", "Printing in Progress", "Preparing Stationery", "Stage Ready", "Ready for Collection", "Collected", "Completed", "Rejected"];

function getBadgeClass(status) {
  const map = {
    "payment successful": "badge-ready",
    received: "badge-received",
    "order received": "badge-received",
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

function formatISTTime(dateInput) {
  if (!dateInput) return "—";
  try {
    let s = String(dateInput).trim();
    if (!s.includes("Z") && !s.includes("+") && !/[+-]\d{2}:\d{2}$/.test(s)) {
      s = s.replace(" ", "T") + "+05:30";
    }
    const d = new Date(s);
    if (isNaN(d.getTime())) return String(dateInput);
    return d.toLocaleTimeString("en-IN", {
      timeZone: "Asia/Kolkata",
      hour: "2-digit",
      minute: "2-digit",
      hour12: true,
    });
  } catch {
    return String(dateInput);
  }
}

function StatCard({ value, label, color }) {
  return (
    <div className="stat-card">
      <div className="stat-value" style={color ? { color } : undefined}>{value}</div>
      <div className="stat-label">{label}</div>
    </div>
  );
}

/* ── Login form ── */
function LoginForm({ onLogin }) {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  async function handleSubmit(e) {
    e.preventDefault();
    if (!username || !password) { setError("Enter username and password."); return; }
    setLoading(true); setError(null);
    try {
      const res = await fetch("https://campusprint-syv1.onrender.com/api/staff/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ username, password }),
      });
      const data = await res.json();
      if (data.success) {
        onLogin(data.user, data.token);
      } else {
        setError(data.error || "Invalid credentials.");
      }
    } catch {
      setError("Cannot reach server.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="container" style={{ padding: "60px 20px", maxWidth: 400, margin: "0 auto" }}>
      <div className="card">
        <div style={{ textAlign: "center", marginBottom: 28 }}>
          <div style={{ display: "flex", justifyContent: "center", marginBottom: 12 }}>
            <div className="logo-badge"><ShieldCheck size={22} /></div>
          </div>
          <h2 style={{ fontSize: "1.5rem", fontWeight: 800, marginBottom: 4 }}>Staff Portal</h2>
          <p style={{ color: "var(--text-muted)", fontSize: ".88rem" }}>
            Sign in to manage orders
          </p>
        </div>

        {error && <div className="alert alert-error" style={{ marginBottom: 16 }}>{error}</div>}

        <form onSubmit={handleSubmit}>
          <div className="form-group">
            <label className="form-label">Username</label>
            <input className="form-input" value={username} onChange={(e) => setUsername(e.target.value)} placeholder="Enter username" />
          </div>
          <div className="form-group">
            <label className="form-label">Password</label>
            <input className="form-input" type="password" value={password} onChange={(e) => setPassword(e.target.value)} placeholder="••••••••" />
          </div>
          <button className="btn btn-primary w-full" type="submit" disabled={loading}>
            {loading ? <><div className="loading-spinner" /> Signing in…</> : "Sign In"}
          </button>
        </form>
      </div>
    </div>
  );
}

/* ── Order row action buttons ── */
function OrderActions({ order, onStatusUpdate }) {
  const [loading, setLoading] = useState(false);
  const [rejReason, setRejReason] = useState("");
  const [showRejectPrompt, setShowRejectPrompt] = useState(false);

  async function updateStatus(newStatus, rejectionReason) {
    setLoading(true);
    try {
      const res = await fetch(`https://campusprint-syv1.onrender.com/api/staff/orders/${order.order_id}/status`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ status: newStatus, rejection_reason: rejectionReason }),
      });
      const data = await res.json();
      if (data.success) onStatusUpdate(data.order);
    } catch { /* silent */ }
    finally { setLoading(false); setShowRejectPrompt(false); }
  }

  const st = (order.order_status || "").trim();
  if (st === "Completed" || st === "Collected" || st === "Rejected") return null;

  const isStationery = order.order_type === "stationery";
  const isReceived = st === "Received" || st === "Order Received" || st === "Payment Successful";
  const isProcessing = st === "Processing" || st === "Printing in Progress" || st === "Preparing Stationery";
  const isReady = st === "Ready for Collection" || st === "Ready" || st === "Stage Ready";
  const isStageReady = st === "Stage Ready";

  return (
    <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
      {isReceived && (
        isStationery ? (
          <button className="btn btn-primary btn-sm" onClick={() => updateStatus("Preparing Stationery")} disabled={loading}>
            {loading ? <Loader size={14} className="spin-icon" /> : null} Start Preparing
          </button>
        ) : (
          <button className="btn btn-primary btn-sm" onClick={() => updateStatus("Printing in Progress")} disabled={loading}>
            {loading ? <Loader size={14} className="spin-icon" /> : null} Start Printing
          </button>
        )
      )}
      {isProcessing && (
        <>
          <button className="btn btn-success btn-sm" onClick={() => updateStatus("Stage Ready")} disabled={loading} title="Mark as Stage Ready Items">
            <Package size={14} /> Stage Ready
          </button>
          <button className="btn btn-success btn-sm" onClick={() => updateStatus("Ready for Collection")} disabled={loading}>
            Mark Ready
          </button>
        </>
      )}
      {isStageReady && (
        <button className="btn btn-success btn-sm" onClick={() => updateStatus("Ready for Collection")} disabled={loading}>
          Ready for Collection
        </button>
      )}
      {isReady && (
        <button className="btn btn-success btn-sm" onClick={() => updateStatus("Collected")} disabled={loading}>
          <CheckCircle size={14} /> Handed Over
        </button>
      )}
      {!showRejectPrompt && (
        <button className="btn btn-danger btn-sm" onClick={() => setShowRejectPrompt(true)} disabled={loading}>
          <XCircle size={14} /> Reject
        </button>
      )}
      {showRejectPrompt && (
        <div style={{ width: "100%", display: "flex", gap: 8, flexWrap: "wrap", marginTop: 4 }}>
          <input
            className="form-input"
            style={{ flex: 1, fontSize: ".82rem", padding: "6px 10px" }}
            placeholder="Rejection reason…"
            value={rejReason}
            onChange={(e) => setRejReason(e.target.value)}
          />
          <button className="btn btn-danger btn-sm" onClick={() => updateStatus("Rejected", rejReason)} disabled={loading}>
            Confirm
          </button>
          <button className="btn btn-outline btn-sm" onClick={() => setShowRejectPrompt(false)}>Cancel</button>
        </div>
      )}
    </div>
  );
}

/* ── Main staff dashboard ── */
export default function StaffPortal() {
  const [user, setUser] = useState(null);
  const [stats, setStats] = useState(null);
  const [orders, setOrders] = useState([]);
  const [loadingOrders, setLoadingOrders] = useState(false);
  const [statusFilter, setStatusFilter] = useState("All");
  const [searchQuery, setSearchQuery] = useState("");
  const [expandedOrderId, setExpandedOrderId] = useState(null);

  /* Auto-refresh every 8 seconds */
  const fetchOrders = useCallback(async (status, search) => {
    setLoadingOrders(true);
    try {
      const params = new URLSearchParams();
      if (status && status !== "All") params.set("status", status);
      if (search) params.set("search", search);
      const [ordersRes, statsRes] = await Promise.all([
        fetch(`https://campusprint-syv1.onrender.com/api/staff/orders?${params}`),
        fetch("https://campusprint-syv1.onrender.com/api/staff/stats"),
      ]);
      const [ordersData, statsData] = await Promise.all([ordersRes.json(), statsRes.json()]);
      if (ordersData.success) setOrders(ordersData.orders);
      if (statsData.success) setStats(statsData.stats);
    } catch { /* silent */ }
    finally { setLoadingOrders(false); }
  }, []);

  useEffect(() => {
    if (!user) return;
    fetchOrders(statusFilter, searchQuery);
    const interval = setInterval(() => fetchOrders(statusFilter, searchQuery), 8000);
    return () => clearInterval(interval);
  }, [user, statusFilter, searchQuery, fetchOrders]);

  function handleStatusUpdate(updatedOrder) {
    setOrders((prev) => prev.map((o) => o.order_id === updatedOrder.order_id ? updatedOrder : o));
  }

  if (!user) {
    return <LoginForm onLogin={(u) => setUser(u)} />;
  }

  return (
    <div className="container" style={{ padding: "32px 20px 60px" }}>
      {/* Header */}
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 28, flexWrap: "wrap", gap: 12 }}>
        <div>
          <h2 style={{ fontSize: "1.6rem", fontWeight: 800, marginBottom: 2 }}>Staff Dashboard</h2>
          <p style={{ color: "var(--text-muted)", fontSize: ".88rem" }}>
            Logged in as <strong>{user.username}</strong> · {user.role}
          </p>
        </div>
        <div style={{ display: "flex", gap: 10 }}>
          <button className="btn btn-outline btn-sm" onClick={() => fetchOrders(statusFilter, searchQuery)} disabled={loadingOrders}>
            <RefreshCw size={14} className={loadingOrders ? "spin-icon" : ""} /> Refresh
          </button>
          <button className="btn btn-outline btn-sm" onClick={() => setUser(null)}>
            <LogOut size={14} /> Log Out
          </button>
        </div>
      </div>

      {/* Stats */}
      {stats && (
        <div className="stat-cards">
          <StatCard value={stats.total_orders} label="Total Orders" />
          <StatCard value={stats.received} label="Received" color="var(--status-received)" />
          <StatCard value={stats.processing} label="Processing" color="#b45309" />
          <StatCard value={stats.ready} label="Ready" color="#047857" />
          <StatCard value={stats.completed} label="Completed" color="#4338ca" />
          <StatCard value={`₹${stats.total_revenue}`} label="Revenue" color="var(--primary)" />
        </div>
      )}

      {/* Filters */}
      <div style={{ display: "flex", gap: 12, marginBottom: 20, flexWrap: "wrap", alignItems: "center" }}>
        <div style={{ position: "relative", flex: 1, minWidth: 200 }}>
          <Search size={16} style={{ position: "absolute", left: 12, top: "50%", transform: "translateY(-50%)", color: "var(--text-muted)" }} />
          <input
            className="form-input"
            style={{ paddingLeft: 36 }}
            placeholder="Search name, roll, token, order ID…"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
          />
        </div>
        <select
          className="form-select"
          style={{ width: "auto" }}
          value={statusFilter}
          onChange={(e) => setStatusFilter(e.target.value)}
        >
          {STATUSES.map((s) => <option key={s}>{s}</option>)}
        </select>
      </div>

      {/* Table */}
      {orders.length === 0 && !loadingOrders ? (
        <div className="alert alert-info">No orders match your filter.</div>
      ) : (
        <div className="staff-table-wrapper" style={{ overflowX: "auto" }}>
          <table className="staff-table">
            <thead>
              <tr>
                <th>Order #</th>
                <th>Token</th>
                <th>Student</th>
                <th>Document / Items</th>
                <th>Pages × Copies</th>
                <th>Amount</th>
                <th>Status</th>
                <th>Actions</th>
                <th>Time</th>
              </tr>
            </thead>
            <tbody>
              {orders.map((order) => {
                const isStationeryOnly = order.order_type === "stationery";
                const isMixed = order.order_type === "mixed";
                const stationeryList = order.stationery_items || [];

                return (
                  <Fragment key={order.order_id}>
                    <tr
                      style={{ cursor: "pointer" }}
                      onClick={() => setExpandedOrderId(expandedOrderId === order.order_id ? null : order.order_id)}
                    >
                      <td style={{ fontWeight: 800, color: "var(--text-main)" }}>
                        #{order.display_order_number || order.id}
                        <div style={{
                          fontSize: ".72rem",
                          color: isStationeryOnly ? "#0284c7" : isMixed ? "#7c3aed" : "var(--primary)",
                          fontWeight: 700, marginTop: 2
                        }}>
                          {isStationeryOnly ? "Stationery" : isMixed ? "Mixed" : "Print"}
                        </div>
                      </td>
                      <td style={{ fontWeight: 700, color: "var(--primary)" }}>{order.token_number}</td>
                      <td>
                        <div style={{ fontWeight: 600 }}>{order.student_name}</div>
                        <div style={{ fontSize: ".78rem", color: "var(--text-muted)" }}>{order.roll_number}</div>
                      </td>
                      <td>
                        {isStationeryOnly ? (
                          <>
                            <div style={{ maxWidth: 170, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", fontWeight: 600 }}>
                              <ShoppingBag size={13} style={{ display: "inline", marginRight: 4 }} />
                              {stationeryList.length} stationery item{stationeryList.length !== 1 ? "s" : ""}
                            </div>
                            <div style={{ fontSize: ".76rem", color: "var(--text-muted)", maxWidth: 170, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                              {stationeryList.map(it => `${it.quantity}x ${it.name}`).join(", ") || "Stationery"}
                            </div>
                          </>
                        ) : isMixed ? (
                          <>
                            <div style={{ maxWidth: 170, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                              {order.document_name || "Documents"}
                            </div>
                            <div style={{ fontSize: ".76rem", color: "#7c3aed", fontWeight: 600 }}>
                              + {stationeryList.length} stationery item(s)
                            </div>
                          </>
                        ) : (
                          <>
                            <div style={{ maxWidth: 170, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                              {order.document_name}
                            </div>
                            <div style={{ fontSize: ".78rem", color: "var(--text-muted)" }}>
                              {order.color_mode === "color" ? "Color" : "B&W"} · {order.side_mode === "double" ? "Duplex" : "Single"}
                            </div>
                          </>
                        )}
                      </td>
                      <td>
                        {isStationeryOnly ? (
                          <span style={{ color: "var(--text-muted)", fontSize: ".82rem" }}>—</span>
                        ) : (
                          `${order.pages || order.print_pages_total || 1} × ${order.copies || 1} = ${order.calculated_sheets || Math.ceil((order.pages || 1) / (order.side_mode === "double" ? 2 : 1)) * (order.copies || 1)} sh`
                        )}
                      </td>
                      <td style={{ fontWeight: 700 }}>₹{order.total_price}</td>
                      <td><span className={getBadgeClass(order.order_status)}>{order.order_status}</span></td>
                      <td onClick={(e) => e.stopPropagation()}>
                        <OrderActions order={order} onStatusUpdate={handleStatusUpdate} />
                      </td>
                      <td style={{ fontSize: ".78rem", color: "var(--text-muted)", whiteSpace: "nowrap" }}>
                        {formatISTTime(order.created_at)}
                      </td>
                    </tr>
                    {expandedOrderId === order.order_id && (
                      <tr key={`${order.order_id}-expanded`}>
                        <td colSpan={9} style={{ background: "var(--bg-subtle)", padding: "16px 24px" }}>
                          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(200px,1fr))", gap: "8px 24px", fontSize: ".88rem" }}>
                            {[
                              ["Order ID", order.order_id],
                              ["Phone", order.phone_number],
                              ["Email", order.email || "—"],
                              ["Estimated Collection", order.readable_collection_time || "Immediate"],
                              ["Processing Duration", order.readable_duration || (order.processing_duration_seconds ? `${Math.round(order.processing_duration_seconds / 60)} min` : "0 min")],
                              ["Print Type", order.print_type || "—"],
                              ["Binding", order.binding_type || "—"],
                              ["Payment Method", order.payment_method],
                              ["Payment Status", order.payment_status],
                              ["Special Instructions", order.special_instructions || "—"],
                            ].map(([k, v]) => (
                              <div key={k} style={{ display: "flex", gap: 8 }}>
                                <span style={{ color: "var(--text-muted)", minWidth: 140 }}>{k}:</span>
                                <span style={{ fontWeight: 600 }}>{v}</span>
                              </div>
                            ))}
                          </div>

                          {/* Stationery Breakdown in Expanded View */}
                          {stationeryList.length > 0 && (
                            <div style={{ marginTop: 14, paddingTop: 12, borderTop: "1px solid var(--border)" }}>
                              <div style={{ fontWeight: 700, fontSize: ".88rem", marginBottom: 6, display: "flex", alignItems: "center", gap: 6 }}>
                                <ShoppingBag size={15} color="var(--primary)" /> Stationery Items Breakdown:
                              </div>
                              <div style={{ display: "flex", flexWrap: "wrap", gap: 10 }}>
                                {stationeryList.map((stItem, idx) => (
                                  <span
                                    key={idx}
                                    style={{
                                      background: "var(--bg-card)",
                                      border: "1px solid var(--border)",
                                      padding: "4px 10px",
                                      borderRadius: "var(--radius-sm)",
                                      fontSize: ".82rem",
                                    }}
                                  >
                                    <strong>{stItem.quantity}x</strong> {stItem.name} (₹{stItem.price} ea) = ₹{Number(stItem.subtotal).toFixed(2)}
                                  </span>
                                ))}
                              </div>
                            </div>
                          )}

                          <div style={{ marginTop: 14, display: "flex", gap: 10, alignItems: "center" }}>
                            {order.document_name && (
                              <a
                                href={`https://campusprint-syv1.onrender.com/api/staff/orders/${order.order_id}/file`}
                                target="_blank"
                                rel="noreferrer"
                                className="btn btn-outline btn-sm"
                                style={{ display: "inline-flex" }}
                              >
                                <ExternalLink size={14} /> View Document
                              </a>
                            )}
                          </div>
                          {order.rejection_reason && (
                            <div className="alert alert-error" style={{ marginTop: 12 }}>
                              <AlertTriangle size={14} /> Rejection: {order.rejection_reason}
                            </div>
                          )}
                        </td>
                      </tr>
                    )}
                  </Fragment>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
