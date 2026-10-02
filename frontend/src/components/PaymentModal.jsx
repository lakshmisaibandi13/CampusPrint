/**
 * PaymentModal.jsx — Razorpay Standard Web Checkout Modal
 *
 * Flow:
 *   1. Receives CampusPrint order (created with status 'Pending')
 *   2. Calls POST /api/payment/create-order with order_id
 *   3. Backend calculates authoritative amount in paise and returns Razorpay order_id + key_id
 *   4. Opens Razorpay Standard Checkout (Test Mode / Live)
 *   5. On payment completion, sends signature to POST /api/payment/verify
 *   6. On backend verification success, displays confirmation and transitions to order queue
 */

import { useState, useEffect, useCallback, useRef } from "react";
import {
  X, CheckCircle, XCircle, AlertTriangle, CreditCard,
  ShieldCheck, RefreshCw, Loader, Lock, ArrowRight, Smartphone
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

export default function PaymentModal({
  order,
  orderAmount,
  studentDetails = {},
  onClose,
  onPaymentVerified,
}) {
  const [loading, setLoading] = useState(false);
  const [verifying, setVerifying] = useState(false);
  const [status, setStatus] = useState("ready"); // ready | in_checkout | verifying | success | error | cancelled
  const [errorMessage, setErrorMessage] = useState(null);
  const [successMessage, setSuccessMessage] = useState(null);
  const hasAutoLaunched = useRef(false);

  const displayAmount = order?.total_price ?? orderAmount ?? 0;
  const orderId = order?.order_id || "";
  const tokenNumber = order?.token_number || "";
  const displayNum = order?.display_order_number || order?.id || "";

  // ── Launch Razorpay Checkout ──────────────────────────────────────────────
  const handlePay = useCallback(async () => {
    if (!orderId) {
      setStatus("error");
      setErrorMessage("Unable to create payment: Order ID is missing.");
      return;
    }

    setLoading(true);
    setStatus("ready");
    setErrorMessage(null);
    setSuccessMessage(null);

    const API = getApiBase();

    try {
      // 1. Ensure Razorpay Checkout script is loaded
      const scriptLoaded = await loadRazorpayScript();
      if (!scriptLoaded || typeof window.Razorpay === "undefined") {
        throw new Error("Unable to load Razorpay payment gateway. Please check your internet connection.");
      }

      // 2. Call /api/payment/create-order to get authoritative Razorpay order
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

      // 3. Configure Razorpay Checkout options
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
          // 4. Server-side verification
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

            // 5. Verification succeeded!
            setVerifying(false);
            setStatus("success");
            setSuccessMessage("Payment successful — your order has been confirmed.");

            setTimeout(() => {
              if (onPaymentVerified) {
                onPaymentVerified(verifyData.order || order);
              }
            }, 1200);

          } catch (verifyErr) {
            setVerifying(false);
            setStatus("error");
            setErrorMessage("Payment verification failed. Please contact counter staff.");
          }
        },
      };

      // 4. Open Razorpay Checkout modal
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
  }, [orderId, displayAmount, displayNum, tokenNumber, studentDetails, order, onPaymentVerified]);

  // Auto-launch checkout on initial mount once order is ready
  useEffect(() => {
    if (!hasAutoLaunched.current && orderId) {
      hasAutoLaunched.current = true;
      handlePay();
    }
  }, [handlePay, orderId]);

  return (
    <div className="modal-backdrop" onClick={status === "verifying" ? undefined : onClose}>
      <div
        className="modal-content animate-fade"
        style={{ maxWidth: 520 }}
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="modal-header">
          <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
            <div style={{
              width: 38, height: 38, borderRadius: "var(--radius-md)",
              background: "var(--primary-light)", color: "var(--primary)",
              display: "flex", alignItems: "center", justifyContent: "center"
            }}>
              <CreditCard size={20} />
            </div>
            <div>
              <h3 style={{ fontSize: "1.2rem", fontWeight: 800 }}>Razorpay Online Payment</h3>
              <div style={{ fontSize: ".78rem", color: "var(--text-muted)" }}>
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

        {/* Order Details Card */}
        <div style={{
          background: "linear-gradient(135deg, #0f172a 0%, #1e293b 100%)",
          color: "#fff",
          borderRadius: "var(--radius-lg)",
          padding: "20px 24px",
          marginBottom: 20,
          boxShadow: "0 10px 25px -5px rgba(15, 23, 42, 0.3)"
        }}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: 14 }}>
            <div>
              <div style={{ fontSize: ".76rem", color: "#94a3b8", textTransform: "uppercase", letterSpacing: "0.06em", fontWeight: 700 }}>
                Order Summary
              </div>
              <div style={{ fontSize: "1.35rem", fontWeight: 800, color: "#fff", marginTop: 2 }}>
                Order #{displayNum}
                {tokenNumber && <span style={{ color: "#38bdf8", marginLeft: 8, fontSize: "1rem" }}>({tokenNumber})</span>}
              </div>
              <div style={{ fontSize: ".78rem", color: "#cbd5e1", marginTop: 2 }}>
                ID: {orderId}
              </div>
            </div>
            <div style={{ textAlign: "right" }}>
              <div style={{ fontSize: ".76rem", color: "#94a3b8", textTransform: "uppercase", letterSpacing: "0.06em", fontWeight: 700 }}>
                Amount to Pay
              </div>
              <div style={{ fontSize: "2rem", fontWeight: 800, color: "#38bdf8", fontFamily: "var(--font-heading)", lineHeight: 1.1 }}>
                ₹{Number(displayAmount).toFixed(2)}
              </div>
            </div>
          </div>

          {(studentDetails.studentName || order?.student_name) && (
            <div style={{
              borderTop: "1px solid rgba(255, 255, 255, 0.12)",
              paddingTop: 10,
              display: "flex",
              justifyContent: "space-between",
              fontSize: ".82rem",
              color: "#cbd5e1"
            }}>
              <span>Student: <strong>{studentDetails.studentName || order?.student_name}</strong></span>
              {(studentDetails.rollNumber || order?.roll_number) && (
                <span>Roll: <strong>{studentDetails.rollNumber || order?.roll_number}</strong></span>
              )}
            </div>
          )}
        </div>

        {/* Status Alerts */}
        {verifying && (
          <div className="alert alert-info animate-fade" style={{ marginBottom: 20, display: "flex", alignItems: "center", gap: 12 }}>
            <Loader size={20} className="spin-icon" style={{ flexShrink: 0, color: "var(--primary)" }} />
            <div>
              <strong style={{ display: "block" }}>Verifying payment server-side…</strong>
              <span style={{ fontSize: ".82rem" }}>Confirming cryptographic signature with bank. Please do not refresh.</span>
            </div>
          </div>
        )}

        {status === "success" && successMessage && (
          <div className="alert alert-success animate-fade" style={{ marginBottom: 20, display: "flex", alignItems: "center", gap: 12 }}>
            <CheckCircle size={22} style={{ flexShrink: 0, color: "#059669" }} />
            <div>
              <strong style={{ display: "block", color: "#065f46" }}>{successMessage}</strong>
              <span style={{ fontSize: ".82rem", color: "#047857" }}>Transitioning to order confirmation…</span>
            </div>
          </div>
        )}

        {status === "cancelled" && (
          <div className="alert animate-fade" style={{
            marginBottom: 20, display: "flex", alignItems: "center", gap: 12,
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

        {status === "error" && errorMessage && (
          <div className="alert alert-error animate-fade" style={{ marginBottom: 20, display: "flex", alignItems: "center", gap: 12 }}>
            <XCircle size={20} style={{ flexShrink: 0, color: "#dc2626" }} />
            <div>
              <strong style={{ display: "block" }}>Payment Error</strong>
              <span style={{ fontSize: ".82rem" }}>{errorMessage}</span>
            </div>
          </div>
        )}

        {/* Action Button */}
        {status !== "success" && (
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
              onClick={handlePay}
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

        {/* Security & Supported Methods Footer */}
        <div style={{
          marginTop: 22,
          paddingTop: 16,
          borderTop: "1px solid var(--border)",
          display: "flex",
          flexDirection: "column",
          gap: 8,
          alignItems: "center",
          textAlign: "center"
        }}>
          <div style={{
            display: "flex",
            alignItems: "center",
            gap: 14,
            fontSize: ".75rem",
            color: "var(--text-muted)",
            fontWeight: 600
          }}>
            <span style={{ display: "flex", alignItems: "center", gap: 4 }}>
              <ShieldCheck size={14} color="#059669" /> 256-bit Encrypted
            </span>
            <span>•</span>
            <span style={{ display: "flex", alignItems: "center", gap: 4 }}>
              <Smartphone size={14} color="var(--primary)" /> UPI / GPay / PhonePe
            </span>
            <span>•</span>
            <span>Cards &amp; NetBanking</span>
          </div>
          <div style={{ fontSize: ".72rem", color: "var(--text-subtle)" }}>
            Powered by Razorpay Standard Web Checkout · Direct Instant Confirmation
          </div>
        </div>
      </div>
    </div>
  );
}
