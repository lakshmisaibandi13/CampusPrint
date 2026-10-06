/**
 * OrderForm.jsx — Multi-PDF order flow
 * ──────────────────────────────────────
 * Step 1  Student details
 * Step 2  Upload multiple PDFs — each gets its own settings card
 * Step 3  Shared options (binding, print-type, special instructions)
 * Step 4  Live combined summary + Proceed to Payment
 * Step 5  PaymentModal (UPI, countdown, screenshot verify)
 * Step 6  Order confirmation with token number
 *
 * Rules enforced here (mirror backend):
 *   • PDF page count comes from /api/inspect-file — never user-editable
 *   • Each file has independent: copies / color_mode / side_mode
 *   • Grand total = Σ per-file printing costs + binding + type surcharge
 *   • Backend at POST /api/orders/multi always recomputes; frontend total
 *     is only for display
 */

import { useState, useRef, useCallback, useEffect } from "react";
import {
  Upload, FileText, X, CheckCircle, Loader, Users,
  Printer, BookOpen, Layers, Scissors, Star, Plus,
  Trash2, AlertCircle, ChevronDown, ChevronUp,
  ShoppingBag, CreditCard
} from "lucide-react";
import PaymentModal from "./PaymentModal";

const API = typeof window !== "undefined" && (window.location.hostname === "localhost" || window.location.hostname === "127.0.0.1")
  ? "/api"
  : (import.meta.env.VITE_API_URL || "https://campusprint-syv1.onrender.com/api");
const BW_RATE    = 2;
const COLOR_RATE = 5;

const DEFAULT_STATIONERY = [
  { id: "black_pen", name: "Black Pen", price: 5, unit: "each", category: "Pens & Pencils" },
  { id: "blue_pen", name: "Blue Pen", price: 5, unit: "each", category: "Pens & Pencils" },
  { id: "red_pen", name: "Red Pen", price: 5, unit: "each", category: "Pens & Pencils" },
  { id: "pencil", name: "Pencil", price: 5, unit: "each", category: "Pens & Pencils" },
  { id: "eraser", name: "Eraser", price: 5, unit: "each", category: "Pens & Pencils" },
  { id: "sharpener", name: "Sharpener", price: 3, unit: "each", category: "Pens & Pencils" },
  { id: "plain_small_notebook", name: "Small Plain Notebook", price: 20, unit: "each", category: "Notebooks" },
  { id: "plain_long_notebook", name: "Long Plain Notebook", price: 50, unit: "each", category: "Notebooks" },
  { id: "ruled_long_notebook", name: "Long Ruled Notebook", price: 50, unit: "each", category: "Notebooks" },
  { id: "assignment_booklet", name: "Assignment Booklet", price: 15, unit: "each", category: "Papers, Booklets & Records" },
  { id: "record_book", name: "Record Book", price: 90, unit: "each", category: "Papers, Booklets & Records" },
  { id: "record_paper", name: "Record Paper", price: 1, unit: "per page", category: "Papers, Booklets & Records" },
  { id: "a4_sheet", name: "A4 Sheet", price: 1, unit: "per sheet", category: "Papers, Booklets & Records" },
  { id: "bee_record", name: "BEE Record", price: 150, unit: "each", category: "Papers, Booklets & Records" },
  { id: "aep_record", name: "AEP Record", price: 100, unit: "each", category: "Papers, Booklets & Records" },
  { id: "english_record", name: "English Record", price: 100, unit: "each", category: "Papers, Booklets & Records" },
];

// ── Pure pricing helper (mirrors database.py:calculate_order_price) ──────────
function calcItemQuote(pages, copies, colorMode, sideMode) {
  if (!pages || !copies) return null;
  const isDouble      = sideMode === "double";
  const isColor       = colorMode === "color";
  const useDoubleRate = isDouble && pages > 1;
  const rate          = useDoubleRate ? (isColor ? 8 : 3) : (isColor ? COLOR_RATE : BW_RATE);
  const rateUnit      = useDoubleRate ? "paper" : "page";
  const sheetsPerCopy = isDouble ? Math.ceil(pages / 2) : pages;

  let costPerCopy;
  if (pages === 1) {
    costPerCopy = isColor ? COLOR_RATE : BW_RATE;
  } else if (isDouble) {
    if (isColor) {
      costPerCopy = Math.floor(pages / 2) * 8 + (pages % 2) * 5;
    } else {
      costPerCopy = Math.floor(pages / 2) * 3 + (pages % 2) * 2;
    }
  } else {
    costPerCopy = pages * (isColor ? COLOR_RATE : BW_RATE);
  }

  const printingCost = costPerCopy * copies;

  return {
    rate,
    rateUnit,
    sheetsPerCopy,
    totalSheets:      sheetsPerCopy * copies,
    totalPrintedPages: pages * copies,
    printingCost,
  };
}

function calcGrandTotal(items, bindingCost, typeExtra) {
  const printingSum = items.reduce((s, it) => {
    const q = it.fileInfo
      ? calcItemQuote(it.fileInfo.pages, it.copies, it.colorMode, it.sideMode)
      : null;
    return s + (q ? q.printingCost : 0);
  }, 0);
  return Math.round((printingSum + bindingCost + typeExtra) * 100) / 100;
}

// ── Stepper ──────────────────────────────────────────────────────────────────
function Stepper({ value, onChange, min = 0, max = 200 }) {
  return (
    <div className="stepper-input">
      <button 
        className="stepper-btn" 
        onClick={() => onChange(Math.max(min, value - 1))}
        disabled={value <= min}
        style={value <= min ? { opacity: 0.4, cursor: "not-allowed" } : undefined}
      >
        −
      </button>
      <span className="stepper-value">{value}</span>
      <button 
        className="stepper-btn" 
        onClick={() => onChange(Math.min(max, value + 1))}
        disabled={value >= max}
        style={value >= max ? { opacity: 0.4, cursor: "not-allowed" } : undefined}
      >
        +
      </button>
    </div>
  );
}

// ── Option pill (compact 2-option toggle) ────────────────────────────────────
function TogglePill({ options, value, onChange }) {
  return (
    <div style={{ display: "flex", gap: 8 }}>
      {options.map((opt) => (
        <button
          key={opt.value}
          onClick={() => onChange(opt.value)}
          style={{
            flex: 1, padding: "6px 10px", borderRadius: "var(--radius-sm)",
            border: value === opt.value ? "2px solid var(--primary)" : "2px solid var(--border)",
            background: value === opt.value ? "var(--primary-light)" : "var(--bg-card)",
            color: value === opt.value ? "var(--primary)" : "var(--text-muted)",
            fontWeight: 700, fontSize: ".82rem", cursor: "pointer",
            transition: "all .15s",
          }}
        >
          {opt.label}
          {opt.tag && (
            <span style={{ marginLeft: 6, fontSize: ".72rem", opacity: .8 }}>{opt.tag}</span>
          )}
        </button>
      ))}
    </div>
  );
}

// ── Per-file card ─────────────────────────────────────────────────────────────
function FileCard({ item, index, onUpdate, onRemove, pricingConfig }) {
  const [collapsed, setCollapsed] = useState(false);
  const q = item.fileInfo
    ? calcItemQuote(item.fileInfo.pages, item.copies, item.colorMode, item.sideMode)
    : null;

  const borderColor = item.fileError
    ? "#ef4444"
    : item.fileInfo
    ? "var(--primary-border)"
    : "var(--border)";

  return (
    <div
      style={{
        border: `2px solid ${borderColor}`,
        borderRadius: "var(--radius-lg)",
        background: "var(--bg-card)",
        marginBottom: 16,
        overflow: "hidden",
        transition: "border-color .2s",
      }}
    >
      {/* Card header */}
      <div
        style={{
          display: "flex", alignItems: "center", gap: 10,
          padding: "12px 16px",
          background: item.fileInfo ? "var(--primary-light)" : "var(--bg-subtle)",
          borderBottom: "1px solid var(--border)",
          cursor: "pointer",
        }}
        onClick={() => setCollapsed((c) => !c)}
      >
        <div
          style={{
            width: 26, height: 26, borderRadius: "50%",
            background: "var(--primary)", color: "#fff",
            display: "flex", alignItems: "center", justifyContent: "center",
            fontSize: ".78rem", fontWeight: 800, flexShrink: 0,
          }}
        >
          {index + 1}
        </div>

        <FileText size={16} color="var(--primary)" style={{ flexShrink: 0 }} />

        <div style={{ flex: 1, minWidth: 0 }}>
          {item.fileInfo ? (
            <>
              <div style={{
                fontWeight: 700, fontSize: ".92rem",
                overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap",
              }}>
                {item.file.name}
              </div>
              <div style={{ fontSize: ".75rem", color: "var(--text-muted)" }}>
                {item.fileInfo.pages} pages · {item.fileInfo.file_size_kb.toFixed(1)} KB
                {item.fileInfo.is_pdf && " · PDF (auto-detected)"}
              </div>
            </>
          ) : item.inspecting ? (
            <span style={{ fontSize: ".88rem", color: "var(--text-muted)", display: "flex", alignItems: "center", gap: 6 }}>
              <Loader size={14} className="spin-icon" /> Reading document…
            </span>
          ) : item.fileError ? (
            <span style={{ fontSize: ".88rem", color: "#ef4444" }}>
              <AlertCircle size={14} style={{ display: "inline", marginRight: 4 }} />
              {item.fileError}
            </span>
          ) : (
            <span style={{ fontSize: ".88rem", color: "var(--text-muted)" }}>
              {item.file?.name || "Uploading…"}
            </span>
          )}
        </div>

        {/* Subtotal badge */}
        {q && (
          <div style={{
            background: "var(--primary)", color: "#fff",
            padding: "2px 10px", borderRadius: "9999px",
            fontSize: ".82rem", fontWeight: 700, flexShrink: 0,
          }}>
            ₹{q.printingCost.toFixed(2)}
          </div>
        )}

        <button
          onClick={(e) => { e.stopPropagation(); setCollapsed((c) => !c); }}
          style={{ background: "none", border: "none", cursor: "pointer", color: "var(--text-muted)", padding: 2 }}
        >
          {collapsed ? <ChevronDown size={16} /> : <ChevronUp size={16} />}
        </button>

        <button
          onClick={(e) => { e.stopPropagation(); onRemove(); }}
          title="Remove this file"
          style={{ background: "none", border: "none", cursor: "pointer", color: "#ef4444", padding: 2 }}
        >
          <Trash2 size={16} />
        </button>
      </div>

      {/* Card body — hidden when collapsed */}
      {!collapsed && item.fileInfo && !item.fileError && (
        <div style={{ padding: "14px 16px" }}>
          {/* Page count badge */}
          <div style={{ marginBottom: 14 }}>
            <span className="page-count-badge">
              <CheckCircle size={13} />
              {item.fileInfo.is_pdf
                ? `${item.fileInfo.pages} pages — auto-detected from PDF`
                : `${item.fileInfo.pages} page — non-PDF`}
            </span>
            <div style={{ fontSize: ".73rem", color: "var(--text-muted)", marginTop: 3 }}>
              Page count is read automatically. It cannot be changed manually.
            </div>
          </div>

          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 14 }}>
            {/* Color mode */}
            <div>
              <div className="form-label" style={{ marginBottom: 6 }}>Color</div>
              <TogglePill
                value={item.colorMode}
                onChange={(v) => onUpdate({ colorMode: v })}
                options={[
                  { value: "bw",    label: "B&W",   tag: "₹2" },
                  { value: "color", label: "Color", tag: "₹5" },
                ]}
              />
            </div>

            {/* Side mode */}
            <div>
              <div className="form-label" style={{ marginBottom: 6 }}>Sides</div>
              <TogglePill
                value={item.sideMode}
                onChange={(v) => onUpdate({ sideMode: v })}
                options={[
                  { value: "single", label: "Single" },
                  { value: "double", label: "Double" },
                ]}
              />
            </div>

            {/* Copies */}
            <div>
              <div className="form-label" style={{ marginBottom: 6 }}>Copies</div>
              <Stepper value={item.copies} onChange={(v) => onUpdate({ copies: v })} />
            </div>
          </div>

          {/* Per-item quote */}
          {q && (
            <div style={{
              marginTop: 14, padding: "10px 12px",
              background: "var(--bg-subtle)", borderRadius: "var(--radius-sm)",
              fontSize: ".82rem", display: "flex", flexWrap: "wrap", gap: "6px 20px",
            }}>
              <span style={{ color: "var(--text-muted)" }}>
                Printed pages: <strong style={{ color: "var(--text-main)" }}>{q.totalPrintedPages}</strong>
              </span>
              <span style={{ color: "var(--text-muted)" }}>
                Sheets: <strong style={{ color: "var(--text-main)" }}>{q.totalSheets}</strong>
              </span>
              <span style={{ color: "var(--text-muted)" }}>
                Rate: <strong style={{ color: "var(--text-main)" }}>₹{q.rate}/{q.rateUnit}</strong>
              </span>
              <span style={{ color: "var(--primary)", fontWeight: 700 }}>
                Subtotal: ₹{q.printingCost.toFixed(2)}
              </span>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

// ── Confirmed order view ──────────────────────────────────────────────────────
// ── Confirmed order view ──────────────────────────────────────────────────────
function ConfirmedView({ order, items, stationeryItems, onTrack, onReset }) {
  const displayItems = stationeryItems && stationeryItems.length > 0
    ? stationeryItems
    : (order.stationery_items || []);

  return (
    <div className="container" style={{ padding: "40px 20px 60px" }}>
      <div style={{ maxWidth: 600, margin: "0 auto" }}>
        <div className="token-display-box">
          <div style={{ fontSize: ".88rem", color: "#94a3b8", marginBottom: 4 }}>Order Number</div>
          <div className="token-big-number">#{order.display_order_number || order.id}</div>
          <div style={{ fontSize: ".92rem", color: "#38bdf8", fontWeight: 700, marginTop: 8 }}>
            Token: {order.token_number}
          </div>
          <div style={{ fontSize: ".82rem", color: "#64748b", marginTop: 4 }}>
            Order ID: {order.order_id}
          </div>
        </div>

        <div className="alert alert-success" style={{ marginBottom: 20 }}>
          <CheckCircle size={18} style={{ flexShrink: 0, marginTop: 2 }} />
          <div>
            <strong>Order placed successfully — payment verified!</strong>
            <div style={{ marginTop: 4, fontSize: ".88rem" }}>
              Show your order or token number at the counter to collect your items.
            </div>
          </div>
        </div>

        {/* Stationery breakdown */}
        {displayItems && displayItems.length > 0 && (
          <div className="card" style={{ marginBottom: 20 }}>
            <div style={{
              fontWeight: 700, fontSize: "1rem", marginBottom: 12,
              paddingBottom: 10, borderBottom: "1px solid var(--border)",
              display: "flex", alignItems: "center", gap: 8
            }}>
              <ShoppingBag size={18} color="var(--primary)" /> Stationery Items in this Order
            </div>
            {displayItems.map((s, i) => (
              <div key={i} style={{
                display: "flex", justifyContent: "space-between", alignItems: "center",
                padding: "8px 0",
                borderBottom: i < displayItems.length - 1 ? "1px solid var(--border)" : "none",
              }}>
                <div>
                  <span style={{ fontWeight: 700 }}>{s.quantity}x</span> {s.name}
                  <span style={{ fontSize: ".78rem", color: "var(--text-muted)", marginLeft: 8 }}>
                    (₹{s.price} each)
                  </span>
                </div>
                <div style={{ fontWeight: 700, color: "var(--primary)" }}>
                  ₹{Number(s.subtotal).toFixed(2)}
                </div>
              </div>
            ))}
          </div>
        )}

        {/* Per-file breakdown */}
        {items && items.length > 0 && (
          <div className="card" style={{ marginBottom: 20 }}>
            <div style={{
              fontWeight: 700, fontSize: "1rem", marginBottom: 12,
              paddingBottom: 10, borderBottom: "1px solid var(--border)",
            }}>
              Printing Documents in this Order
            </div>
            {items.map((it, i) => {
              const q = calcItemQuote(it.pages, it.copies, it.color_mode, it.side_mode);
              return (
                <div key={i} style={{
                  padding: "10px 0",
                  borderBottom: i < items.length - 1 ? "1px solid var(--border)" : "none",
                }}>
                  <div style={{ fontWeight: 700, fontSize: ".9rem", marginBottom: 4 }}>
                    {i + 1}. {it.document_name}
                  </div>
                  <div style={{
                    display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(140px, 1fr))",
                    gap: "4px 16px", fontSize: ".82rem", color: "var(--text-muted)",
                  }}>
                    {[
                      ["Pages", it.pages],
                      ["Copies", it.copies],
                      ["Color", it.color_mode === "color" ? "Full Color" : "B&W"],
                      ["Sides", it.side_mode === "double" ? "Double-sided" : "Single-sided"],
                      ["Sheets", it.calculated_sheets],
                      ["Subtotal", `₹${it.item_total}`],
                    ].map(([k, v]) => (
                      <div key={k}>
                        <span>{k}: </span>
                        <strong style={{ color: "var(--text-main)" }}>{v}</strong>
                      </div>
                    ))}
                  </div>
                </div>
              );
            })}
          </div>
        )}

        {/* Order totals */}
        <div className="card" style={{ marginBottom: 20 }}>
          <div style={{
            fontWeight: 700, fontSize: "1rem", marginBottom: 12,
            paddingBottom: 10, borderBottom: "1px solid var(--border)",
          }}>
            Payment Summary
          </div>
          {[
            ["Order Number",      `#${order.display_order_number || order.id}`],
            ["Token",             order.token_number],
            ["Total Amount Paid", `₹${order.total_price}`],
            ["Payment Method",    "UPI"],
            ["Status",            order.order_status],
          ].map(([label, val]) => (
            <div className="summary-row" key={label}>
              <span>{label}</span>
              <span style={{ fontWeight: 600, color: "var(--text-main)" }}>{val}</span>
            </div>
          ))}
        </div>

        <div style={{ display: "flex", gap: 12, justifyContent: "center" }}>
          <button className="btn btn-primary" onClick={onTrack}>
            <Printer size={16} /> Track My Order
          </button>
          <button className="btn btn-outline" onClick={onReset}>
            Place Another Order
          </button>
        </div>
      </div>
    </div>
  );
}

// ── Stationery Selection Component ───────────────────────────────────────────
function StationerySection({ catalog, quantities, onQuantityChange }) {
  const categories = ["Pens & Pencils", "Notebooks", "Papers, Booklets & Records"];
  const totalItems = Object.values(quantities).reduce((a, b) => a + (b || 0), 0);
  const subtotal = catalog.reduce((sum, item) => sum + (quantities[item.id] || 0) * item.price, 0);

  return (
    <div className="card" style={{ marginBottom: 24 }}>
      <div className="form-section-title" style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
          <span className="form-step-badge">3</span>
          <ShoppingBag size={18} /> Stationery Items (Optional)
        </div>
        {totalItems > 0 && (
          <span style={{
            background: "var(--primary)", color: "#fff",
            padding: "2px 10px", borderRadius: "9999px", fontSize: ".78rem", fontWeight: 700,
          }}>
            {totalItems} item{totalItems !== 1 ? "s" : ""} (₹{subtotal.toFixed(2)})
          </span>
        )}
      </div>

      <p style={{ fontSize: ".82rem", color: "var(--text-muted)", marginTop: -8, marginBottom: 16 }}>
        Select college stationery, notebooks, or papers. You can purchase stationery only, printing only, or both together.
      </p>

      {categories.map((cat) => {
        const catItems = catalog.filter((it) => it.category === cat || (cat === "Papers, Booklets & Records" && it.category === "Papers & Booklets"));
        return (
          <div key={cat} style={{ marginBottom: 18 }}>
            <div style={{
              fontSize: ".82rem", fontWeight: 700, color: "var(--text-muted)",
              textTransform: "uppercase", letterSpacing: "0.05em", marginBottom: 8,
              borderBottom: "1px solid var(--border)", paddingBottom: 4
            }}>
              {cat}
            </div>
            <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(260px, 1fr))", gap: 8 }}>
              {catItems.map((item) => {
                const qty = quantities[item.id] || 0;
                return (
                  <div
                    key={item.id}
                    style={{
                      display: "flex",
                      alignItems: "center",
                      justifyContent: "space-between",
                      padding: "8px 12px",
                      background: qty > 0 ? "var(--primary-light)" : "var(--bg-card)",
                      border: qty > 0 ? "1.5px solid var(--primary)" : "1px solid var(--border)",
                      borderRadius: "var(--radius-md)",
                      transition: "all .15s",
                    }}
                  >
                    <div style={{ flex: 1, minWidth: 0, paddingRight: 8 }}>
                      <div style={{ fontWeight: 700, fontSize: ".88rem", color: "var(--text-main)" }}>
                        {item.name}
                      </div>
                      <div style={{ fontSize: ".78rem", color: "var(--text-muted)" }}>
                        {item.unit === "per page" ? "₹1 / page" : item.unit === "per sheet" ? "₹1 / sheet" : `₹${item.price} each`}
                        {qty > 0 && (
                          <strong style={{ color: "var(--primary)", marginLeft: 6 }}>
                            = ₹{(qty * item.price).toFixed(2)}
                          </strong>
                        )}
                      </div>
                    </div>
                    <div style={{ flexShrink: 0 }}>
                      <Stepper
                        value={qty}
                        onChange={(v) => onQuantityChange(item.id, v)}
                        min={0}
                        max={100}
                      />
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        );
      })}

      {subtotal > 0 && (
        <div style={{
          marginTop: 12, padding: "10px 14px",
          background: "var(--primary-light)",
          borderRadius: "var(--radius-sm)",
          display: "flex", justifyContent: "space-between", alignItems: "center"
        }}>
          <span style={{ fontSize: ".88rem", fontWeight: 600, color: "var(--primary)" }}>
            Stationery Subtotal ({totalItems} item{totalItems !== 1 ? "s" : ""})
          </span>
          <span style={{ fontSize: "1rem", fontWeight: 800, color: "var(--primary)" }}>
            ₹{subtotal.toFixed(2)}
          </span>
        </div>
      )}
    </div>
  );
}

// ── Main component ────────────────────────────────────────────────────────────
export default function OrderForm({ onTabChange }) {
  // Fetch pricing config & stationery catalog once
  const [pricingConfig, setPricingConfig] = useState(null);
  const [stationeryCatalog, setStationeryCatalog] = useState(DEFAULT_STATIONERY);
  const [stationeryQuantities, setStationeryQuantities] = useState({});
  const [confirmedStationery, setConfirmedStationery] = useState([]);
  const [isDemoMode, setIsDemoMode] = useState(false);

  useEffect(() => {
    fetch(`${API}/pricing`)
      .then((r) => r.json())
      .then((d) => d.success && setPricingConfig(d.pricing))
      .catch(() => {});

    fetch(`${API}/stationery`)
      .then((r) => r.json())
      .then((d) => {
        if (d.success && d.items && d.items.length > 0) {
          setStationeryCatalog(d.items);
        }
      })
      .catch(() => {});

    fetch(`${API}/payment/config`)
      .then((r) => r.json())
      .then((d) => {
        if (d.success && d.demo_payment_mode) {
          setIsDemoMode(true);
        }
      })
      .catch(() => {});
  }, []);

  function handleStationeryChange(id, qty) {
    setStationeryQuantities((prev) => ({
      ...prev,
      [id]: Math.max(0, qty),
    }));
  }

  // Student details
  const [studentName,  setStudentName]  = useState("");
  const [rollNumber,   setRollNumber]   = useState("");
  const [phoneNumber,  setPhoneNumber]  = useState("");
  const [email,        setEmail]        = useState("");

  // Files list — each entry:
  // { id, file, fileInfo, fileError, inspecting, copies, colorMode, sideMode }
  const [fileItems, setFileItems] = useState([]);
  const [globalDragActive, setGlobalDragActive] = useState(false);
  const addFileInputRef = useRef(null);

  // Shared order settings
  const [printType,           setPrintType]           = useState("regular");
  const [bindingType,         setBindingType]         = useState("none");
  const [specialInstructions, setSpecialInstructions] = useState("");

  // Payment / confirmation state
  const [showPayment,        setShowPayment]        = useState(false);
  const [placing,            setPlacing]            = useState(false);
  const [formError,          setFormError]          = useState(null);
  const [confirmedOrder,     setConfirmedOrder]     = useState(null);
  const [confirmedItems,     setConfirmedItems]     = useState([]);
  const [activePendingOrder, setActivePendingOrder] = useState(null);
  const [activeItems,        setActiveItems]        = useState([]);
  const [activeStationery,   setActiveStationery]   = useState([]);

  // ── Inspect a single file via /api/inspect-file ───────────────────────────
  const inspectFile = useCallback(async (id, selectedFile) => {
    setFileItems((prev) =>
      prev.map((it) =>
        it.id === id
          ? { ...it, file: selectedFile, inspecting: true, fileInfo: null, fileError: null }
          : it
      )
    );

    const formData = new FormData();
    formData.append("document", selectedFile);

    try {
      const res  = await fetch(`${API}/inspect-file`, { method: "POST", body: formData });
      const data = await res.json();
      if (data.success) {
        setFileItems((prev) =>
          prev.map((it) =>
            it.id === id
              ? {
                  ...it,
                  inspecting: false,
                  fileInfo: {
                    pages:        data.pages,
                    file_size_kb: data.file_size_kb,
                    is_pdf:       data.is_pdf,
                    filename:     data.filename,
                  },
                  fileError: null,
                }
              : it
          )
        );
      } else {
        setFileItems((prev) =>
          prev.map((it) =>
            it.id === id
              ? { ...it, inspecting: false, fileInfo: null, fileError: data.error || "Failed to read file." }
              : it
          )
        );
      }
    } catch {
      setFileItems((prev) =>
        prev.map((it) =>
          it.id === id
            ? { ...it, inspecting: false, fileInfo: null, fileError: "Could not reach server." }
            : it
        )
      );
    }
  }, []);

  // ── Add new file slot(s) ──────────────────────────────────────────────────
  function addFiles(fileList) {
    for (const f of Array.from(fileList)) {
      const id = `${Date.now()}-${Math.random()}`;
      const newItem = {
        id, file: f,
        fileInfo: null, fileError: null, inspecting: true,
        copies: 1, colorMode: "bw", sideMode: "single",
      };
      setFileItems((prev) => [...prev, newItem]);
      inspectFile(id, f);
    }
  }

  function handleAddInputChange(e) {
    if (e.target.files?.length) addFiles(e.target.files);
    // Reset input so same file can be re-added
    e.target.value = "";
  }

  function handleGlobalDrop(e) {
    e.preventDefault();
    setGlobalDragActive(false);
    if (e.dataTransfer.files?.length) addFiles(e.dataTransfer.files);
  }

  // ── Update a single file item ──────────────────────────────────────────────
  function updateItem(id, patch) {
    setFileItems((prev) => prev.map((it) => it.id === id ? { ...it, ...patch } : it));
  }

  function removeItem(id) {
    setFileItems((prev) => prev.filter((it) => it.id !== id));
  }

  // ── Derived totals ────────────────────────────────────────────────────────
  const bindingCost = (() => {
    for (const b of pricingConfig?.bindings || []) {
      if (b.id === bindingType) return b.price || 0;
    }
    return 0;
  })();

  const typeExtra = (() => {
    const totalCopies = fileItems.reduce((s, it) => s + it.copies, 0);
    for (const t of pricingConfig?.types || []) {
      if (t.id === printType) return (t.extra_cost || 0) * totalCopies;
    }
    return 0;
  })();

  const selectedStationery = stationeryCatalog
    .filter((it) => (stationeryQuantities[it.id] || 0) > 0)
    .map((it) => ({
      id: it.id,
      name: it.name,
      price: it.price,
      quantity: stationeryQuantities[it.id],
      subtotal: Math.round(it.price * stationeryQuantities[it.id] * 100) / 100,
    }));
  const stationeryTotal = selectedStationery.reduce((sum, it) => sum + it.subtotal, 0);

  const readyItems  = fileItems.filter((it) => it.fileInfo && !it.fileError);
  const printingTotal = readyItems.length > 0 ? calcGrandTotal(readyItems, bindingCost, typeExtra) : 0;
  const grandTotal  = Math.round((printingTotal + stationeryTotal) * 100) / 100;

  const totalPrintedPages = readyItems.reduce((s, it) => {
    const q = calcItemQuote(it.fileInfo.pages, it.copies, it.colorMode, it.sideMode);
    return s + (q?.totalPrintedPages || 0);
  }, 0);

  const totalSheets = readyItems.reduce((s, it) => {
    const q = calcItemQuote(it.fileInfo.pages, it.copies, it.colorMode, it.sideMode);
    return s + (q?.totalSheets || 0);
  }, 0);

  // ── Validation ─────────────────────────────────────────────────────────────
  function validate() {
    if (!studentName.trim())                  return "Student name is required.";
    if (!rollNumber.trim())                   return "Roll number is required.";
    if (!/^\d{10}$/.test(phoneNumber.trim())) return "Enter a valid 10-digit phone number.";
    if (fileItems.length === 0 && selectedStationery.length === 0) {
      return "Please upload at least one document or select at least one stationery item.";
    }
    if (fileItems.length > 0) {
      if (fileItems.some((it) => it.inspecting)) return "Please wait — files are still being read.";
      if (fileItems.some((it) => it.fileError))  return "Remove files with errors before proceeding.";
      if (readyItems.length === 0 && selectedStationery.length === 0) {
        return "No valid documents ready for printing.";
      }
    }
    if (grandTotal <= 0) return "Order total must be greater than ₹0.";
    return null;
  }

  // ── Open payment / create order ───────────────────────────────────────────
  async function handleProceedToPayment() {
    const err = validate();
    if (err) { setFormError(err); return; }
    setFormError(null);

    // If order was already created for these items, re-open payment modal
    if (activePendingOrder) {
      setShowPayment(true);
      return;
    }

    setPlacing(true);

    const formData = new FormData();
    formData.append("student_name",        studentName.trim());
    formData.append("roll_number",         rollNumber.trim());
    formData.append("phone_number",        phoneNumber.trim());
    formData.append("email",               email.trim());
    formData.append("print_type",          printType);
    formData.append("binding_type",        bindingType);
    formData.append("special_instructions", specialInstructions.trim());
    formData.append("payment_method",      isDemoMode ? "Demo Payment" : "Razorpay");

    if (selectedStationery.length > 0) {
      formData.append("stationery_items", JSON.stringify(selectedStationery));
    }

    readyItems.forEach((it, i) => {
      formData.append(`document_${i}`,   it.file);
      formData.append(`copies_${i}`,     it.copies);
      formData.append(`color_mode_${i}`, it.colorMode);
      formData.append(`side_mode_${i}`,  it.sideMode);
    });

    try {
      const res = await fetch(`${API}/orders/multi`, { method: "POST", body: formData });
      const data = await res.json();
      if (data.success && data.order) {
        setActivePendingOrder(data.order);
        setActiveItems(data.items || []);
        setActiveStationery(data.stationery_items || selectedStationery);
        setShowPayment(true);
      } else {
        setFormError(data.error || "Failed to create order. Please try again.");
      }
    } catch {
      setFormError("Network error. Please try again.");
    } finally {
      setPlacing(false);
    }
  }

  // ── Called after payment verified by Razorpay / backend ───────────────────
  function handlePaymentSuccess(verifiedOrder) {
    setShowPayment(false);
    setConfirmedOrder(verifiedOrder || activePendingOrder);
    setConfirmedItems(activeItems || []);
    setConfirmedStationery(activeStationery || selectedStationery);
  }

  // ── Reset form ─────────────────────────────────────────────────────────────
  function resetForm() {
    setConfirmedOrder(null);
    setConfirmedItems([]);
    setConfirmedStationery([]);
    setStationeryQuantities({});
    setFileItems([]);
    setStudentName(""); setRollNumber(""); setPhoneNumber(""); setEmail("");
    setPrintType("regular"); setBindingType("none"); setSpecialInstructions("");
    setFormError(null);
    setActivePendingOrder(null);
    setActiveItems([]);
    setActiveStationery([]);
  }

  // ── Confirmed screen ───────────────────────────────────────────────────────
  if (confirmedOrder) {
    return (
      <ConfirmedView
        order={confirmedOrder}
        items={confirmedItems}
        stationeryItems={confirmedStationery}
        onTrack={() => onTabChange("track")}
        onReset={resetForm}
      />
    );
  }

  const printTypes = pricingConfig?.types || [
    { id: "regular",        name: "Standard Document / Notes",       extra_cost: 0  },
    { id: "assignment",     name: "College Assignment / Lab Record",  extra_cost: 0  },
    { id: "project_report", name: "Final Project Report",            extra_cost: 15 },
    { id: "certificate",    name: "Glossy / Certificate Print",      extra_cost: 20 },
  ];
  const bindings = pricingConfig?.bindings || [
    { id: "none",          name: "No Binding",                price: 0   },
    { id: "corner_staple", name: "Corner Staple",             price: 2   },
    { id: "spiral",        name: "Spiral Binding",            price: 30  },
    { id: "soft_binding",  name: "Soft Book Binding",         price: 50  },
    { id: "hard_binding",  name: "Hard Bound Golden Embossed",price: 160 },
  ];

  return (
    <div
      className="container"
      onDragOver={(e) => { e.preventDefault(); setGlobalDragActive(true); }}
      onDragLeave={(e) => { if (!e.currentTarget.contains(e.relatedTarget)) setGlobalDragActive(false); }}
      onDrop={handleGlobalDrop}
    >
      {/* Global drag overlay */}
      {globalDragActive && (
        <div style={{
          position: "fixed", inset: 0, zIndex: 200,
          background: "rgba(37,99,235,.15)", border: "3px dashed var(--primary)",
          display: "flex", alignItems: "center", justifyContent: "center",
          pointerEvents: "none",
        }}>
          <div style={{ background: "#fff", borderRadius: "var(--radius-xl)", padding: "32px 48px", textAlign: "center" }}>
            <Upload size={48} color="var(--primary)" style={{ marginBottom: 12 }} />
            <div style={{ fontSize: "1.2rem", fontWeight: 800, color: "var(--primary)" }}>
              Drop files to add them to your order
            </div>
          </div>
        </div>
      )}

      <div className="order-layout">
        {/* ══ LEFT: Form ══════════════════════════════════════════════════ */}
        <div>

          {/* ── Step 1: Student Details ── */}
          <div className="card" style={{ marginBottom: 24 }}>
            <div className="form-section-title">
              <span className="form-step-badge">1</span>
              <Users size={18} /> Student Details
            </div>
            <div className="form-row">
              <div className="form-group">
                <label className="form-label">Full Name *</label>
                <input className="form-input" placeholder="Aarav Sharma"
                  value={studentName} onChange={(e) => setStudentName(e.target.value)} />
              </div>
              <div className="form-group">
                <label className="form-label">Roll Number *</label>
                <input className="form-input" placeholder="CS2026-042"
                  value={rollNumber} onChange={(e) => setRollNumber(e.target.value)} />
              </div>
            </div>
            <div className="form-row">
              <div className="form-group">
                <label className="form-label">Phone Number *</label>
                <input className="form-input" placeholder="9876543210" maxLength={10}
                  value={phoneNumber}
                  onChange={(e) => setPhoneNumber(e.target.value.replace(/\D/g, ""))} />
              </div>
              <div className="form-group">
                <label className="form-label">Email (optional)</label>
                <input className="form-input" type="email" placeholder="you@college.edu"
                  value={email} onChange={(e) => setEmail(e.target.value)} />
              </div>
            </div>
          </div>

          {/* ── Step 2: Upload Files ── */}
          <div className="card" style={{ marginBottom: 24 }}>
            <div className="form-section-title">
              <span className="form-step-badge">2</span>
              <Upload size={18} /> Upload Documents
              {fileItems.length > 0 && (
                <span style={{
                  marginLeft: "auto", background: "var(--primary)", color: "#fff",
                  padding: "2px 10px", borderRadius: "9999px", fontSize: ".78rem", fontWeight: 700,
                }}>
                  {fileItems.length} file{fileItems.length !== 1 ? "s" : ""}
                </span>
              )}
            </div>

            {/* Per-file cards */}
            {fileItems.map((item, i) => (
              <FileCard
                key={item.id}
                item={item}
                index={i}
                onUpdate={(patch) => updateItem(item.id, patch)}
                onRemove={() => removeItem(item.id)}
                pricingConfig={pricingConfig}
              />
            ))}

            {/* Add more files button / dropzone */}
            <div
              className={`dropzone${globalDragActive ? " drag-active" : ""}`}
              style={{ marginTop: fileItems.length > 0 ? 4 : 0 }}
              onClick={() => addFileInputRef.current?.click()}
            >
              <div className="dropzone-icon" style={{ width: 40, height: 40 }}>
                <Plus size={40} />
              </div>
              <div className="dropzone-title" style={{ fontSize: ".95rem" }}>
                {fileItems.length === 0 ? "Click to upload or drag & drop" : "Add another file"}
              </div>
              <div className="dropzone-subtitle">
                PDF, DOC, DOCX, PPT, PPTX, TXT, JPG, PNG · Max 50 MB each
              </div>
            </div>

            <input
              ref={addFileInputRef}
              type="file"
              multiple
              accept=".pdf,.doc,.docx,.ppt,.pptx,.txt,.jpg,.jpeg,.png"
              style={{ display: "none" }}
              onChange={handleAddInputChange}
            />

            {fileItems.length > 0 && (
              <p style={{ fontSize: ".75rem", color: "var(--text-muted)", marginTop: 10 }}>
                Each file has its own copies / color / sides settings above. Settings are independent.
              </p>
            )}
          </div>

          {/* ── Step 3: Stationery Section (Optional) ── */}
          <StationerySection
            catalog={stationeryCatalog}
            quantities={stationeryQuantities}
            onQuantityChange={handleStationeryChange}
          />

          {/* ── Step 4: Finishing & Options ── */}
          <div className="card" style={{ marginBottom: 24 }}>
            <div className="form-section-title">
              <span className="form-step-badge">4</span>
              <Scissors size={18} /> Finishing &amp; Options (For Documents)
            </div>

            <div className="form-group">
              <label className="form-label">Document Type</label>
              <select className="form-select" value={printType}
                onChange={(e) => setPrintType(e.target.value)}>
                {printTypes.map((t) => (
                  <option key={t.id} value={t.id}>
                    {t.name}{t.extra_cost > 0 ? ` (+₹${t.extra_cost}/copy)` : ""}
                  </option>
                ))}
              </select>
            </div>

            <div className="form-group">
              <label className="form-label">Binding &amp; Finishing</label>
              <select className="form-select" value={bindingType}
                onChange={(e) => setBindingType(e.target.value)}>
                {bindings.map((b) => (
                  <option key={b.id} value={b.id}>
                    {b.name}{b.price > 0 ? ` (+₹${b.price})` : ""}
                  </option>
                ))}
              </select>
            </div>

            <div className="form-group">
              <label className="form-label">Special Instructions (optional)</label>
              <textarea className="form-textarea" rows={3}
                placeholder="e.g. Staple on top-left, first page in colour…"
                value={specialInstructions}
                onChange={(e) => setSpecialInstructions(e.target.value)} />
            </div>
          </div>

          {formError && (
            <div className="alert alert-error" style={{ marginBottom: 16 }}>
              <AlertCircle size={16} style={{ flexShrink: 0 }} />
              {formError}
            </div>
          )}
        </div>

        {/* ══ RIGHT: Live Summary ══════════════════════════════════════════ */}
        <div>
          <div className="summary-card">
            <div className="summary-header">
              <span>Order Summary</span>
              {(readyItems.length > 0 || selectedStationery.length > 0) && (
                <span style={{ fontSize: ".78rem", color: "var(--text-muted)", fontWeight: 500 }}>
                  {[
                    readyItems.length > 0 ? `${readyItems.length} file${readyItems.length !== 1 ? "s" : ""}` : null,
                    selectedStationery.length > 0 ? `${selectedStationery.reduce((s, it) => s + it.quantity, 0)} item${selectedStationery.reduce((s, it) => s + it.quantity, 0) !== 1 ? "s" : ""}` : null
                  ].filter(Boolean).join(" · ")}
                </span>
              )}
            </div>

            {readyItems.length === 0 && selectedStationery.length === 0 ? (
              <p style={{ color: "var(--text-muted)", fontSize: ".88rem", textAlign: "center", padding: "12px 0" }}>
                Upload documents or select stationery to see your price quote.
              </p>
            ) : (
              <>
                {/* Printing documents section */}
                {readyItems.length > 0 && (
                  <div style={{ marginBottom: 12 }}>
                    <div style={{ fontSize: ".8rem", fontWeight: 700, color: "var(--text-muted)", textTransform: "uppercase", letterSpacing: "0.05em", marginBottom: 6 }}>
                      Printing Documents
                    </div>
                    {readyItems.map((it, i) => {
                      const q = calcItemQuote(it.fileInfo.pages, it.copies, it.colorMode, it.sideMode);
                      return (
                        <div key={it.id} style={{
                          padding: "8px 0",
                          borderBottom: "1px solid var(--border)",
                          marginBottom: 6,
                        }}>
                          <div style={{
                            fontSize: ".82rem", fontWeight: 700,
                            overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap",
                            color: "var(--text-main)", marginBottom: 3,
                          }}>
                            {i + 1}. {it.file.name}
                          </div>
                          <div style={{ fontSize: ".78rem", color: "var(--text-muted)", marginBottom: 2 }}>
                            {it.fileInfo.pages} pages × {it.copies} {it.copies === 1 ? "copy" : "copies"} ·{" "}
                            {it.colorMode === "color" ? "Color" : "B&W"} ·{" "}
                            {it.sideMode === "double" ? "Double" : "Single"}
                          </div>
                          {q && (
                            <div style={{ display: "flex", justifyContent: "space-between", fontSize: ".82rem" }}>
                              <span style={{ color: "var(--text-muted)" }}>
                                {q.totalPrintedPages} pg · {q.totalSheets} sheets
                              </span>
                              <span style={{ fontWeight: 700, color: "var(--primary)" }}>
                                ₹{q.printingCost.toFixed(2)}
                              </span>
                            </div>
                          )}
                        </div>
                      );
                    })}

                    <div className="summary-row highlight" style={{ marginTop: 6 }}>
                      <span>Total Printed Pages</span><span>{totalPrintedPages}</span>
                    </div>
                    <div className="summary-row highlight">
                      <span>Total Physical Sheets</span><span>{totalSheets}</span>
                    </div>

                    {bindingCost > 0 && (
                      <div className="summary-row">
                        <span>Binding</span><span>+₹{bindingCost.toFixed(2)}</span>
                      </div>
                    )}
                    {typeExtra > 0 && (
                      <div className="summary-row">
                        <span>Document Type</span><span>+₹{typeExtra.toFixed(2)}</span>
                      </div>
                    )}

                    <div className="summary-row" style={{ fontWeight: 700, marginTop: 4 }}>
                      <span>Printing Subtotal</span>
                      <span style={{ color: "var(--primary)" }}>₹{printingTotal.toFixed(2)}</span>
                    </div>
                  </div>
                )}

                {/* Stationery items section */}
                {selectedStationery.length > 0 && (
                  <div style={{ marginTop: readyItems.length > 0 ? 12 : 0, marginBottom: 12 }}>
                    {readyItems.length > 0 && <div className="summary-divider" style={{ margin: "10px 0" }} />}
                    <div style={{ fontSize: ".8rem", fontWeight: 700, color: "var(--text-muted)", textTransform: "uppercase", letterSpacing: "0.05em", marginBottom: 6 }}>
                      Stationery Items
                    </div>
                    {selectedStationery.map((s) => (
                      <div key={s.id} style={{
                        display: "flex", justifyContent: "space-between", alignItems: "center",
                        fontSize: ".82rem", padding: "4px 0",
                      }}>
                        <div>
                          <span style={{ fontWeight: 600 }}>{s.quantity}x</span> {s.name}
                          <span style={{ color: "var(--text-muted)", fontSize: ".75rem", marginLeft: 4 }}>
                            (₹{s.price})
                          </span>
                        </div>
                        <span style={{ fontWeight: 700, color: "var(--text-main)" }}>
                          ₹{s.subtotal.toFixed(2)}
                        </span>
                      </div>
                    ))}
                    <div className="summary-row" style={{ fontWeight: 700, marginTop: 6 }}>
                      <span>Stationery Subtotal</span>
                      <span style={{ color: "var(--primary)" }}>₹{stationeryTotal.toFixed(2)}</span>
                    </div>
                  </div>
                )}

                <div className="summary-divider" />
                <div className="summary-total-row">
                  <span className="total-label">Grand Total</span>
                  <span className="total-price">₹{grandTotal.toFixed(2)}</span>
                </div>
              </>
            )}

            <button
              className="btn btn-primary w-full"
              onClick={handleProceedToPayment}
              disabled={placing || (readyItems.length === 0 && selectedStationery.length === 0) || fileItems.some((it) => it.inspecting)}
            >
              {placing ? (
                <><div className="loading-spinner" /> Preparing Order &amp; Payment…</>
              ) : isDemoMode ? (
                <><CreditCard size={18} /> Pay ₹{grandTotal.toFixed(2)} &amp; Confirm Order</>
              ) : (
                <><CreditCard size={18} /> Pay ₹{grandTotal.toFixed(2)} with Razorpay &amp; Confirm</>
              )}
            </button>

            <p style={{ fontSize: ".75rem", color: "var(--text-muted)", textAlign: "center", marginTop: 10, fontWeight: 400 }}>
              {isDemoMode
                ? "Online payment · Instant confirmation"
                : "Online payment via Razorpay · Instant confirmation"}
            </p>
          </div>
        </div>
      </div>

      {/* ── Razorpay Payment Modal ── */}
      {showPayment && activePendingOrder && (
        <PaymentModal
          order={activePendingOrder}
          orderAmount={activePendingOrder.total_price || grandTotal}
          studentDetails={{
            studentName,
            rollNumber,
            phoneNumber,
            email,
          }}
          onClose={() => setShowPayment(false)}
          onPaymentVerified={handlePaymentSuccess}
        />
      )}
    </div>
  );
}
