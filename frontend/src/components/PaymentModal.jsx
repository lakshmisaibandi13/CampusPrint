/**
 * PaymentModal.jsx — UPI-only payment with real QR, countdown, screenshot verify
 *
 * Flow:
 *   1. Create 10-min payment session via POST /api/payment/session
 *   2. Show real QR image (/payment_qr.png) + dynamic amount + countdown
 *   3. User pays via UPI app, takes screenshot
 *   4. User uploads screenshot → POST /api/payment/session/<id>/verify
 *   5. Show per-check verification result
 *   6. On success → call onPaymentVerified(sessionId, transactionRef)
 */

import { useState, useEffect, useRef, useCallback } from "react";
import {
  X, Upload, CheckCircle, XCircle, AlertTriangle,
  Clock, RefreshCw, ImagePlus, CreditCard, Info
} from "lucide-react";

const API = "https://campusprint-syv1.onrender.com/api/payment";
const VERIFY_WINDOW_SECONDS = 600; // 10 minutes

// ── Helpers ──────────────────────────────────────────────────────────────────
function fmt(seconds) {
  const m = Math.floor(Math.max(0, seconds) / 60).toString().padStart(2, "0");
  const s = (Math.max(0, seconds) % 60).toString().padStart(2, "0");
  return `${m}:${s}`;
}

// Friendly label for each check key
const CHECK_LABELS = {
  screenshot_content: "Screenshot content",
  amount:             "Payment amount",
  receiver:           "Merchant / receiver",
  transaction_id:     "Transaction reference ID",
  time_window:        "Payment time",
  payment_date:       "Payment date",
  ocr_setup:          "Verification system",
  ocr_read:           "Screenshot readability",
};

function CheckRow({ checkKey, check }) {
  const label = CHECK_LABELS[checkKey] || checkKey;
  const isWarning = check.warning && !check.passed;

  let icon, color;
  if (check.passed) {
    icon  = <CheckCircle  size={15} />;
    color = "#059669";
  } else if (isWarning) {
    icon  = <AlertTriangle size={15} />;
    color = "#d97706";
  } else {
    icon  = <XCircle size={15} />;
    color = "#dc2626";
  }

  return (
    <div style={{
      display: "flex", alignItems: "flex-start", gap: 8,
      padding: "5px 0",
      borderBottom: "1px solid rgba(0,0,0,.06)",
    }}>
      <span style={{ color, flexShrink: 0, marginTop: 1 }}>{icon}</span>
      <div style={{ fontSize: ".82rem", flex: 1 }}>
        <span style={{ fontWeight: 700, color: "var(--text-main)" }}>{label}: </span>
        <span style={{ color: check.passed ? "#065f46" : isWarning ? "#92400e" : "#b91c1c" }}>
          {check.message}
        </span>
      </div>
    </div>
  );
}

// ── Main component ────────────────────────────────────────────────────────────
export default function PaymentModal({ orderAmount, existingSessionId, onSessionCreated, onClose, onPaymentVerified }) {
  // Session
  const [sessionId,      setSessionId]      = useState(null);
  const [sessionLoading, setSessionLoading] = useState(true);
  const [sessionError,   setSessionError]   = useState(null);

  // Merchant identity — populated from the session response so it is always
  // in sync with whatever QR / Config was active when the session was created.
  const [merchantName, setMerchantName] = useState("CampusPrint");
  const [merchantUpi,  setMerchantUpi]  = useState("campusprint@upi");

  // Countdown
  const [remainingSec, setRemainingSec] = useState(VERIFY_WINDOW_SECONDS);
  const [expired,      setExpired]      = useState(false);
  const timerRef = useRef(null);

  // Screenshot upload
  const [screenshotFile,    setScreenshotFile]    = useState(null);
  const [screenshotPreview, setScreenshotPreview] = useState(null);
  const [dragActive,        setDragActive]        = useState(false);
  const fileInputRef = useRef(null);

  // Verification
  const [verifying,          setVerifying]          = useState(false);
  const [verificationResult, setVerificationResult] = useState(null);

  // QR image load error (fallback)
  const [qrError, setQrError] = useState(false);

  // ── Create / resume session on mount ──────────────────────────────────────
  // Uses POST /api/payment/session/resume which returns an existing unexpired
  // session when one already exists for this amount, preventing timer resets
  // when the modal is closed and reopened.
  const startSession = useCallback(async (forceNew = false) => {
    setSessionLoading(true);
    setSessionError(null);
    setExpired(false);
    setVerificationResult(null);
    setScreenshotFile(null);
    setScreenshotPreview(null);
    try {
      const body = { order_amount: orderAmount };
      // Pass the existing session ID (if any) so the backend can resume it
      if (!forceNew && existingSessionId) {
        body.session_id = existingSessionId;
      }
      const res  = await fetch(`${API}/session/resume`, {
        method:  "POST",
        headers: { "Content-Type": "application/json" },
        body:    JSON.stringify(body),
      });
      const data = await res.json();
      if (!data.success) throw new Error(data.error || "Failed to create payment session");
      setSessionId(data.session_id);
      setRemainingSec(data.remaining_seconds ?? VERIFY_WINDOW_SECONDS);
      // Update displayed merchant info from the session (dynamic, never hardcoded)
      if (data.merchant_name) setMerchantName(data.merchant_name);
      if (data.merchant_upi)  setMerchantUpi(data.merchant_upi);
      // Notify parent to persist the session ID across modal unmounts
      if (onSessionCreated) onSessionCreated(data.session_id);
    } catch (err) {
      setSessionError(err.message);
    } finally {
      setSessionLoading(false);
    }
  }, [orderAmount, existingSessionId, onSessionCreated]);

  useEffect(() => { startSession(); return () => clearInterval(timerRef.current); }, [startSession]);

  // ── Countdown tick ─────────────────────────────────────────────────────────
  useEffect(() => {
    if (!sessionId || expired || sessionLoading) return;
    clearInterval(timerRef.current);
    timerRef.current = setInterval(() => {
      setRemainingSec((prev) => {
        if (prev <= 1) { setExpired(true); clearInterval(timerRef.current); return 0; }
        return prev - 1;
      });
    }, 1000);
    return () => clearInterval(timerRef.current);
  }, [sessionId, expired, sessionLoading]);

  // ── File selection ─────────────────────────────────────────────────────────
  function handleFileSelect(file) {
    if (!file) return;
    const ok = ["image/png", "image/jpeg", "image/jpg", "image/webp"];
    if (!ok.includes(file.type)) {
      alert("Please upload a PNG, JPG/JPEG, or WEBP image.");
      return;
    }
    setScreenshotFile(file);
    setVerificationResult(null);
    const reader = new FileReader();
    reader.onload = (e) => setScreenshotPreview(e.target.result);
    reader.readAsDataURL(file);
  }

  function onDrop(e) {
    e.preventDefault();
    setDragActive(false);
    handleFileSelect(e.dataTransfer.files[0]);
  }

  // ── Verify screenshot ──────────────────────────────────────────────────────
  async function handleVerify() {
    if (!screenshotFile || !sessionId || expired) return;
    setVerifying(true);
    setVerificationResult(null);
    try {
      const fd = new FormData();
      fd.append("screenshot", screenshotFile);
      const res  = await fetch(`${API}/session/${sessionId}/verify`, { method: "POST", body: fd });
      const data = await res.json();
      setVerificationResult(data);
      if (data.success) {
        setTimeout(() => onPaymentVerified(sessionId, data.transaction_ref), 1800);
      }
    } catch {
      setVerificationResult({ success: false, message: "Network error. Please try again.", checks: {} });
    } finally {
      setVerifying(false);
    }
  }

  // ── Guards ─────────────────────────────────────────────────────────────────
  const isUrgent = remainingSec <= 60 && !expired;

  if (sessionLoading) {
    return (
      <div className="modal-backdrop">
        <div className="modal-content" style={{ textAlign: "center", padding: 48 }}>
          <div className="loading-spinner dark"
               style={{ margin: "0 auto 16px", width: 36, height: 36, borderWidth: 3 }} />
          <p style={{ color: "var(--text-muted)" }}>Setting up payment session…</p>
        </div>
      </div>
    );
  }

  if (sessionError) {
    return (
      <div className="modal-backdrop">
        <div className="modal-content">
          <div className="modal-header">
            <h2 style={{ fontSize: "1.2rem", fontWeight: 700 }}>Payment Setup Failed</h2>
            <button className="modal-close" onClick={onClose}><X size={20} /></button>
          </div>
          <div className="alert alert-error" style={{ marginBottom: 16 }}>{sessionError}</div>
          <div style={{ display: "flex", gap: 12 }}>
            <button className="btn btn-primary w-full" onClick={() => startSession(false)}>
              <RefreshCw size={16} /> Try Again
            </button>
            <button className="btn btn-outline w-full" onClick={onClose}>Cancel</button>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div
      className="modal-backdrop"
      onClick={(e) => e.target === e.currentTarget && onClose()}
    >
      <div className="modal-content animate-fade">

        {/* ── Header ── */}
        <div className="modal-header">
          <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
            <CreditCard size={22} color="var(--primary)" />
            <h2 style={{ fontSize: "1.2rem", fontWeight: 700 }}>UPI Payment</h2>
          </div>
          <button className="modal-close" onClick={onClose}><X size={20} /></button>
        </div>

        {/* ── Amount ── */}
        <div className="payment-amount-display">
          <div className="payment-amount-label">Amount to Pay</div>
          <div className="payment-amount-value">₹{orderAmount.toFixed(2)}</div>
          <div style={{ fontSize: ".78rem", color: "var(--text-muted)", marginTop: 4 }}>
            Merchant: {merchantName} · {merchantUpi}
          </div>
        </div>

        {/* ── QR + countdown row ── */}
        <div className="qr-section">

          {/* Real QR image */}
          <div className="qr-box">
            {!qrError ? (
              <img
                src="/payment_qr.png"
                alt="CampusPrint UPI QR Code"
                style={{
                  width: 200, height: 200,
                  objectFit: "contain",
                  borderRadius: "var(--radius-sm)",
                  display: "block",
                }}
                onError={() => setQrError(true)}
              />
            ) : (
              /* Fallback if image file missing */
              <div style={{
                width: 200, height: 200,
                display: "flex", flexDirection: "column",
                alignItems: "center", justifyContent: "center",
                gap: 8, border: "2px dashed #93c5fd",
                borderRadius: "var(--radius-md)",
                background: "var(--primary-light)",
                color: "var(--primary)",
              }}>
                <Info size={36} />
                <span style={{ fontSize: ".78rem", fontWeight: 700, textAlign: "center", padding: "0 8px" }}>
                  QR image not found.<br />Ask staff for UPI ID.
                </span>
              </div>
            )}
            <span className="qr-upi-id" style={{ marginTop: 6 }}>{merchantUpi}</span>
          </div>

          {/* Instructions */}
          <div style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 8 }}>
            <p className="qr-instruction">
              Open GPay / PhonePe / Paytm · Scan QR · Pay <strong>₹{orderAmount.toFixed(2)}</strong> to <strong>{merchantName}</strong> · Take a screenshot
            </p>

            {/* Countdown */}
            {!expired ? (
              <div className="countdown-wrapper">
                <span className="countdown-label">
                  <Clock size={12} style={{ display: "inline", marginRight: 4 }} />
                  Verification window
                </span>
                <span className={`countdown-timer${isUrgent ? " urgent" : ""}`}>
                  {fmt(remainingSec)}
                </span>
                {isUrgent && (
                  <span style={{ fontSize: ".73rem", color: "#ef4444", fontWeight: 600 }}>
                    Less than a minute left!
                  </span>
                )}
              </div>
            ) : (
              <div className="countdown-wrapper">
                <span className="countdown-timer expired">00:00</span>
                <span className="countdown-expired-msg">Verification window expired</span>
                <button
                  className="btn btn-primary btn-sm"
                  style={{ marginTop: 8 }}
                  onClick={() => startSession(true)}
                >
                  <RefreshCw size={14} /> Restart Payment Session
                </button>
              </div>
            )}
          </div>
        </div>

        {/* ── Screenshot upload (only when not expired) ── */}
        {!expired && (
          <>
            <div style={{
              fontWeight: 700, fontSize: ".95rem", marginBottom: 8,
              color: "var(--text-main)",
            }}>
              Upload Payment Screenshot
            </div>

            {screenshotPreview ? (
              <div style={{ marginBottom: 12 }}>
                <div className="screenshot-preview">
                  <img src={screenshotPreview} alt="Payment screenshot preview" />
                </div>
                <div style={{
                  display: "flex", justifyContent: "space-between",
                  alignItems: "center", marginTop: 6,
                }}>
                  <span style={{ fontSize: ".82rem", color: "var(--text-muted)" }}>
                    {screenshotFile?.name}
                  </span>
                  <button
                    style={{ fontSize: ".78rem", color: "var(--primary)", background: "none", border: "none", cursor: "pointer" }}
                    onClick={() => {
                      setScreenshotFile(null);
                      setScreenshotPreview(null);
                      setVerificationResult(null);
                    }}
                  >
                    Change
                  </button>
                </div>
              </div>
            ) : (
              <div
                className={`screenshot-upload-area${dragActive ? " drag-active" : ""}`}
                onClick={() => fileInputRef.current?.click()}
                onDragOver={(e) => { e.preventDefault(); setDragActive(true); }}
                onDragLeave={() => setDragActive(false)}
                onDrop={onDrop}
              >
                <ImagePlus size={34} style={{ color: "var(--primary)", marginBottom: 6 }} />
                <div style={{ fontWeight: 700, marginBottom: 4, fontSize: ".9rem" }}>
                  Click or drag your payment screenshot here
                </div>
                <div style={{ fontSize: ".75rem", color: "var(--text-muted)" }}>
                  PNG · JPG · JPEG · WEBP · Max 10 MB
                </div>
              </div>
            )}

            <input
              ref={fileInputRef}
              type="file"
              accept="image/png,image/jpeg,image/jpg,image/webp"
              style={{ display: "none" }}
              onChange={(e) => handleFileSelect(e.target.files[0])}
            />

            {/* ── Verification result ── */}
            {verificationResult && (
              <div
                className={`verification-result ${verificationResult.success ? "success" : "failed"} animate-fade`}
                style={{ marginTop: 14 }}
              >
                {/* Title */}
                <div className="verification-result-title" style={{ marginBottom: 10 }}>
                  {verificationResult.success
                    ? "✓ Payment Verified Successfully"
                    : "✗ Payment Verification Failed"}
                </div>

                {/* Per-check rows */}
                {verificationResult.checks &&
                  Object.entries(verificationResult.checks).map(([key, check]) => (
                    <CheckRow key={key} checkKey={key} check={check} />
                  ))
                }

                {/* Transaction ref */}
                {verificationResult.transaction_ref && (
                  <div style={{
                    marginTop: 8, fontSize: ".78rem",
                    color: "var(--text-muted)",
                    background: "rgba(0,0,0,.04)",
                    padding: "4px 8px", borderRadius: "var(--radius-sm)",
                  }}>
                    Transaction Ref: <strong>{verificationResult.transaction_ref}</strong>
                  </div>
                )}

                {/* Prototype note */}
                {verificationResult.prototype_note && (
                  <div className="prototype-note" style={{ marginTop: 8 }}>
                    ℹ {verificationResult.prototype_note}
                  </div>
                )}

                {/* Top-level failure message when no checks returned */}
                {!verificationResult.success &&
                  (!verificationResult.checks ||
                    Object.keys(verificationResult.checks).length === 0) && (
                  <div style={{ fontSize: ".88rem", color: "#b91c1c", marginTop: 4 }}>
                    {verificationResult.message}
                  </div>
                )}
              </div>
            )}

            {/* ── Verify button ── */}
            <button
              className="btn btn-primary w-full"
              style={{ marginTop: 14 }}
              onClick={handleVerify}
              disabled={!screenshotFile || verifying || !!verificationResult?.success}
            >
              {verifying ? (
                <><div className="loading-spinner" /> Verifying…</>
              ) : verificationResult?.success ? (
                <><CheckCircle size={18} /> Payment Verified — Proceeding…</>
              ) : (
                <><Upload size={18} /> Verify Payment</>
              )}
            </button>
          </>
        )}

        {/* ── Expired — block upload ── */}
        {expired && !verificationResult?.success && (
          <div className="alert alert-error" style={{ marginTop: 14 }}>
            <XCircle size={16} style={{ flexShrink: 0 }} />
            The 10-minute verification window has expired. Please restart the payment session.
          </div>
        )}

        <button
          className="btn btn-outline w-full"
          style={{ marginTop: 12 }}
          onClick={onClose}
        >
          Cancel / Go Back
        </button>

        <p style={{ fontSize: ".72rem", color: "var(--text-subtle)", textAlign: "center", marginTop: 10 }}>
          🔒 Prototype UPI payment · Demo verification layer
        </p>
      </div>
    </div>
  );
}
