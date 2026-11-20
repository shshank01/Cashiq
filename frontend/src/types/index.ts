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
  id?: string;
  workspace_id: string;
  company_name?: string;
  business_type: string | null;
  industry: string | null;
  operating_model?: string | null;
  relevant_expense_categories?: {
    industry_key?: string | null;
    industry_label?: string;
    operating_model?: string;
    expected: string[];
    unusual: string[];
    unrelated: string[];
    learned_categories?: Record<string, { verified_count: number; status: string }>;
  };
  company_size?: string;
  annual_revenue_range?: string;
  configured?: boolean;
}

export interface AnomalyContributingFactor {
  factor: string;
  label: string;
  score: number;
  weight: number;
  triggered: boolean;
  confidence: number;
  detail: string;
  metrics?: Record<string, any>;
}

export interface AnomalyExplanationDetails {
  alert_type?: 'operational_relevance' | 'amount_anomaly' | 'merchant_category_mismatch' | 'merchant_behavior' | 'frequency_timing' | 'multivariate' | 'none' | string;
  primary_factor?: string;
  confidence?: number;
  business_context?: {
    profile_configured?: boolean;
    industry?: string | null;
    business_type?: string | null;
    operating_model?: string | null;
    category_relevance_status?: 'expected' | 'unusual' | 'unrelated' | 'unknown' | string;
    evaluated_category?: string;
    personalized?: boolean;
  };
  contributing_factors?: AnomalyContributingFactor[];
  signals?: Record<string, any>;
  category?: string;
  category_mean_minor?: number;
  category_median_minor?: number;
  category_multiple?: number;
  category_mad_z_score?: number;
  merchant_novelty_score?: number;
  isolation_forest_score?: number;
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
  anomaly_severity?: string | null;
  anomaly_reason: string | null;
  anomaly_explanation?: string | null;
  anomaly_explanation_details?: AnomalyExplanationDetails | null;
  anomaly_alert_type?: string | null;
  anomaly_confidence?: number | null;
  anomaly_feedback_status?: 'legitimate' | 'incorrect_category' | 'genuine_anomaly' | 'suspicious' | null;
  created_at: string;
}

export interface MLStatusResponse {
  workspace_id: string;
  active_model_versions: {
    categorizer: string;
    anomaly_detector: string;
    forecaster: string;
  };
  health: {
    status: string;
    total_transactions: number;
    anomalies_flagged: number;
    anomaly_rate: number;
    review_rate: number;
    verified_feedback_count: number;
    false_positive_rate: number;
    drift_detected: boolean;
    drift_details?: Array<{
      category: string;
      type: string;
      shift_ratio: number;
    }>;
  };
  labels: {
    total_transactions: number;
    verified_ratio: number;
    is_retraining_ready: boolean;
  };
  feedback: {
    total_feedback_count: number;
    legitimate_count: number;
    suspicious_count: number;
    false_positive_rate: number;
  };
  orchestrator_version?: string;
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
    description?: string | null;
    merchant: string | null;
    category_name?: string | null;
    amount_minor: number;
    currency?: string;
    anomaly_score?: number | null;
    anomaly_severity?: string | null;
    anomaly_alert_type?: string | null;
    anomaly_confidence?: number | null;
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

// 1. What-If Financial Simulator types
export interface SimulationScenarioItem {
  month_index: number;
  month_label: string;
  projected_income_minor: number;
  projected_expense_minor: number;
  net_cash_flow_minor: number;
  ending_cash_minor: number;
}

export interface SimulationScenarioDetail {
  label: string;
  revenue_change_pct: number;
  expense_change_pct: number;
  delayed_receivables_days: number;
  ending_cash_minor: number;
  lowest_cash_minor: number;
  runway_months: number;
  is_sustainable: boolean;
  projections: SimulationScenarioItem[];
}

export interface SimulationResponse {
  starting_cash_minor: number;
  baseline_monthly_income_minor: number;
  baseline_monthly_expense_minor: number;
  horizon_months: number;
  inputs: {
    revenue_change_pct: number;
    expense_change_pct: number;
    delayed_receivables_days: number;
    custom_events: any[];
  };
  scenarios: {
    baseline: SimulationScenarioDetail;
    expected_case: SimulationScenarioDetail;
    best_case: SimulationScenarioDetail;
    worst_case: SimulationScenarioDetail;
  };
  comparison_chart: Array<{
    month_index: number;
    month_label: string;
    baseline_cash_minor: number;
    expected_cash_minor: number;
    best_cash_minor: number;
    worst_cash_minor: number;
    expected_net_flow_minor: number;
    baseline_net_flow_minor: number;
  }>;
}

export interface SavedScenario {
  id: string;
  name: string;
  description: string | null;
  parameters: any;
  results: any;
  created_at: string;
}

// 2. Budget Management types
export interface CategoryBudgetPerformance {
  category: string;
  limit_minor: number;
  spent_minor: number;
  remaining_minor: number;
  spent_pct: number;
  status: 'safe' | 'warning' | 'over_budget' | 'unbudgeted';
  has_budget: boolean;
}

export interface BudgetAlert {
  category: string;
  severity: 'info' | 'warning' | 'critical';
  message: string;
  spent_minor: number;
  limit_minor: number;
}

export interface BudgetPerformanceResponse {
  budget_id: string | null;
  workspace_id: string;
  month: string;
  name: string;
  total_budget_limit_minor: number;
  total_spent_minor: number;
  remaining_minor: number;
  spent_pct: number;
  status: 'safe' | 'warning' | 'over_budget';
  overbudget_categories_count: number;
  category_performances: CategoryBudgetPerformance[];
  alerts: BudgetAlert[];
  comparison_chart: Array<{
    category: string;
    budget_minor: number;
    actual_minor: number;
    variance_minor: number;
    spent_pct: number;
    status: string;
  }>;
}

export interface BudgetSummary {
  id: string;
  month: string;
  name: string;
  total_limit_minor: number;
  total_spent_minor: number;
  spent_pct: number;
  status: string;
  overbudget_categories_count: number;
  created_at: string;
}

// 3. Bank Statement Reconciliation types
export interface ReconciliationItemData {
  id: string;
  date: string;
  description: string;
  amount_minor: number;
  reference?: string | null;
  transaction_id?: string | null;
  match_type: 'exact' | 'probable' | 'difference' | 'duplicate' | 'unmatched_bank' | 'unmatched_ledger';
  status: 'pending' | 'approved' | 'rejected';
  discrepancy_details?: {
    date_diff_days?: number;
    amount_diff_minor?: number;
    reason?: string;
  } | null;
}

export interface ReconciliationSessionData {
  id: string;
  workspace_id: string;
  filename: string;
  total_statement_rows: number;
  matched_count: number;
  unmatched_bank_count: number;
  unmatched_ledger_count: number;
  status: 'completed' | 'in_review' | 'reconciled';
  summary: {
    exact_matches: number;
    probable_matches: number;
    difference_matches: number;
    duplicate_matches: number;
    match_rate_pct: number;
  };
  created_at: string;
  items: ReconciliationItemData[];
}

// 4. Financial Health Score types
export interface HealthScoreFactor {
  id: string;
  name: string;
  score: number;
  weight: number;
  status: 'strong' | 'fair' | 'weak';
  metric_label: string;
  detail: string;
}

export interface HealthScoreData {
  overall_score: number;
  grade: 'A+' | 'A' | 'B' | 'C' | 'D' | 'F' | string;
  status_description: string;
  current_cash_minor: number;
  runway_months: number;
  factors: HealthScoreFactor[];
  positive_drivers: string[];
  negative_drivers: string[];
  suggestions: string[];
  historical_trend: Array<{
    month: string;
    score: number;
    net_flow_minor: number;
  }>;
}

// 5. Audit Log type
export interface AuditLogItem {
  id: string;
  action: string;
  resource_type: string;
  resource_id?: string | null;
  details?: any;
  created_at: string;
  user_id?: string | null;
}
