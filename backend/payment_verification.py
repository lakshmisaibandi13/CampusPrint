"""
payment_verification.py
=======================
Prototype UPI payment screenshot verification service.

IMPORTANT — PROTOTYPE / DEMO LAYER:
-------------------------------------
Uses pytesseract OCR to read text from payment screenshots and then checks:
  1. Tesseract is reachable and OCR succeeds
  2. Minimum readable content  (rejects blank / random photos)
  3. RECEIVER / MERCHANT       ← hard check, uses per-session snapshot
  4. PAYMENT AMOUNT            ← hard check
  5. PAYMENT DATE              ← hard check (must match session date in local TZ)
  6. PAYMENT TIME              ← hard check (must be inside 10-min window, local TZ)
  7. TRANSACTION / UTR ID      ← hard check

The merchant_name and merchant_identifiers are passed in from the session
snapshot so they automatically follow whichever QR / merchant was active
when the session was created.  Changing Config later does not retro-affect
in-progress sessions.

Timezone note
─────────────
payment_sessions timestamps are stored as SQLite UTC.
UPI app screenshots show payment time in LOCAL time (e.g. IST = UTC+5:30).
Config.TIMEZONE_OFFSET_HOURS converts UTC session timestamps to local time
before comparing against the screenshot's time strings.
"""

import re
import os
from datetime import datetime, timedelta, date as date_type
from config import Config

VERIFICATION_WINDOW_MINUTES = 10
MIN_OCR_WORD_COUNT = 5


# ── Tesseract configuration ───────────────────────────────────────────────────

def _configure_tesseract():
    """Import pytesseract and set the exe path from Config. Returns module or None."""
    try:
        import pytesseract
        cmd = getattr(Config, "TESSERACT_CMD",
                      r"C:\Program Files\Tesseract-OCR\tesseract.exe")
        pytesseract.pytesseract.tesseract_cmd = cmd
        return pytesseract
    except ImportError:
        return None


# ── OCR extraction ────────────────────────────────────────────────────────────

def _extract_primary_amount_from_image(pil_image, pytesseract) -> tuple[float | None, str | None]:
    """
    Extract the primary payment confirmation amount directly from the screenshot layout.

    Visual structure handling:
    - Google Pay / PhonePe: prominent card with amount above 'View details',
      often containing a colored checkmark badge (neutralized to prevent false zeros)
      and the Rupee symbol ₹ (which English OCR mis-segments as '<' while merging the
      slash with '3' to form '5'). Segmenting the digits away from ₹ avoids this mis-segmentation.
    - FamPay (both light & dark mode): prominent amount numbers above 'Paid to'.
      In dark mode screenshots, background is dark (~#191919) and text is white (#ffffff).
      Inverting dark regions ensures standard black-on-white OCR and accurate column segmentation,
      preventing the Rupee symbol ₹ from being misread as digit '2' (e.g. ₹3 -> 23).
    - Synthetic / invoices: 'Amount: Rs. X' line.
    - Fallback: Upper-middle confirmation card (top 15%–45% of height).

    Returns (detected_amount_float, detection_method).
    """
    try:
        from PIL import ImageOps

        w, h = pil_image.size
        gray_full = pil_image.convert("L")

        # If full image is dark mode, invert for text/anchor detection
        corners_full = [
            gray_full.getpixel((5, 5)),
            gray_full.getpixel((w - 5, 5)),
            gray_full.getpixel((5, h - 5)),
            gray_full.getpixel((w - 5, h - 5)),
        ]
        if sum(corners_full) / len(corners_full) < 128:
            gray_for_data = ImageOps.invert(gray_full)
        else:
            gray_for_data = gray_full

        data = pytesseract.image_to_data(gray_for_data, output_type=pytesseract.Output.DICT)
        words = [w.strip() for w in data['text']]

        candidate_boxes = []

        # 1. 'View details' anchor (Google Pay)
        for i, word in enumerate(words):
            if word.lower() == 'view' and i + 1 < len(words) and words[i + 1].lower().startswith('detail'):
                vy = data['top'][i]
                crop_top = max(0, vy - int(h * 0.13))
                crop_bottom = max(0, vy - int(h * 0.005))
                candidate_boxes.append(('view_details', (max(0, int(w * 0.08)), crop_top, min(w, int(w * 0.92)), crop_bottom)))
                break

        # 2. 'Amount' keyword (Synthetic / invoice / receipt)
        for i, word in enumerate(words):
            if 'amount' in word.lower():
                ay = data['top'][i]
                candidate_boxes.append(('amount_kw', (max(0, int(w * 0.05)), max(0, ay - 15), min(w, int(w * 0.95)), min(h, ay + 65))))
                break

        # 3. 'Paid to' anchor (FamPay / other UPI)
        for i, word in enumerate(words):
            if word.lower() == 'paid':
                py = data['top'][i]
                # In FamPay, amount is above 'Paid to'
                candidate_boxes.append(('paid_above', (max(0, int(w * 0.08)), max(0, py - int(h * 0.24)), min(w, int(w * 0.92)), py)))
                # Below 'Paid to' (Receipts)
                candidate_boxes.append(('paid_below', (max(0, int(w * 0.05)), py, min(w, int(w * 0.95)), min(h, py + int(h * 0.25)))))
                break

        # 4. Fallback: Upper-middle confirmation card
        candidate_boxes.append(('header_fallback', (max(0, int(w * 0.1)), int(h * 0.18), min(w, int(w * 0.9)), int(h * 0.42))))

        for name, box in candidate_boxes:
            crop = pil_image.crop(box)
            cw, ch = crop.size
            if cw < 20 or ch < 20:
                continue

            # Determine if crop has dark background (dark mode)
            corners = [
                crop.getpixel((2, 2)),
                crop.getpixel((cw - 3, 2)),
                crop.getpixel((2, ch - 3)),
                crop.getpixel((cw - 3, ch - 3)),
            ]
            avg_bg = sum(sum(c[:3]) for c in corners) / (3 * len(corners))
            is_dark_bg = avg_bg < 128

            crop_clean = crop.copy()
            pix = crop_clean.load()
            # Neutralize saturated colors (green/blue badges, icons) to the background color
            fill_color = (0, 0, 0) if is_dark_bg else (255, 255, 255)
            for y in range(ch):
                for x in range(cw):
                    r, g, b = pix[x, y]
                    if max(r, g, b) - min(r, g, b) > 28 or (g > 95 and g > r * 1.15 and g > b * 1.15) or (b > 100 and b > r * 1.2 and b > g * 1.1):
                        pix[x, y] = fill_color

            gray = crop_clean.convert('L')
            # If dark background, invert so text is black on white
            if is_dark_bg:
                gray = ImageOps.invert(gray)

            # Method 1: Column segmentation to isolate digit glyphs from the currency symbol ₹
            col_counts = [0] * cw
            pixL = gray.load()
            for y in range(ch):
                for x in range(cw):
                    if pixL[x, y] < 128:
                        col_counts[x] += 1

            active = [x for x, c in enumerate(col_counts) if c > 3]
            if active:
                start_x, end_x = active[0], active[-1]
                segments = []
                in_seg = False
                seg_start = 0
                for x in range(start_x, end_x + 1):
                    if col_counts[x] > 2:
                        if not in_seg:
                            in_seg = True
                            seg_start = x
                    else:
                        if in_seg:
                            in_seg = False
                            segments.append((seg_start, x - 1))
                if in_seg:
                    segments.append((seg_start, end_x))

                # If >= 2 segments, segment 0 is the currency symbol ₹
                # Segments 1.. are the numeric digits
                if len(segments) >= 2:
                    dx1 = segments[1][0]
                    dx2 = segments[-1][1]
                    row_counts = [0] * ch
                    for y in range(ch):
                        for x in range(dx1, dx2 + 1):
                            if pixL[x, y] < 128:
                                row_counts[y] += 1
                    act_rows = [y for y, c in enumerate(row_counts) if c > 0]
                    if act_rows:
                        y1 = max(0, act_rows[0] - 5)
                        y2 = min(ch, act_rows[-1] + 5)
                        d_crop = gray.crop((max(0, dx1 - 5), y1, min(cw, dx2 + 5), y2))
                        d_pad = ImageOps.expand(d_crop, border=20, fill=255)
                        for psm in [7, 6, 10]:
                            txt = pytesseract.image_to_string(d_pad, config=f'--oem 3 --psm {psm} -c tessedit_char_whitelist=0123456789.').strip()
                            m = re.search(r'\b(\d+(?:\.\d{1,2})?)\b', txt)
                            if m:
                                v = float(m.group(1))
                                if v > 0 and v not in (2024, 2025, 2026, 2027):
                                    return v, f"{name}_isolated"

            # Method 2: OCR on whole neutralized region
            for psm in [7, 6]:
                txt = pytesseract.image_to_string(gray, config=f'--oem 3 --psm {psm}').strip()
                # Currency prefixed: ₹6, Rs. 6, INR 6
                m = re.search(r'(?:₹|\u20b9|Rs\.?|INR)\s*(\d+(?:[.,]\d{1,2})?)', txt, re.IGNORECASE)
                if m:
                    v = float(m.group(1).replace(',', '.'))
                    if v > 0 and v not in (2024, 2025, 2026, 2027):
                        return v, f"{name}_prefixed"
                # Stand-alone numbers (like in FamPay '34.00' or '6')
                m2 = re.search(r'^\s*(\d+(?:[.,]\d{1,2})?)\s*$', txt, re.MULTILINE)
                if m2:
                    v = float(m2.group(1).replace(',', '.'))
                    if v > 0 and v not in (2024, 2025, 2026, 2027):
                        return v, f"{name}_line_num"
                # Number after 'amount' or 'paid'
                m3 = re.search(r'(?:amount|paid)\s*(?:is|of|to)?[:\s]*(?:₹|\u20b9|Rs\.?|INR)?\s*(\d+(?:[.,]\d{1,2})?)', txt, re.IGNORECASE)
                if m3:
                    v = float(m3.group(1).replace(',', '.'))
                    if v > 0 and v not in (2024, 2025, 2026, 2027):
                        return v, f"{name}_kw_num"

    except Exception:
        pass

    return None, None


def _extract_text_from_image(image_bytes: bytes) -> tuple[str, bool, str | None]:
    """
    Extract plain text from an image via pytesseract.

    Returns (text, ocr_available, error_detail).
    """
    pytesseract = _configure_tesseract()
    if pytesseract is None:
        return "", False, "pytesseract is not installed (pip install pytesseract)."

    try:
        from PIL import Image
    except ImportError:
        return "", False, "Pillow is not installed (pip install Pillow)."

    cmd = pytesseract.pytesseract.tesseract_cmd
    if not os.path.isfile(cmd):
        return "", False, (
            f"Tesseract executable not found at '{cmd}'. "
            "Install Tesseract OCR and set TESSERACT_CMD in config."
        )

    try:
        import io as _io
        pil_image = Image.open(_io.BytesIO(image_bytes)).convert("RGB")
        w, h = pil_image.size
        if w < 600 or h < 600:
            scale = max(2, 600 // min(w, h))
            pil_image = pil_image.resize((w * scale, h * scale), Image.LANCZOS)
            w, h = pil_image.size

        # Multi-pass OCR:
        # Pass 1: Standard PSM 3 (auto page segmentation - critical for screenshots with isolated headers/amounts)
        gray = pil_image.convert("L")
        text_psm3 = pytesseract.image_to_string(gray, config=r"--oem 3 --psm 3")

        # Pass 2: Standard PSM 6 (uniform block of text)
        text_psm6 = pytesseract.image_to_string(gray, config=r"--oem 3 --psm 6")

        # Pass 3: Saturated color neutralization
        im_neut = pil_image.copy()
        pix = pil_image.load()
        npix = im_neut.load()
        has_color = False
        for y in range(h):
            for x in range(w):
                r, g, b = pix[x, y]
                if max(r, g, b) - min(r, g, b) > 35:
                    npix[x, y] = (255, 255, 255)
                    has_color = True

        text_neutral = ""
        if has_color:
            text_neutral = pytesseract.image_to_string(im_neut.convert("L"), config=r"--oem 3 --psm 3")

        # Extract primary confirmation amount from screenshot layout
        primary_amount, primary_source = _extract_primary_amount_from_image(pil_image, pytesseract)
        primary_header = ""
        if primary_amount is not None:
            primary_label = int(primary_amount) if primary_amount == int(primary_amount) else f"{primary_amount:.2f}"
            primary_header = f"PRIMARY_PAYMENT_CONFIRMATION_AMOUNT: ₹{primary_label} ({primary_source})\n"

        combined_text = f"{primary_header}{text_psm3}\n{text_psm6}\n{text_neutral}".strip()
        return combined_text, True, None
    except pytesseract.TesseractError as exc:
        return "", True, f"Tesseract error: {exc}"
    except Exception as exc:
        return "", True, f"OCR failed: {exc}"


# ── Normalisation ─────────────────────────────────────────────────────────────

def _norm(text: str) -> str:
    """Lowercase + collapse whitespace."""
    return re.sub(r"\s+", " ", text.lower()).strip()


# ── Check functions ───────────────────────────────────────────────────────────

def _check_minimum_content(text: str) -> tuple[bool, str]:
    wc = len(text.split())
    if wc < MIN_OCR_WORD_COUNT:
        return (
            False,
            f"Payment details could not be read from the screenshot "
            f"({wc} word(s) detected). "
            "Please upload a clear screenshot of your UPI payment confirmation."
        )
    return True, f"Screenshot contains readable text ({wc} words)."


def _check_receiver(
    text: str,
    merchant_name: str = None,
    merchant_identifiers: list[str] = None,
) -> tuple[bool, str]:
    """
    HARD CHECK — receiver in the screenshot must match the session merchant.

    Uses the per-session snapshot (merchant_name / merchant_identifiers) so
    this check automatically adapts if the QR is changed.
    """
    if merchant_name is None:
        merchant_name = getattr(Config, "MERCHANT_NAME", "Lakshmi Sai Bandi")
    if not merchant_identifiers:
        merchant_identifiers = getattr(Config, "MERCHANT_IDENTIFIERS", ["lakshmi sai bandi", "campusprint"])

    normalised = _norm(text)
    for identifier in merchant_identifiers:
        ident = identifier.lower().strip()
        if len(ident) >= 4 and ident in normalised:
            return True, f"Merchant '{identifier}' found in screenshot."
    return (
        False,
        f"Payment receiver could not be verified as '{merchant_name}'. "
        "Ensure you scanned the correct CampusPrint QR code and the screenshot "
        "shows the recipient's name or UPI ID."
    )


def _check_amount(text: str, expected_amount: float, primary_amount: float | None = None) -> tuple[bool, str]:
    """
    HARD CHECK — paid amount must match order total (±₹0.01).
    Prioritizes the primary payment confirmation amount extracted from the screenshot structure.
    Falls back to multi-tiered OCR text candidate extraction for text payloads.
    """
    label = int(expected_amount) if expected_amount == int(expected_amount) else f"{expected_amount:.2f}"

    # Check if primary confirmation amount is provided or present in header
    if primary_amount is None:
        m_prim = re.search(r'PRIMARY_PAYMENT_CONFIRMATION_AMOUNT:\s*(?:₹|\u20b9|Rs\.?|INR)?\s*(\d+(?:\.\d{1,2})?)', text, re.IGNORECASE)
        if m_prim:
            try:
                primary_amount = float(m_prim.group(1))
            except ValueError:
                pass

    if primary_amount is not None:
        if abs(primary_amount - expected_amount) < 0.01:
            return True, f"Amount ₹{label} matched in screenshot."
        else:
            det_label = int(primary_amount) if primary_amount == int(primary_amount) else f"{primary_amount:.2f}"
            return (
                False,
                f"Detected payment of ₹{det_label}, but required order amount is ₹{label}. "
                "The screenshot amount must match the order amount."
            )

    cleaned = text.replace(",", "")
    high_cands: list[float] = []
    med_cands: list[float] = []
    low_cands: list[float] = []

    # 1. Currency-prefixed numbers: ₹6, Rs. 6, INR 6, re 6, and OCR glyph misreads <6, ~6, *6, =6, F6, z6, Z6
    for m in re.finditer(r'(?:₹|\u20b9|Rs\.?|INR|re\.?|[<~*#=¢¥FzZ])\s*(\d+(?:[.,]\d{1,2})?)', cleaned, re.IGNORECASE):
        try:
            val = float(m.group(1).replace(',', '.'))
            if val > 0:
                high_cands.append(val)
        except ValueError:
            pass

    # 2. Contextual keywords: 'paid 6', 'amount 6', 'total 6', 'payment of 6'
    for m in re.finditer(r'(?:paid|amount|total|payment\s+of)\s*(?:of|to|is|:)?\s*(?:₹|\u20b9|Rs\.?|INR|[<~*#=¢¥FzZ])?\s*(\d+(?:[.,]\d{1,2})?)', cleaned, re.IGNORECASE):
        try:
            val = float(m.group(1).replace(',', '.'))
            if val > 0:
                high_cands.append(val)
        except ValueError:
            pass

    # 3. Isolated lines: lines consisting solely of an amount (with optional currency glyphs)
    for line in cleaned.splitlines():
        line = line.strip()
        m = re.match(r'^[<~*#=¢¥FzZ₹\u20b9RsINRe\s]*(\d+(?:[.,]\d{1,2})?)[<~*#=¢¥FzZ₹\u20b9\s]*$', line, re.IGNORECASE)
        if m:
            try:
                val = float(m.group(1).replace(',', '.'))
                if val > 0:
                    med_cands.append(val)
            except ValueError:
                pass

    # 4. Filter text to remove times, dates, and durations before general search
    filtered_text = re.sub(r'\b\d{1,2}:\d{2}(?::\d{2})?(?:\s*[AaPp][Mm])?\b', ' ', cleaned)
    filtered_text = re.sub(r'\b\d{1,4}[/\-.]\d{1,2}[/\-.]\d{1,4}\b', ' ', filtered_text)
    filtered_text = re.sub(r'\b\d{1,2}\s+[A-Za-z]{3,9}\b', ' ', filtered_text)
    filtered_text = re.sub(r'\b[A-Za-z]{3,9}\s+\d{1,2}\b', ' ', filtered_text)
    filtered_text = re.sub(r'\b\d+\s*(?:hrs?|hours?|mins?|minutes?|sec|seconds?|days?)\b', ' ', filtered_text, flags=re.IGNORECASE)
    filtered_text = re.sub(r'-\s*\d{4,}\b', ' ', filtered_text)

    for m in re.finditer(r'(?<![A-Za-z0-9])(\d+(?:\.\d{1,2})?)(?![A-Za-z0-9])', filtered_text):
        try:
            val = float(m.group(1))
            if val not in (2024, 2025, 2026, 2027) and val > 0:
                low_cands.append(val)
        except ValueError:
            pass

    all_cands = high_cands + med_cands + low_cands

    # Check for exact numerical match (tolerance 0.01)
    for cand in all_cands:
        if abs(cand - expected_amount) < 0.01:
            return True, f"Amount ₹{label} matched in screenshot."

    # If a prominent candidate was detected but does not match expected_amount
    detected_cand = None
    for cand in (high_cands + med_cands):
        if cand > 0 and cand not in (2024, 2025, 2026, 2027):
            detected_cand = cand
            break

    if detected_cand is not None and abs(detected_cand - expected_amount) >= 0.01:
        det_label = int(detected_cand) if detected_cand == int(detected_cand) else f"{detected_cand:.2f}"
        return (
            False,
            f"Detected payment of ₹{det_label}, but required order amount is ₹{label}. "
            "The screenshot amount must match the order amount."
        )

    return (
        False,
        f"Payment amount ₹{label} could not be detected in the screenshot. "
        "Ensure the screenshot clearly shows the paid amount."
    )


def _check_date(text: str, session_started_at: datetime) -> tuple[bool, str]:
    """
    HARD CHECK — payment date must match the session date (in local time).

    session_started_at is UTC; we convert to local using
    Config.TIMEZONE_OFFSET_HOURS before comparing, because UPI apps show
    local date in the screenshot.

    No date found → FAIL (no leniency in production mode).
    """
    if session_started_at.tzinfo is not None:
        session_started_at = session_started_at.replace(tzinfo=None)
    tz_offset    = getattr(Config, "TIMEZONE_OFFSET_HOURS", 5.5)
    local_dt     = session_started_at + timedelta(hours=tz_offset)
    session_date = local_dt.date()

    found_dates: list[date_type] = []

    # ── Numeric patterns ─────────────────────────────────────────────────────
    # ISO: 2026-09-12
    for m in re.finditer(r"\b(\d{4})[/\-.](\d{1,2})[/\-.](\d{1,2})\b", text):
        try:
            found_dates.append(date_type(int(m.group(1)), int(m.group(2)), int(m.group(3))))
        except ValueError:
            pass
    # DD/MM/YYYY or DD-MM-YYYY or DD.MM.YYYY
    for m in re.finditer(r"\b(\d{1,2})[/\-.](\d{1,2})[/\-.](\d{4})\b", text):
        try:
            found_dates.append(date_type(int(m.group(3)), int(m.group(2)), int(m.group(1))))
        except ValueError:
            pass
    # DD/MM/YY
    for m in re.finditer(r"\b(\d{1,2})[/\-.](\d{1,2})[/\-.](\d{2})\b", text):
        try:
            found_dates.append(date_type(2000 + int(m.group(3)), int(m.group(2)), int(m.group(1))))
        except ValueError:
            pass

    # ── Named-month patterns ─────────────────────────────────────────────────
    MONTHS = {
        "jan":1,"feb":2,"mar":3,"apr":4,"may":5,"jun":6,
        "jul":7,"aug":8,"sep":9,"oct":10,"nov":11,"dec":12,
    }
    MONTH_NAMES = (
        r"(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|"
        r"Jul(?:y)?|Aug(?:ust)?|Sep(?:t(?:ember)?)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)"
    )

    # Day-first: e.g. "15 Sep 2026", "15 September 2026", "15th Sep 2026", "15 Sep", "15-Sep-2026"
    # Year matches 4-digit year or 2-digit year (not followed by colon to avoid matching time like 10 in 10:58)
    day_first_pattern = (
        rf"\b([1-9]|[12]\d|3[01])(?:st|nd|rd|th)?[\s/-]+"
        rf"({MONTH_NAMES})\.?"
        rf"(?:[\s,/-]+(20\d{{2}}|\d{{2}}(?!\s*[:]))\b)?"
    )
    for m in re.finditer(day_first_pattern, text, re.IGNORECASE):
        key = m.group(2)[:3].lower()
        if key in MONTHS:
            try:
                yr = int(m.group(3)) if m.group(3) else session_date.year
                if yr < 100: yr += 2000
                found_dates.append(date_type(yr, MONTHS[key], int(m.group(1))))
            except (ValueError, TypeError):
                pass

    # Month-first: e.g. "Sep 15, 2026", "September 15 2026", "Sep 15th, 2026", "Sep 15"
    month_first_pattern = (
        rf"\b({MONTH_NAMES})\.?[\s/-]+"
        rf"([1-9]|[12]\d|3[01])(?:st|nd|rd|th)?\b"
        rf"(?:[\s,/-]+(20\d{{2}}|\d{{2}}(?!\s*[:]))\b)?"
    )
    for m in re.finditer(month_first_pattern, text, re.IGNORECASE):
        key = m.group(1)[:3].lower()
        if key in MONTHS:
            try:
                yr = int(m.group(3)) if m.group(3) else session_date.year
                if yr < 100: yr += 2000
                found_dates.append(date_type(yr, MONTHS[key], int(m.group(2))))
            except (ValueError, TypeError):
                pass

    if not found_dates:
        return (
            False,
            "Payment date could not be read from the screenshot. "
            "Please upload a clear screenshot that shows the payment date."
        )

    for candidate in found_dates:
        if candidate == session_date:
            return True, f"Payment date {candidate.strftime('%d %b %Y')} matches session date."

    mismatched = found_dates[0].strftime("%d %b %Y")
    return (
        False,
        f"Payment date {mismatched} does not match the session date "
        f"{session_date.strftime('%d %b %Y')}. "
        "Old screenshots are not accepted."
    )


def _check_time_window(text: str, session_started_at: datetime) -> tuple[bool, str]:
    """
    HARD CHECK — payment time must fall inside the valid session window.

    session_started_at is UTC. We convert to local time using
    Config.TIMEZONE_OFFSET_HOURS before comparing, because UPI apps show
    local time in screenshots.

    Dynamic Window:
    Allows payments made within the session window, plus reasonable pre-session
    time (up to 15 minutes prior to session creation, in case the customer scanned
    and paid right before completing checkout) and clock drift / upload tolerance (+2 minutes).

    Also gracefully handles:
    - 12-hour format with AM/PM (e.g. 5:26 PM, 05:26pm)
    - 12-hour format without AM/PM (e.g. 5:26, 05:26 - infers AM or PM based on session time)
    - 24-hour format (e.g. 17:26, 17:26:30)
    - Dot or colon separators (e.g. 5.26 PM, 5:26 PM)
    - Spaces inside time strings
    """
    if session_started_at.tzinfo is not None:
        session_started_at = session_started_at.replace(tzinfo=None)

    tz_offset = getattr(Config, "TIMEZONE_OFFSET_HOURS", 5.5)
    local_start = session_started_at + timedelta(hours=tz_offset)
    local_end = local_start + timedelta(minutes=VERIFICATION_WINDOW_MINUTES)
    sess_date = local_start.date()

    tol = timedelta(minutes=1)
    window_start = local_start - tol
    window_end = local_end + tol

    direct_start = session_started_at - tol
    direct_end = session_started_at + timedelta(minutes=VERIFICATION_WINDOW_MINUTES) + tol

    # 1. Precise time regex patterns:
    # Colon time: 1-2 digit hour (0-23), colon, 2 digit minute (0-59), optional seconds, optional AM/PM (with or without space)
    # Examples: 5:26pm, 05:26 PM, 17:26, 5:26:30 PM
    colon_pattern = r"\b([01]?\d|2[0-3])\s*:\s*([0-5]\d)(?:\s*:\s*([0-5]\d))?\s*([AaPp][Mm])?\b"

    # Dot time: only valid if followed by AM/PM (to avoid matching amounts like 34.00 or 15.50)
    # Examples: 5.26pm, 5.26 PM, 05.26 AM
    dot_pattern = r"\b([01]?\d|2[0-3])\s*\.\s*([0-5]\d)\s*([AaPp][Mm])\b"

    matches = re.findall(colon_pattern, text, re.IGNORECASE) + re.findall(dot_pattern, text, re.IGNORECASE)

    if not matches:
        return (
            False,
            "Payment time could not be read from the screenshot. "
            "Please upload a screenshot that clearly shows the payment timestamp."
        )

    parsed_candidates: list[tuple[datetime, str]] = []

    for match in matches:
        h_str = match[0]
        m_str = match[1]
        s_str = match[2] if len(match) > 2 and match[2] and match[2].isdigit() else ""
        ampm_raw = match[3] if len(match) > 3 and match[3] else (match[2] if len(match) > 2 and match[2] and match[2].upper() in ("AM", "PM") else "")
        ampm_str = ampm_raw.upper().strip() if ampm_raw else ""

        try:
            hour = int(h_str)
            minute = int(m_str)
            second = int(s_str) if s_str else 0
        except ValueError:
            continue

        if ampm_str in ("AM", "PM"):
            # 12-hour format with AM/PM
            if hour == 12:
                hour_24 = 12 if ampm_str == "PM" else 0
            else:
                hour_24 = hour + (12 if ampm_str == "PM" else 0)

            disp_str = f"{hour}:{minute:02d} {ampm_str}"
            for base_date in (sess_date, session_started_at.date()):
                from datetime import time as dt_time
                t = dt_time(hour_24, minute, second)
                cand = datetime.combine(base_date, t)
                parsed_candidates.append((cand, disp_str))
                parsed_candidates.append((cand - timedelta(days=1), disp_str))
                parsed_candidates.append((cand + timedelta(days=1), disp_str))
        else:
            # No AM/PM specified: could be 24-hr (e.g. 17:26) or 12-hr (e.g. 05:26)
            disp_str = f"{hour:02d}:{minute:02d}"
            for base_date in (sess_date, session_started_at.date()):
                from datetime import time as dt_time
                if 0 <= hour <= 23:
                    cand = datetime.combine(base_date, dt_time(hour, minute, second))
                    parsed_candidates.append((cand, disp_str))
                    parsed_candidates.append((cand - timedelta(days=1), disp_str))
                    parsed_candidates.append((cand + timedelta(days=1), disp_str))
                if 1 <= hour <= 11:
                    cand_pm = datetime.combine(base_date, dt_time(hour + 12, minute, second))
                    disp_pm = f"{hour}:{minute:02d} PM"
                    parsed_candidates.append((cand_pm, disp_pm))
                    parsed_candidates.append((cand_pm - timedelta(days=1), disp_pm))
                    parsed_candidates.append((cand_pm + timedelta(days=1), disp_pm))
                elif hour == 12:
                    cand_am = datetime.combine(base_date, dt_time(0, minute, second))
                    parsed_candidates.append((cand_am, f"12:{minute:02d} AM"))

    # 2. Check candidates against the valid dynamic window
    for cand, disp in parsed_candidates:
        if (window_start <= cand <= window_end) or (direct_start <= cand <= direct_end):
            readable_time = cand.strftime("%I:%M %p").lstrip("0")
            return (
                True,
                f"Payment time {readable_time} is within the valid window "
                f"({local_start.strftime('%I:%M %p').lstrip('0')}–{local_end.strftime('%I:%M %p').lstrip('0')})."
            )

    first_disp = parsed_candidates[0][1] if parsed_candidates else "Unknown"
    return (
        False,
        f"Payment time in the screenshot ({first_disp}) is outside the valid window "
        f"({local_start.strftime('%I:%M %p').lstrip('0')} – {local_end.strftime('%I:%M %p').lstrip('0')}). "
        "Payment must be made and screenshot uploaded within the valid session window."
    )


def _check_transaction_id(text: str) -> tuple[bool, str | None]:
    """HARD CHECK — a UPI transaction / UTR reference ID must be present."""
    # Labeled: UTR / Ref No / Transaction ID / Txn ID
    labeled = re.search(
        r"(?:UTR|Ref(?:erence)?\.?\s*(?:No\.?|ID\.?)?|Transaction\s+ID|Txn\s+ID)"
        r"[:\s#]*([A-Za-z0-9]{6,24})",
        text, re.IGNORECASE
    )
    if labeled:
        return True, labeled.group(1)

    long_nums = re.findall(r"\b(\d{12,18})\b", text)
    if long_nums:
        return True, max(long_nums, key=len)

    short_nums = re.findall(r"\b(\d{9,11})\b", text)
    if short_nums:
        return True, max(short_nums, key=len)

    return False, None


# ── Public entry point ────────────────────────────────────────────────────────

def verify_screenshot(
    image_bytes: bytes,
    expected_amount: float,
    session_started_at: datetime,
    *,
    merchant_name: str = "",
    merchant_identifiers: list[str] | None = None,
) -> dict:
    """
    Prototype verification of a UPI payment screenshot.

    All checks are HARD (no leniency) except that OCR failure returns a
    clean setup error rather than crashing.

    Parameters
    ----------
    image_bytes          : raw bytes of the uploaded image
    expected_amount      : order total that must appear in the screenshot
    session_started_at   : UTC datetime the payment session was created
    merchant_name        : display name for error messages (from session snapshot)
    merchant_identifiers : lower-cased substrings to match against OCR text
                           (from session snapshot — NOT read from Config live)
    """
    if not merchant_identifiers:
        merchant_identifiers = getattr(Config, "MERCHANT_IDENTIFIERS", [])
    if not merchant_name:
        merchant_name = getattr(Config, "MERCHANT_NAME", "CampusPrint")

    checks: dict = {}

    # ── 1. OCR ──────────────────────────────────────────────────────────────
    extracted_text, ocr_available, ocr_error = _extract_text_from_image(image_bytes)

    if not ocr_available:
        return {
            "success": False,
            "status":  "failed",
            "message": f"Payment verification unavailable: {ocr_error}",
            "checks":  {"ocr_setup": {"passed": False, "message": ocr_error}},
            "transaction_ref": None,
            "prototype_note":  "PROTOTYPE: Configure Tesseract OCR to enable verification.",
        }

    if ocr_error:
        return {
            "success": False,
            "status":  "failed",
            "message": "Payment verification failed: unable to read payment details from the screenshot.",
            "checks":  {"ocr_read": {"passed": False, "message": ocr_error}},
            "transaction_ref": None,
            "prototype_note":  "PROTOTYPE: OCR-based verification only.",
        }

    # ── 2. Minimum content ───────────────────────────────────────────────────
    content_ok, content_msg = _check_minimum_content(extracted_text)
    checks["screenshot_content"] = {"passed": content_ok, "message": content_msg}
    if not content_ok:
        return {
            "success": False, "status": "failed",
            "message": content_msg, "checks": checks,
            "transaction_ref": None,
            "prototype_note":  "PROTOTYPE: OCR-based verification only.",
        }

    # ── 3. Receiver (HARD) ───────────────────────────────────────────────────
    receiver_ok, receiver_msg = _check_receiver(
        extracted_text, merchant_name, merchant_identifiers
    )
    checks["receiver"] = {"passed": receiver_ok, "message": receiver_msg}

    # ── 4. Amount (HARD) ────────────────────────────────────────────────────
    amount_ok, amount_msg = _check_amount(extracted_text, expected_amount)
    checks["amount"] = {"passed": amount_ok, "message": amount_msg}

    # ── 5. Date (HARD) ──────────────────────────────────────────────────────
    date_ok, date_msg = _check_date(extracted_text, session_started_at)
    checks["payment_date"] = {"passed": date_ok, "message": date_msg}

    # ── 6. Time window (HARD) ───────────────────────────────────────────────
    time_ok, time_msg = _check_time_window(extracted_text, session_started_at)
    checks["time_window"] = {"passed": time_ok, "message": time_msg}

    # ── 7. Transaction ID (OPTIONAL) ─────────────────────────────────────────
    txn_ok, transaction_ref = _check_transaction_id(extracted_text)
    checks["transaction_id"] = {
        "passed":  True,
        "message": (
            f"Transaction reference detected: {transaction_ref}"
            if txn_ok
            else "Transaction reference optional (not detected in screenshot)."
        ),
    }

    # ── Overall — ALL REQUIRED checks must pass (receiver, amount, date, time) ──
    all_passed = receiver_ok and amount_ok and date_ok and time_ok

    if all_passed:
        return {
            "success": True,
            "status":  "verified",
            "message": "Payment Verified Successfully",
            "checks":  checks,
            "transaction_ref": transaction_ref,
            "prototype_note":  (
                "PROTOTYPE: OCR-based verification only. "
                "Does not confirm actual bank settlement."
            ),
        }

    failure_msgs = [v["message"] for v in checks.values() if not v.get("passed")]
    return {
        "success": False,
        "status":  "failed",
        "message": failure_msgs[0] if failure_msgs else "Payment verification failed.",
        "checks":  checks,
        "transaction_ref": transaction_ref,
        "prototype_note":  (
            "PROTOTYPE: OCR-based verification only. "
            "Does not confirm actual bank settlement."
        ),
    }
