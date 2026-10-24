export interface User {
  id: string;
  email: string;
  full_name: string;
}

export interface AuthResponse {
  access_token: string;
  user: User;
}

export interface Workspace {
  id: string;
  name: string;
  currency: string;
  role: string;
  created_at: string;
}

export interface BusinessProfile {
  id: string;
  workspace_id: string;
  business_type: string;
  industry: string;
  company_size: string;
  annual_revenue_range: string;
}

export interface Transaction {
  id: string;
  date: string;
  amount_minor: number;
  currency: string;
  description: string;
  merchant: string | null;
  category_name: string;
  type: 'income' | 'expense';
  account_id: string;
  notes: string | null;
  source: string;
  confidence: number | null;
  model_version: string | null;
  is_anomaly: boolean;
  anomaly_score: number | null;
  anomaly_reason: string | null;
  created_at: string;
}

export interface TransactionsResponse {
  transactions: Transaction[];
  total: number;
  page: number;
  per_page: number;
  total_pages: number;
}

export interface DashboardData {
  kpis: {
    current_cash_minor: number;
    income_minor: number;
    expenses_minor: number;
    net_cash_flow_minor: number;
    runway_months: number | null;
    total_payables_minor: number;
    total_receivables_minor: number;
  };
  cash_flow_history: Array<{
    date: string;
    income_minor: number;
    expenses_minor: number;
    net_minor: number;
  }>;
  income_vs_expenses: Array<{
    month: string;
    income_minor: number;
    expenses_minor: number;
  }>;
  spending_by_category: Array<{
    category: string;
    amount_minor: number;
    percentage: number;
  }>;
  forecast_preview: Array<{
    date: string;
    predicted_minor: number;
    lower_minor: number;
    upper_minor: number;
  }>;
  recent_insights: Array<{
    id: string;
    type: string;
    title: string;
    description: string;
    severity: 'info' | 'warning' | 'critical';
    created_at: string;
  }>;
  upcoming_recurring: Array<{
    merchant: string;
    amount_minor: number;
    frequency: string;
    next_date: string;
  }>;
  anomalous_transactions: Array<{
    id: string;
    date: string;
    merchant: string | null;
    amount_minor: number;
    anomaly_reason: string | null;
  }>;
  upcoming_payables: Array<{
    id: string;
    vendor: string;
    amount_minor: number;
    due_date: string;
  }>;
  upcoming_receivables: Array<{
    id: string;
    client: string;
    amount_minor: number;
    due_date: string;
  }>;
}

export interface Payable {
  id: string;
  vendor: string;
  description: string | null;
  amount_minor: number;
  currency: string;
  due_date: string;
  status: 'pending' | 'paid' | 'overdue';
}

export interface Receivable {
  id: string;
  client: string;
  description: string | null;
  amount_minor: number;
  currency: string;
  due_date: string;
  status: 'pending' | 'received' | 'overdue';
}

export interface RecurringPayment {
  id: string;
  merchant: string;
  description?: string;
  category_name?: string;
  amount_minor: number;
  currency: string;
  frequency: 'daily' | 'weekly' | 'bi-weekly' | 'monthly' | 'quarterly' | 'yearly' | string;
  next_date: string;
  confidence: number;
  type: 'income' | 'expense' | string;
  status: 'active' | 'paused' | 'cancelled' | string;
}

export interface ForecastData {
  forecast_type: 'estimated' | 'projected' | 'forecast';
  daily_forecast: Array<{
    date: string;
    income_minor: number;
    expenses_minor: number;
    net_minor: number;
    cash_position_minor: number;
    lower_minor: number;
    upper_minor: number;
  }>;
  summary: {
    forecast_days: number;
    avg_daily_income_minor: number;
    avg_daily_expenses_minor: number;
    end_cash_position_minor: number;
  };
  metrics: {
    mae: number | null;
    rmse: number | null;
  };
  model_info: {
    method: string;
    data_points_used: number;
  };
}

export interface Insight {
  id: string;
  type: string;
  title: string;
  description: string;
  severity: 'info' | 'warning' | 'critical';
  created_at: string;
}

export interface Document {
  id: string;
  filename: string;
  status: 'processing' | 'processed' | 'failed';
  uploaded_at: string;
}

export interface AssistantResponse {
  response: string;
  conversation_id: string;
}
