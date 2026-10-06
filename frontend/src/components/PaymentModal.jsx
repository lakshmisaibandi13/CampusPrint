/**
 * PaymentModal.jsx — CampusPrint Dual Payment Modal
 *
 * Supports:
 * 1. Demo Payment Mode (when DEMO_PAYMENT_MODE=true on backend):
 *    - Card payment (with 'Use Card' quick-fill and validation)
 *    - UPI payment (with UPI ID and transaction reference)
 *    - QR payment (with order payload and instant verification)
 *    - Net Banking payment (with SBI, HDFC, ICICI, Indian Bank, Axis Bank)
 *    - Professional UI matching modern payment gateways
 *    - Backend authoritative verification at POST /api/payment/demo
 *
 * 2. Razorpay Standard Web Checkout (when DEMO_PAYMENT_MODE=false):
 *    - Calls POST /api/payment/create-order
 *    - Launches official Razorpay Standard Checkout
 *    - Cryptographic signature verification at POST /api/payment/verify
 */

import { useState, useEffect, useCallback, useRef } from "react";
import QRCode from "qrcode";
import {
  X, CheckCircle, XCircle, AlertTriangle, CreditCard,
  ShieldCheck, RefreshCw, Loader, Lock, ArrowRight, Smartphone,
  QrCode, Building2, Check, Copy
} from "lucide-react";

const getApiBase = () => {
  if (typeof window !== "undefined") {
    if (window.location.hostname === "localhost" || window.location.hostname === "127.0.0.1") {
      return "/api";
    }
  }
  return "https://campusprint-syv1.onrender.com/api";
};

function loadRazorpayScript() {
  return new Promise((resolve) => {
    if (typeof window !== "undefined" && window.Razorpay) {
      resolve(true);
      return;
    }
    const existing = document.querySelector('script[src="https://checkout.razorpay.com/v1/checkout.js"]');
    if (existing) {
      existing.addEventListener("load", () => resolve(true));
      existing.addEventListener("error", () => resolve(false));
      return;
    }
    const script = document.createElement("script");
    script.src = "https://checkout.razorpay.com/v1/checkout.js";
    script.async = true;
    script.onload = () => resolve(true);
    script.onerror = () => resolve(false);
    document.body.appendChild(script);
  });
}

const DEMO_BANKS = [
  { id: "sbi", name: "State Bank of India (SBI)", code: "SBI", initials: "SBI" },
  { id: "hdfc", name: "HDFC Bank", code: "HDFC", initials: "HDFC" },
  { id: "icici", name: "ICICI Bank", code: "ICICI", initials: "ICICI" },
  { id: "indian", name: "Indian Bank", code: "INDB", initials: "IB" },
  { id: "axis", name: "Axis Bank", code: "AXIS", initials: "AXIS" },
];

function formatPaymentMethod(method) {
  if (!method) return "Card";
  const m = String(method).replace(/\bdemo\b/gi, "").trim();
  if (/qr/i.test(m)) return "QR Code";
  if (/net|bank/i.test(m)) return "Net Banking";
  if (/upi/i.test(m)) return "UPI";
  if (/card/i.test(m)) return "Card";
  return m || "Online Payment";
}

function formatPaymentId(id) {
  if (!id) return "";
  return String(id).replace(/CPDEMO-/g, "PAY-").replace(/DEMO-/g, "PAY-");
}

export default function PaymentModal({
  order,
  orderAmount,
  studentDetails = {},
  onClose,
  onPaymentVerified,
}) {
  const [demoMode, setDemoMode] = useState(null); // null (loading) | true | false
  const [loading, setLoading] = useState(false);
  const [verifying, setVerifying] = useState(false);
  const [status, setStatus] = useState("ready"); // ready | in_checkout | verifying | success | error | cancelled
  const [errorMessage, setErrorMessage] = useState(null);
  const [successData, setSuccessData] = useState(null);

  // Tabs: 'card' | 'upi' | 'qr' | 'netbanking'
  const [demoTab, setDemoTab] = useState("card");

  // Card form state
  const [cardName, setCardName] = useState(studentDetails.studentName || order?.student_name || "");
  const [cardNumber, setCardNumber] = useState("");
  const [cardExpiry, setCardExpiry] = useState("");
  const [cardCvv, setCardCvv] = useState("");
  const [cardError, setCardError] = useState("");

  // UPI state
  const [upiId, setUpiId] = useState("pay@campusprint");
  const [copiedUpi, setCopiedUpi] = useState(false);

  // QR state
  const [qrDataUrl, setQrDataUrl] = useState("");

  // Net banking state
  const [selectedBank, setSelectedBank] = useState(null);

  const hasAutoLaunchedRazorpay = useRef(false);

  const displayAmount = order?.total_price ?? orderAmount ?? 0;
  const orderId = order?.order_id || "";
  const tokenNumber = order?.token_number || "";
  const displayNum = order?.display_order_number || order?.id || "";
  const upiTxnId = orderId ? `PAY-${orderId}` : "PAY-TXN";

  // ── 1. Check Backend Payment Mode Configuration ───────────────────────────
  useEffect(() => {
    let isMounted = true;
    const API = getApiBase();

    fetch(`${API}/payment/config`)
      .then((res) => res.json())
      .then((data) => {
        if (isMounted) {
          const isDemo = Boolean(data && data.demo_payment_mode);
          setDemoMode(isDemo);
        }
      })
      .catch(() => {
        if (isMounted) {
          // Fallback to Razorpay if config unreachable
          setDemoMode(false);
        }
      });

    return () => {
      isMounted = false;
    };
  }, []);

  // ── 2. Generate QR Code Payload ───────────────────────────────────────────
  useEffect(() => {
    if (orderId && displayAmount) {
      const qrPayload = `CAMPUSPRINT\nORDER=${orderId}\nAMOUNT=₹${Number(displayAmount).toFixed(2)}`;
      QRCode.toDataURL(qrPayload, {
        width: 240,
        margin: 2,
        color: {
          dark: "#0f172a",
          light: "#ffffff",
        },
      })
        .then((url) => setQrDataUrl(url))
        .catch(() => {});
    }
  }, [orderId, displayAmount]);

  // ── 3. Fill Card Values ───────────────────────────────────────────────────
  const handleUseDemoCard = () => {
    setCardName(studentDetails.studentName || order?.student_name || "Cardholder");
    setCardNumber("4111 2222 3333 4444");
    setCardExpiry("12/28");
    setCardCvv("123");
    setCardError("");
  };

  // ── 4. Format Card Number Input ───────────────────────────────────────────
  const handleCardNumberChange = (e) => {
    const raw = e.target.value.replace(/\D/g, "").slice(0, 16);
    const parts = raw.match(/[\s\S]{1,4}/g) || [];
    setCardNumber(parts.join(" "));
    setCardError("");
  };

  // ── 5. Format Card Expiry Input ───────────────────────────────────────────
  const handleExpiryChange = (e) => {
    let raw = e.target.value.replace(/\D/g, "").slice(0, 4);
    if (raw.length >= 3) {
      raw = raw.slice(0, 2) + "/" + raw.slice(2);
    }
    setCardExpiry(raw);
    setCardError("");
  };

  // ── 6. Execute Payment Processing ─────────────────────────────────────────
  const handleDemoPayment = async (methodLabel, details = {}) => {
    if (!orderId) {
      setStatus("error");
      setErrorMessage("Unable to process payment: Order ID is missing.");
      return;
    }

    setVerifying(true);
    setStatus("verifying");
    setErrorMessage(null);
    setCardError("");

    const API = getApiBase();

    try {
      const res = await fetch(`${API}/payment/demo`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          order_id: orderId,
          payment_method: methodLabel,
          ...details,
        }),
      });

      const data = await res.json();
      if (!res.ok || !data.success) {
        throw new Error(data.error || "Payment processing failed.");
      }

      setVerifying(false);
      setStatus("success");
      setSuccessData({
        method: data.payment_method || methodLabel,
        transactionId: data.demo_transaction_id || data.transaction_id,
        orderStatus: data.order_status || "Order Received",
        updatedOrder: data.order,
      });

      // Transition to order confirmed view after brief confirmation display
      setTimeout(() => {
        if (onPaymentVerified) {
          onPaymentVerified(data.order || order);
        }
      }, 1400);

    } catch (err) {
      setVerifying(false);
      setStatus("error");
      setErrorMessage(err.message || "Payment processing failed. Please try again.");
    }
  };

  // ── 7. Validate & Submit Card ─────────────────────────────────────────────
  const handleCardSubmit = (e) => {
    e.preventDefault();
    const cleanNum = cardNumber.replace(/\s/g, "");
    if (!cardName.trim()) {
      setCardError("Please enter cardholder name.");
      return;
    }
    if (cleanNum.length !== 16) {
      setCardError("Card number must be 16 digits (e.g. 4111 2222 3333 4444).");
      return;
    }
    const expiryParts = cardExpiry.split("/");
    if (expiryParts.length !== 2 || expiryParts[0].length !== 2 || expiryParts[1].length !== 2) {
      setCardError("Expiry must be in MM/YY format (e.g. 12/28).");
      return;
    }
    const month = parseInt(expiryParts[0], 10);
    if (month < 1 || month > 12) {
      setCardError("Invalid expiry month (must be 01 - 12).");
      return;
    }
    if (cardCvv.length < 3) {
      setCardError("CVV must be 3 digits.");
      return;
    }

    handleDemoPayment("Demo Card", {
      cardholder_name: cardName.trim(),
      card_masked: `•••• •••• •••• ${cleanNum.slice(-4)}`,
    });
  };

  // ── 8. Razorpay Standard Checkout Flow (Active when DEMO_PAYMENT_MODE=false) ─
  const handleRazorpayPay = useCallback(async () => {
    if (!orderId) {
      setStatus("error");
      setErrorMessage("Unable to create payment: Order ID is missing.");
      return;
    }

    setLoading(true);
    setStatus("ready");
    setErrorMessage(null);

    const API = getApiBase();

    try {
      const scriptLoaded = await loadRazorpayScript();
      if (!scriptLoaded || typeof window.Razorpay === "undefined") {
        throw new Error("Unable to load Razorpay payment gateway. Please check your internet connection.");
      }

      const res = await fetch(`${API}/payment/create-order`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ order_id: orderId }),
      });

      const data = await res.json();
      if (!res.ok || !data.success) {
        throw new Error(data.error || "Unable to create payment.");
      }

      const { razorpay_key_id, razorpay_order_id, amount, currency } = data;

      const options = {
        key: razorpay_key_id,
        amount: amount,
        currency: currency || "INR",
        name: "CampusPrint",
        description: `Order #${displayNum} (${tokenNumber || orderId})`,
        order_id: razorpay_order_id,
        prefill: {
          name: studentDetails.studentName || order?.student_name || "",
          email: studentDetails.email || order?.email || "",
          contact: studentDetails.phoneNumber || order?.phone_number || "",
        },
        notes: {
          campusprint_order_id: orderId,
        },
        theme: {
          color: "#2563eb",
          backdrop_color: "rgba(15, 23, 42, 0.8)",
        },
        modal: {
          ondismiss: () => {
            setLoading(false);
            setStatus("cancelled");
            setErrorMessage("Payment cancelled. You can retry whenever you are ready.");
          },
        },
        handler: async (response) => {
          setLoading(false);
          setVerifying(true);
          setStatus("verifying");

          try {
            const verifyRes = await fetch(`${API}/payment/verify`, {
              method: "POST",
              headers: { "Content-Type": "application/json" },
              body: JSON.stringify({
                order_id: orderId,
                razorpay_order_id: response.razorpay_order_id,
                razorpay_payment_id: response.razorpay_payment_id,
                razorpay_signature: response.razorpay_signature,
              }),
            });

            const verifyData = await verifyRes.json();
            if (!verifyRes.ok || !verifyData.success) {
              setStatus("error");
              setErrorMessage(verifyData.error || "Payment verification failed. Please contact counter staff.");
              setVerifying(false);
              return;
            }

            setVerifying(false);
            setStatus("success");
            setSuccessData({
              method: "Razorpay",
              transactionId: response.razorpay_payment_id,
              orderStatus: "Order Received",
            });

            setTimeout(() => {
              if (onPaymentVerified) {
                onPaymentVerified(verifyData.order || order);
              }
            }, 1200);

          } catch {
            setVerifying(false);
            setStatus("error");
            setErrorMessage("Payment verification failed. Please contact counter staff.");
          }
        },
      };

      const rzp = new window.Razorpay(options);

      rzp.on("payment.failed", (failedResp) => {
        setLoading(false);
        setStatus("error");
        const reason = failedResp.error?.description || failedResp.error?.reason || "Payment failed.";
        setErrorMessage(`Payment failed: ${reason}`);
      });

      setStatus("in_checkout");
      setLoading(false);
      rzp.open();

    } catch (err) {
      setLoading(false);
      setStatus("error");
      setErrorMessage(err.message || "Unable to create payment.");
    }
  }, [orderId, displayNum, tokenNumber, studentDetails, order, onPaymentVerified]);

  // Auto-launch Razorpay only when demoMode is explicitly false
  useEffect(() => {
    if (demoMode === false && !hasAutoLaunchedRazorpay.current && orderId) {
      hasAutoLaunchedRazorpay.current = true;
      handleRazorpayPay();
    }
  }, [demoMode, handleRazorpayPay, orderId]);

  return (
    <div className="modal-backdrop" onClick={status === "verifying" ? undefined : onClose}>
      <div
        className="modal-content animate-fade"
        style={{ maxWidth: 560 }}
        onClick={(e) => e.stopPropagation()}
      >
        {/* ── Modal Header ── */}
        <div className="modal-header">
          <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
            <div style={{
              width: 42, height: 42, borderRadius: "var(--radius-md)",
              background: "var(--primary-light)",
              color: "var(--primary)",
              display: "flex", alignItems: "center", justifyContent: "center"
            }}>
              <CreditCard size={22} />
            </div>
            <div>
              <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                <h3 style={{ fontSize: "1.25rem", fontWeight: 800 }}>CampusPrint Payment</h3>
              </div>
              <div style={{ fontSize: ".8rem", color: "var(--text-muted)", fontWeight: 500 }}>
                Fast, secure UPI, Cards &amp; NetBanking
              </div>
            </div>
          </div>
          {status !== "verifying" && (
            <button className="modal-close" onClick={onClose} aria-label="Close modal">
              <X size={20} />
            </button>
          )}
        </div>

        {/* ── Order Summary Card ── */}
        <div style={{
          background: "linear-gradient(135deg, #0f172a 0%, #1e293b 100%)",
          color: "#fff",
          borderRadius: "var(--radius-lg)",
          padding: "18px 22px",
          marginBottom: 18,
          boxShadow: "0 10px 25px -5px rgba(15, 23, 42, 0.3)"
        }}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: 10 }}>
            <div>
              <div style={{ fontSize: ".74rem", color: "#94a3b8", textTransform: "uppercase", letterSpacing: "0.06em", fontWeight: 700 }}>
                Order Summary
              </div>
              <div style={{ fontSize: "1.25rem", fontWeight: 800, color: "#fff", marginTop: 2 }}>
                Order #{displayNum}
                {tokenNumber && <span style={{ color: "#38bdf8", marginLeft: 8, fontSize: ".95rem" }}>({tokenNumber})</span>}
              </div>
              <div style={{ fontSize: ".76rem", color: "#cbd5e1", marginTop: 2 }}>
                ID: {orderId}
              </div>
            </div>
            <div style={{ textAlign: "right" }}>
              <div style={{ fontSize: ".74rem", color: "#94a3b8", textTransform: "uppercase", letterSpacing: "0.06em", fontWeight: 700 }}>
                Amount to Pay
              </div>
              <div style={{ fontSize: "1.85rem", fontWeight: 800, color: "#38bdf8", fontFamily: "var(--font-heading)", lineHeight: 1.1 }}>
                ₹{Number(displayAmount).toFixed(2)}
              </div>
            </div>
          </div>

          {(studentDetails.studentName || order?.student_name) && (
            <div style={{
              borderTop: "1px solid rgba(255, 255, 255, 0.12)",
              paddingTop: 8,
              display: "flex",
              justifyContent: "space-between",
              fontSize: ".8rem",
              color: "#cbd5e1"
            }}>
              <span>Student: <strong>{studentDetails.studentName || order?.student_name}</strong></span>
              {(studentDetails.rollNumber || order?.roll_number) && (
                <span>Roll: <strong>{studentDetails.rollNumber || order?.roll_number}</strong></span>
              )}
            </div>
          )}
        </div>

        {/* ── Status Alerts ── */}
        {verifying && (
          <div className="alert alert-info animate-fade" style={{ marginBottom: 18, display: "flex", alignItems: "center", gap: 12 }}>
            <Loader size={20} className="spin-icon" style={{ flexShrink: 0, color: "var(--primary)" }} />
            <div>
              <strong style={{ display: "block" }}>Verifying payment server-side…</strong>
              <span style={{ fontSize: ".82rem" }}>
                Confirming payment with bank. Please do not refresh.
              </span>
            </div>
          </div>
        )}

        {status === "success" && (
          <div className="alert alert-success animate-fade" style={{
            marginBottom: 20, padding: "18px",
            background: "#ecfdf5", border: "1.5px solid #10b981", borderRadius: "var(--radius-md)"
          }}>
            <div style={{ display: "flex", alignItems: "center", gap: 12, marginBottom: 8 }}>
              <CheckCircle size={28} style={{ flexShrink: 0, color: "#059669" }} />
              <div>
                <h4 style={{ fontSize: "1.15rem", fontWeight: 800, color: "#065f46" }}>
                  Payment Successful
                </h4>
                <div style={{ fontSize: ".84rem", color: "#047857" }}>
                  Your payment has been verified.
                </div>
              </div>
            </div>
            <div style={{
              background: "rgba(255, 255, 255, 0.7)", borderRadius: "var(--radius-sm)",
              padding: "10px 14px", fontSize: ".84rem", color: "#064e3b", display: "grid", gap: 4
            }}>
              <div>Payment Method: <strong>{formatPaymentMethod(successData?.method)}</strong></div>
              <div>Payment ID: <strong style={{ fontFamily: "monospace" }}>{formatPaymentId(successData?.transactionId)}</strong></div>
              <div>Order Status: <strong>{successData?.orderStatus || "Order Received"}</strong></div>
            </div>
          </div>
        )}

        {status === "error" && errorMessage && (
          <div className="alert alert-error animate-fade" style={{ marginBottom: 18, display: "flex", alignItems: "center", gap: 12 }}>
            <XCircle size={20} style={{ flexShrink: 0, color: "#dc2626" }} />
            <div>
              <strong style={{ display: "block" }}>Payment Error</strong>
              <span style={{ fontSize: ".82rem" }}>{errorMessage}</span>
            </div>
          </div>
        )}

        {status === "cancelled" && (
          <div className="alert animate-fade" style={{
            marginBottom: 18, display: "flex", alignItems: "center", gap: 12,
            background: "#fffbeb", border: "1px solid #fde68a", color: "#92400e"
          }}>
            <AlertTriangle size={20} style={{ flexShrink: 0, color: "#d97706" }} />
            <div>
              <strong style={{ display: "block" }}>Payment cancelled</strong>
              <span style={{ fontSize: ".82rem" }}>
                {errorMessage || "You closed the payment window. Your documents remain saved. Click below to retry."}
              </span>
            </div>
          </div>
        )}

        {/* ── PAYMENT INTERFACE (When DEMO_PAYMENT_MODE=true) ──────────────── */}
        {demoMode && status !== "success" && (
          <div className="animate-fade">
            {/* Payment Method Tabs */}
            <div className="demo-tabs-nav">
              <button
                type="button"
                className={`demo-tab-button ${demoTab === "card" ? "active" : ""}`}
                onClick={() => setDemoTab("card")}
                disabled={verifying}
              >
                <CreditCard size={18} />
                <span>Card</span>
              </button>
              <button
                type="button"
                className={`demo-tab-button ${demoTab === "upi" ? "active" : ""}`}
                onClick={() => setDemoTab("upi")}
                disabled={verifying}
              >
                <Smartphone size={18} />
                <span>UPI ID</span>
              </button>
              <button
                type="button"
                className={`demo-tab-button ${demoTab === "qr" ? "active" : ""}`}
                onClick={() => setDemoTab("qr")}
                disabled={verifying}
              >
                <QrCode size={18} />
                <span>QR Code</span>
              </button>
              <button
                type="button"
                className={`demo-tab-button ${demoTab === "netbanking" ? "active" : ""}`}
                onClick={() => setDemoTab("netbanking")}
                disabled={verifying}
              >
                <Building2 size={18} />
                <span>Net Banking</span>
              </button>
            </div>

            {/* ── TAB 1: CARD ────────────────────────────────────────────── */}
            {demoTab === "card" && (
              <form onSubmit={handleCardSubmit} className="animate-fade">
                {/* Virtual Card Graphic Preview */}
                <div className="demo-virtual-card">
                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 12 }}>
                    <div className="demo-card-chip" />
                  </div>
                  <div className="demo-card-number-display">
                    {cardNumber || "•••• •••• •••• ••••"}
                  </div>
                  <div className="demo-card-footer">
                    <div>
                      <div style={{ fontSize: ".65rem", color: "#94a3b8", textTransform: "uppercase" }}>Cardholder</div>
                      <div style={{ fontWeight: 700, color: "#fff" }}>{cardName || "CARDHOLDER"}</div>
                    </div>
                    <div style={{ textAlign: "right" }}>
                      <div style={{ fontSize: ".65rem", color: "#94a3b8", textTransform: "uppercase" }}>Expires</div>
                      <div style={{ fontWeight: 700, color: "#fff" }}>{cardExpiry || "MM/YY"}</div>
                    </div>
                  </div>
                </div>

                {/* Auto-fill Button */}
                <div style={{ display: "flex", justifyContent: "flex-end", marginBottom: 12 }}>
                  <button
                    type="button"
                    className="btn btn-sm btn-outline"
                    onClick={handleUseDemoCard}
                    style={{ fontSize: ".8rem", color: "var(--primary)", borderColor: "var(--primary-border)" }}
                  >
                    <CreditCard size={14} /> Use Card
                  </button>
                </div>

                {/* Card Form Inputs */}
                <div className="form-group" style={{ marginBottom: 12 }}>
                  <label className="form-label" style={{ fontSize: ".82rem" }}>Cardholder Name *</label>
                  <input
                    type="text"
                    className="form-input"
                    placeholder="Aarav Sharma"
                    value={cardName}
                    onChange={(e) => { setCardName(e.target.value); setCardError(""); }}
                    disabled={verifying}
                  />
                </div>

                <div className="form-group" style={{ marginBottom: 12 }}>
                  <label className="form-label" style={{ fontSize: ".82rem" }}>Card Number *</label>
                  <input
                    type="text"
                    className="form-input"
                    placeholder="4111 2222 3333 4444"
                    maxLength={19}
                    value={cardNumber}
                    onChange={handleCardNumberChange}
                    disabled={verifying}
                  />
                </div>

                <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12, marginBottom: 16 }}>
                  <div className="form-group">
                    <label className="form-label" style={{ fontSize: ".82rem" }}>Expiry Date *</label>
                    <input
                      type="text"
                      className="form-input"
                      placeholder="MM/YY (e.g. 12/28)"
                      maxLength={5}
                      value={cardExpiry}
                      onChange={handleExpiryChange}
                      disabled={verifying}
                    />
                  </div>
                  <div className="form-group">
                    <label className="form-label" style={{ fontSize: ".82rem" }}>CVV *</label>
                    <input
                      type="password"
                      className="form-input"
                      placeholder="123"
                      maxLength={4}
                      value={cardCvv}
                      onChange={(e) => { setCardCvv(e.target.value.replace(/\D/g, "")); setCardError(""); }}
                      disabled={verifying}
                    />
                  </div>
                </div>

                {cardError && (
                  <div style={{ color: "#dc2626", fontSize: ".82rem", marginBottom: 12, fontWeight: 600 }}>
                    {cardError}
                  </div>
                )}

                <button
                  type="submit"
                  className="btn btn-primary w-full"
                  disabled={verifying}
                  style={{ padding: "12px", fontSize: "1rem" }}
                >
                  {verifying ? (
                    <><Loader size={18} className="spin-icon" /> Processing Payment…</>
                  ) : (
                    <><Lock size={16} /> Pay ₹{Number(displayAmount).toFixed(2)}</>
                  )}
                </button>
              </form>
            )}

            {/* ── TAB 2: UPI ──────────────────────────────────────────────── */}
            {demoTab === "upi" && (
              <div className="animate-fade">
                <div style={{
                  background: "var(--bg-subtle)", borderRadius: "var(--radius-md)",
                  padding: "16px", border: "1px solid var(--border)", marginBottom: 16
                }}>
                  <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 10 }}>
                    <Smartphone size={18} color="var(--primary)" />
                    <span style={{ fontSize: ".9rem", fontWeight: 700 }}>UPI Payment</span>
                  </div>

                  <div className="form-group" style={{ marginBottom: 12 }}>
                    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 4 }}>
                      <label className="form-label" style={{ fontSize: ".82rem", marginBottom: 0 }}>UPI ID</label>
                      <button
                        type="button"
                        onClick={() => {
                          if (navigator.clipboard) {
                            navigator.clipboard.writeText(upiId);
                            setCopiedUpi(true);
                            setTimeout(() => setCopiedUpi(false), 2000);
                          }
                        }}
                        style={{
                          background: "none", border: "none", color: copiedUpi ? "#059669" : "var(--primary)",
                          fontSize: ".74rem", fontWeight: 700, display: "flex", alignItems: "center", gap: 4, cursor: "pointer"
                        }}
                      >
                        {copiedUpi ? <><Check size={12} /> Copied</> : <><Copy size={12} /> Copy ID</>}
                      </button>
                    </div>
                    <input
                      type="text"
                      className="form-input"
                      value={upiId}
                      onChange={(e) => setUpiId(e.target.value)}
                      placeholder="student@upi"
                      disabled={verifying}
                    />
                  </div>

                  <div className="form-group">
                    <label className="form-label" style={{ fontSize: ".82rem" }}>Transaction ID</label>
                    <input
                      type="text"
                      className="form-input"
                      value={upiTxnId}
                      readOnly
                      style={{ background: "#f8fafc", fontFamily: "monospace" }}
                    />
                  </div>
                </div>

                <button
                  type="button"
                  className="btn btn-primary w-full"
                  onClick={() => handleDemoPayment("Demo UPI", { upi_id: upiId, transaction_ref: upiTxnId })}
                  disabled={verifying}
                  style={{ padding: "12px", fontSize: "1rem" }}
                >
                  {verifying ? (
                    <><Loader size={18} className="spin-icon" /> Verifying Payment…</>
                  ) : (
                    <><CheckCircle size={18} /> Verify Payment</>
                  )}
                </button>
              </div>
            )}

            {/* ── TAB 3: QR CODE ─────────────────────────────────────────── */}
            {demoTab === "qr" && (
              <div className="animate-fade" style={{ textAlign: "center" }}>
                <div style={{
                  background: "#fff", border: "2px solid var(--border)",
                  borderRadius: "var(--radius-lg)", padding: "20px", display: "inline-block",
                  marginBottom: 16, boxShadow: "var(--shadow-sm)"
                }}>
                  {qrDataUrl ? (
                    <img
                      src={qrDataUrl}
                      alt="CampusPrint QR Code"
                      style={{ width: 200, height: 200, display: "block", margin: "0 auto" }}
                    />
                  ) : (
                    <div style={{ width: 200, height: 200, display: "flex", alignItems: "center", justifyContent: "center" }}>
                      <Loader size={28} className="spin-icon" />
                    </div>
                  )}
                </div>

                <button
                  type="button"
                  className="btn btn-primary w-full"
                  onClick={() => handleDemoPayment("Demo QR")}
                  disabled={verifying}
                  style={{ padding: "12px", fontSize: "1rem" }}
                >
                  {verifying ? (
                    <><Loader size={18} className="spin-icon" /> Processing Payment…</>
                  ) : (
                    <><QrCode size={18} /> Pay ₹{Number(displayAmount).toFixed(2)}</>
                  )}
                </button>
              </div>
            )}

            {/* ── TAB 4: NET BANKING ──────────────────────────────────────── */}
            {demoTab === "netbanking" && (
              <div className="animate-fade">
                {!selectedBank ? (
                  <>
                    <div style={{ fontSize: ".84rem", color: "var(--text-muted)", marginBottom: 12, fontWeight: 600 }}>
                      Select your bank:
                    </div>

                    <div className="demo-bank-grid">
                      {DEMO_BANKS.map((b) => (
                        <div
                          key={b.id}
                          className="demo-bank-item"
                          onClick={() => setSelectedBank(b)}
                        >
                          <div className="demo-bank-avatar">{b.initials}</div>
                          <div style={{ fontWeight: 700, fontSize: ".86rem", color: "var(--text-main)" }}>
                            {b.name}
                          </div>
                        </div>
                      ))}
                    </div>
                  </>
                ) : (
                  <div className="animate-fade">
                    <div style={{
                      background: "var(--bg-subtle)", border: "1.5px solid var(--border)",
                      borderRadius: "var(--radius-md)", padding: "18px", marginBottom: 16
                    }}>
                      <div style={{ display: "flex", alignItems: "center", gap: 12, marginBottom: 12 }}>
                        <div className="demo-bank-avatar" style={{ background: "var(--primary-light)", color: "var(--primary)" }}>
                          {selectedBank.initials}
                        </div>
                        <div>
                          <div style={{ fontWeight: 800, fontSize: "1rem" }}>{selectedBank.name}</div>
                          <div style={{ fontSize: ".76rem", color: "var(--text-muted)" }}>Internet Banking Gateway</div>
                        </div>
                      </div>

                      <div style={{
                        background: "#fff", padding: "12px 14px", borderRadius: "var(--radius-sm)",
                        border: "1px solid var(--border)", fontSize: ".82rem", display: "grid", gap: 6
                      }}>
                        <div style={{ display: "flex", justifyContent: "space-between" }}>
                          <span style={{ color: "var(--text-muted)" }}>Merchant:</span>
                          <strong>CampusPrint MLRIT</strong>
                        </div>
                        <div style={{ display: "flex", justifyContent: "space-between" }}>
                          <span style={{ color: "var(--text-muted)" }}>Order Reference:</span>
                          <strong>{orderId}</strong>
                        </div>
                        <div style={{ display: "flex", justifyContent: "space-between" }}>
                          <span style={{ color: "var(--text-muted)" }}>Payable Amount:</span>
                          <strong style={{ color: "var(--primary)" }}>₹{Number(displayAmount).toFixed(2)}</strong>
                        </div>
                      </div>

                      <div style={{ fontSize: ".76rem", color: "#065f46", background: "#ecfdf5", padding: "8px 10px", borderRadius: "var(--radius-sm)", marginTop: 12 }}>
                        Bank-grade 256-bit SSL encrypted connection
                      </div>
                    </div>

                    <div style={{ display: "flex", gap: 10 }}>
                      <button
                        type="button"
                        className="btn btn-outline"
                        onClick={() => setSelectedBank(null)}
                        disabled={verifying}
                        style={{ flex: 1 }}
                      >
                        Change Bank
                      </button>
                      <button
                        type="button"
                        className="btn btn-primary"
                        onClick={() => handleDemoPayment("Demo Net Banking", { bank: selectedBank.name })}
                        disabled={verifying}
                        style={{ flex: 2 }}
                      >
                        {verifying ? (
                          <><Loader size={18} className="spin-icon" /> Processing Payment…</>
                        ) : (
                          <><Check size={18} /> Confirm Payment</>
                        )}
                      </button>
                    </div>
                  </div>
                )}
              </div>
            )}
          </div>
        )}

        {/* ── REAL RAZORPAY INTERFACE (When DEMO_PAYMENT_MODE=false) ───────── */}
        {demoMode === false && status !== "success" && (
          <div style={{ marginTop: 10 }}>
            <button
              className="btn btn-primary w-full"
              style={{
                padding: "14px 20px",
                fontSize: "1.02rem",
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                gap: 10,
                boxShadow: "0 4px 14px rgba(37, 99, 235, 0.35)"
              }}
              onClick={handleRazorpayPay}
              disabled={loading || verifying}
            >
              {loading ? (
                <>
                  <Loader size={18} className="spin-icon" />
                  <span>Opening Razorpay Checkout…</span>
                </>
              ) : verifying ? (
                <>
                  <Loader size={18} className="spin-icon" />
                  <span>Verifying Payment…</span>
                </>
              ) : status === "cancelled" || status === "error" ? (
                <>
                  <RefreshCw size={18} />
                  <span>Retry Payment (₹{Number(displayAmount).toFixed(2)})</span>
                </>
              ) : (
                <>
                  <Lock size={18} />
                  <span>Pay ₹{Number(displayAmount).toFixed(2)} via Razorpay</span>
                  <ArrowRight size={18} />
                </>
              )}
            </button>
          </div>
        )}

        {/* ── Loading Backend Config State ── */}
        {demoMode === null && (
          <div style={{ padding: "30px 0", textAlign: "center", color: "var(--text-muted)" }}>
            <Loader size={24} className="spin-icon" style={{ margin: "0 auto 8px" }} />
            <div style={{ fontSize: ".85rem" }}>Initializing secure payment environment…</div>
          </div>
        )}

        {/* ── Security Footer ── */}
        <div style={{
          marginTop: 20,
          paddingTop: 14,
          borderTop: "1px solid var(--border)",
          display: "flex",
          flexDirection: "column",
          gap: 6,
          alignItems: "center",
          textAlign: "center"
        }}>
          <div style={{
            display: "flex",
            alignItems: "center",
            gap: 12,
            fontSize: ".75rem",
            color: "var(--text-muted)",
            fontWeight: 600,
            flexWrap: "wrap",
            justifyContent: "center"
          }}>
            <span style={{ display: "flex", alignItems: "center", gap: 4 }}>
              <ShieldCheck size={14} color="#059669" /> Safe &amp; Protected
            </span>
            <span>•</span>
            <span>Cards</span>
            <span>•</span>
            <span>UPI ID</span>
            <span>•</span>
            <span>QR Code</span>
            <span>•</span>
            <span>Net Banking</span>
          </div>
          <div style={{ fontSize: ".72rem", color: "var(--text-subtle)" }}>
            {demoMode
              ? "End-to-end encrypted · Direct instant confirmation"
              : "Powered by Razorpay Standard Web Checkout · Direct Instant Confirmation"}
          </div>
        </div>
      </div>
    </div>
  );
}
