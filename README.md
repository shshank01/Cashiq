# CashIQ — AI-Powered Financial Intelligence Platform

CashIQ turns raw transactions into structured accounting intelligence, automated category classification, anomaly alerts, time-series cash-flow forecasts, recurring payment tracking, and controlled-tool AI assistance for startups and growing businesses.

---

## ⚡ Quick Start (Windows One-Click)

Simply double-click:
```bat
run_cashiq.bat
```
This automatically launches:
* **Backend API**: `http://localhost:8000` (API Docs at `http://localhost:8000/docs`)
* **Frontend Web App**: `http://localhost:3000`

---

## 🛠️ Step-by-Step Manual Setup

### 1. Prerequisites
Ensure you have installed:
* **Python** 3.10+ (Python 3.14 recommended)
* **Node.js** 18+ and `npm`

---

### 2. Backend Setup & Run

Open a terminal in the project directory:

```bash
cd backend
```

Install backend dependencies:
```bash
pip install -r requirements.txt
```

*(Optional)* Seed or re-seed the SQLite database with 150 days of realistic transactions, accounts, anomalies, recurring payments, and forecast trajectories:
```bash
python seed.py
```

Start the backend server:
```bash
python run.py
```
> The API will run at **`http://localhost:8000`**. You can explore the interactive OpenAPI documentation at **`http://localhost:8000/docs`**.

---

### 3. Frontend Setup & Run

Open a **second terminal** in the project directory:

```bash
cd frontend
```

Install frontend packages (already installed if `node_modules` exists):
```bash
npm install
```

Start the Vite development server:
```bash
npm run dev
```
> The application will open at **`http://localhost:3000`**.

---

## 🔑 Demo Login Credentials

Pre-seeded business workspace (**Apex Cloud Technologies**):

* **Email**: `demo@cashiq.io`
* **Password**: `password123`

*(You can also register a new account on the login page; a new dedicated business workspace is automatically created and isolated for you.)*

---

## 🏛️ Architecture & Implemented Features

1. **Dashboard & KPIs**:
   * Current Cash, 30-Day Income, Operating Expenses, Net Cash Flow, Burn-based Runway, Active Payables, and Receivables.
   * Cash-flow history chart, Income vs Expenses comparison, Category spend breakdown, and 14-day cash trajectory.
   * Algorithmic insights, upcoming recurring debits, and anomaly alerts.

2. **Transactions Ledger**:
   * Stored in integer minor units (cents/paise) to eliminate floating-point rounding errors.
   * Full CRUD: Create, Edit, Delete, Filter by Type / Category, Search, and Pagination.
   * **Supervised TF-IDF + Logistic Regression ML Categorization** trained on transaction text with confidence scores.
   * User confirmation/correction feedback loop to continuously refine model labels.

3. **Format-Aware Document & OCR Ingestion (v3.0)**:
   * **Images & Scanned Receipts**: Lazy-loaded CPU OCR engine supporting optional PaddleOCR (PP-OCR + selective PP-StructureV3), RapidOCR (PP-OCRv6 ONNX Runtime), native Windows OCR (`winocr`), and Tesseract fallbacks. Conditional image quality checks (EXIF, perspective correction, deskewing, CLAHE, adaptive thresholding) compared against the original image, with bounding-box preservation and targeted low-confidence crop retries.
   * **PDFs (Digital, Scanned & Mixed)**: PyMuPDF native text & structured table extraction for digital pages; OCR applied only to scanned/image pages with bounded parallelism preserving page order and column separation.
   * **CSV Files (Zero OCR)**: Robust encoding, delimiter, preamble header, and footer summary detection with Indian bank statement support (HDFC/SBI/ICICI/Axis, `DD/MM/YYYY`, `1,23,456.78`, UPI/UTR, separate debit/credit, running balance cross-validation).
   * **Financial Reconciliation & Provenance**: Extracts total, subtotal, GST/CGST/SGST/IGST, discount, GSTIN, invoice/ref #, payment method, and line items with deterministic arithmetic validation (`subtotal + tax - discount == total`), field-level confidence & source provenance, SHA-256 hash caching, and raw text retention.

4. **Business-Context-Aware Anomaly Detection (v3.0)**:
   * **Operational Expense Relevance**: Evaluates category relevance (`expected`, `unusual`, `unrelated`, `unknown`) against the workspace's Business Profile (industry, business type, operating model) and gradually personalizes from verified transactions — separating operational irrelevance from spending amount anomalies.
   * **Merchant Normalization & Consistency**: Normalizes case, punctuation, payment-gateway prefixes (`UPI/`, `RZP*`, `PAYTM*`, `STRIPE*`), UPI handles, and aliases; detects merchant-category mismatches while honoring verified exceptions and treating new merchants neutrally.
   * **Robust Statistics & Contextual Isolation Forest**: Uses per-category and per-merchant median, IQR, and MAD (no raw historical-max suppression), currency-aware cold-start benchmarks, and contextualized Isolation Forest features where each historical transaction uses its own baselines.
   * **Adaptive Feedback Loop**: Supports `legitimate`, `incorrect_category` (re-classifies & re-evaluates), and `genuine_anomaly` feedback with structured explanations displayed in the UI.

5. **Cash-Flow Forecasting & Cold-Start**:
   * Time-ordered statistical modeling (Moving Average, Seasonal Naive, Exponential Smoothing) with MAE/RMSE validation.
   * Hybrid cold-start architecture: archetypes + known payables/receivables for early businesses.
   * Classifications: *Estimated*, *Projected*, and *Forecast*.

6. **Payables & Receivables**:
   * Deterministic tracking of overdue, pending, and scheduled cash obligations.

7. **Recurring Payments**:
   * Statistical interval and coefficient-of-variation detection for recurring subscriptions and vendor bills.

8. **AI Financial Assistant**:
   * Controlled tool execution (`getDashboardSummary`, `getCategorySpend`, `comparePeriods`, `getPayables`, `getReceivables`, `getForecast`, `getInsights`).
   * Multi-tenant workspace data isolation; strict grounding without hallucinations.

---

## 🧪 Running Tests & Document Benchmarks

```bash
# Run anomaly detection, document ingestion, and API regression tests
cd backend
pytest tests/ -v

# Run legacy v2 vs upgraded v3 document-ingestion accuracy benchmark
python tests/benchmark_document_ingestion.py

# Run legacy ML accuracy & architecture verification suites
cd ..
python test_accuracy.py
python test_ml_architecture.py
```
