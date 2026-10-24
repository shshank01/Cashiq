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
pip install fastapi uvicorn sqlalchemy aiosqlite pydantic pydantic-settings python-multipart bcrypt pyjwt greenlet scikit-learn scipy numpy pandas statsmodels pillow pdfplumber requests
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

3. **Receipt & Bank Statement Ingestion**:
   * Direct CSV and PDF statement parsing, and image receipt OCR.
   * Draft extraction workflow: Upload → Extract → Draft Table → Confidence Check → User Review → Confirm into ledger.

4. **Anomaly Detection**:
   * Business-specific statistical outlier engine: IQR, Z-score, and Multivariate Isolation Forest.
   * Distinguishes high category multipliers and unusual spend spikes with detailed rationales.

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
