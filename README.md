# Digital Xerox & Stationery Ordering System (CampusPrint) 🖨️✨

A full-stack web application designed for college campuses to eliminate long queues at the college Xerox and stationery counter. Students can upload their assignments, lab manuals, and project reports from anywhere, configure print options with live price calculation, simulate payment, and receive a collection token number. College staff manage orders, review documents, and update status in real time.

---

## 🌟 Key Features

### For Students
- **Modern Landing Page**: Clean responsive hero section showcasing live counter status and transparent Xerox rates.
- **Document Upload**: Supports PDF, Word documents (`.doc`, `.docx`), PowerPoint slides (`.ppt`, `.pptx`), text, and images (`.jpg`, `.png`).
- **Flexible Print Preferences**:
  - **Color Mode**: Black & White (₹2/page) or Full Color (₹5/page).
  - **Print Sides**: Single-Sided or Double-Sided (Back-to-back duplex with paper-sheet calculation).
  - **Copies & Pages**: Interactive stepper inputs with automatic sheet calculation.
  - **Binding & Finishing**: None, Corner Staple (+₹2), Spiral Binding (+₹30), Soft Book (+₹50), or Hard Bound Golden Embossed (+₹160).
  - **Special Instructions**: Direct notes to staff (e.g. *"First page in color glossy"*).
- **Live Price Calculator**: Real-time quote breakdown as you change settings.
- **Simulated Payment**: Interactive checkout supporting Simulated UPI (GPay/PhonePe/Paytm QR), Campus Student ID Card, or Cash at Counter.
- **Instant Token Generation**: Generates a unique Token Number (`TK-101`) and Order ID (`ORD-YYYYMMDD-XXXX`).
- **Live Order Tracker**: Real-time 4-step progress timeline:
  - `Received` ➔ `Processing` ➔ `Ready for Collection` ➔ `Completed`
  - Handles `Rejected` status with staff's rejection explanation.
- **Digital Receipt**: Instant order summary with print/save receipt option.

### For College Xerox Staff
- **Protected Staff Portal**: Login system (`staff` / `xerox@admin`).
- **Live Metrics Dashboard**: Real-time counter for Total Orders, Pending, In-Printing, Ready for Pickup, Completed, and Gross Revenue ₹.
- **Order Queue & Search**: Filter by status or instantly search by student name, roll number, or token.
- **Document Access**: View or download original student documents directly from the dashboard.
- **One-Click Status Updates**:
  - `Start Printing` (moves to *Processing*)
  - `Mark Ready` (moves to *Ready for Collection*)
  - `Handed Over` (moves to *Completed*)
  - `Reject Order` (prompts staff for a rejection reason shown to the student).
- **Auto-Refresh**: Live polling every 8 seconds keeps the queue synchronized.

---

## 🛠️ Tech Stack

| Layer | Technology |
|---|---|
| **Frontend** | React 18, Vite, Lucide Icons, Custom Design System |
| **Backend** | Python Flask, Flask-CORS, Werkzeug |
| **Database** | SQLite (designed with DAO abstraction for easy migration to AWS DynamoDB) |
| **Architecture** | RESTful JSON API with multipart file handling |

---

## 📁 Project Structure

```text
xerox/
├── backend/
│   ├── app.py                 # Flask server entry point & CORS configuration
│   ├── config.py              # Centralized pricing & upload rules
│   ├── database.py            # SQLite schema, DAO helper functions, price logic
│   ├── routes/
│   │   ├── order_routes.py    # /api/orders, /api/pricing, /api/orders/track
│   │   └── staff_routes.py    # /api/staff/login, /api/staff/orders, stats, file download
│   ├── uploads/               # Secure document storage
│   ├── requirements.txt       # Python dependencies
│   └── test_api.py            # Automated test suite
│
├── frontend/
│   ├── src/
│   │   ├── components/
│   │   │   ├── Navbar.jsx      # Top navigation with tabs & branding
│   │   │   ├── LandingHero.jsx # Hero section with shop rates & features
│   │   │   ├── OrderForm.jsx   # Document upload, options, price quote, checkout
│   │   │   ├── TrackOrder.jsx  # Live order tracker & timeline
│   │   │   ├── StaffPortal.jsx # Staff login, metrics, & order queue management
│   │   │   └── Footer.jsx       # Shop timings, location, and info
│   │   ├── App.jsx             # Root application orchestrator
│   │   └── index.css           # Modern design system & status badges
│   ├── package.json
│   └── vite.config.js          # Vite config with backend proxy on /api
│
├── run_backend.bat            # Quick launch script for backend
├── run_frontend.bat           # Quick launch script for frontend
└── README.md                  # Project documentation
```

---

## 🚀 How to Run Locally

### Prerequisites
- **Python 3.10+** (tested on Python 3.14)
- **Node.js 18+** & **npm**

---

### Step 1: Start the Flask Backend

Open your terminal in the project directory (`xerox`):

```powershell
# Navigate to backend
cd backend

# Install dependencies (already installed if done once)
pip install -r requirements.txt

# Run the Flask server
python app.py
```

The backend starts at: **`http://127.0.0.1:5000`**

You can test its health anytime at `http://127.0.0.1:5000/api/health`.

---

### Step 2: Start the React Frontend

Open a **second terminal** in the project directory (`xerox`):

```powershell
# Navigate to frontend
cd frontend

# Install dependencies (already installed if done once)
npm install

# Start Vite development server
npm run dev
```

The frontend starts at: **`http://localhost:5173`**

Open your browser and navigate to:
👉 **[http://localhost:5173](http://localhost:5173)**

---

## 🌐 Sharing with Teammates (Public HTTPS Tunnel)

To allow teammates on other Wi-Fi networks or mobile data to review the live application without deploying to the cloud:

1. Ensure both the Flask backend and React frontend are running.
2. In the project folder, run:
   ```powershell
   .\share_tunnel.bat
   # or
   .\cloudflared.exe tunnel --url http://localhost:5173 --http-host-header="localhost:5173"
   ```
3. Cloudflare will output an HTTPS URL:
   ```text
   Your quick Tunnel has been created! Visit it at:
   https://<random-subdomain>.trycloudflare.com
   ```
4. Send this link to your teammates. Both the frontend and backend APIs will work through this single secure link with zero additional configuration!

---

## 🔑 Default Staff Credentials

To access the Staff Portal:
- **Username**: `staff`
- **Password**: `xerox@admin`

*(Configurable via environment variables `STAFF_USERNAME` and `STAFF_PASSWORD` in `backend/config.py`)*

---

## ⚙️ Configurable Pricing

All pricing logic is centralized in [`backend/config.py`](file:///c:/Users/USE/Desktop/xerox/backend/config.py):

```python
PRICING = {
    "bw_per_page": 2.00,       # ₹2 per page for B&W
    "color_per_page": 5.00,    # ₹5 per page for Color
    "types": [
        {"id": "regular", "name": "Standard Document / Notes", "extra_cost": 0.0},
        {"id": "assignment", "name": "College Assignment / Lab Record", "extra_cost": 0.0},
        {"id": "project_report", "name": "Final Project Report", "extra_cost": 15.0},
        {"id": "certificate", "name": "Glossy / Certificate Print", "extra_cost": 20.0}
    ],
    "bindings": [
        {"id": "none", "name": "No Binding", "price": 0.0},
        {"id": "corner_staple", "name": "Corner Staple", "price": 2.0},
        {"id": "spiral", "name": "Spiral Binding", "price": 30.0},
        {"id": "soft_binding", "name": "Soft Book Binding", "price": 50.0},
        {"id": "hard_binding", "name": "Hard Bound Golden Embossed", "price": 160.0}
    ]
}
```

---

## 🧪 Automated Testing

Run the included backend test suite to verify pricing calculations, order placement, file uploads, staff authentication, and status transitions:

```powershell
cd backend
python test_api.py
```

---

## ☁️ Future Deployment Roadmap

1. **Amazon DynamoDB**: Replace `backend/database.py` SQLite queries with `boto3` DynamoDB Table operations (`orders` table with partition key `order_id` and GSI on `token_number`).
2. **AWS S3**: Store uploaded document files in an S3 bucket with pre-signed URLs.
3. **Docker**: Add `Dockerfile` for backend and frontend with a simple `docker-compose.yml`.
