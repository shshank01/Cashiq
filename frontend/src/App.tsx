import React from 'react';
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import AppLayout from './components/layout/AppLayout';
import DashboardPage from './pages/DashboardPage';
import TransactionsPage from './pages/TransactionsPage';
import ForecastPage from './pages/ForecastPage';
import InsightsPage from './pages/InsightsPage';
import PayablesPage from './pages/PayablesPage';
import ReceivablesPage from './pages/ReceivablesPage';
import RecurringPage from './pages/RecurringPage';
import ReportsPage from './pages/ReportsPage';
import AssistantPage from './pages/AssistantPage';
import SettingsPage from './pages/SettingsPage';
import LoginPage from './pages/auth/LoginPage';
import RegisterPage from './pages/auth/RegisterPage';
import { AuthProvider, useAuth } from './contexts/AuthContext';
import { WorkspaceProvider } from './contexts/WorkspaceContext';

const ProtectedRoute = ({ children }: { children: React.ReactNode }) => {
  const { isAuthenticated, isLoading } = useAuth();
  
  if (isLoading) return <div>Loading...</div>;
  if (!isAuthenticated) return <Navigate to="/login" replace />;
  
  return <>{children}</>;
};

function App() {
  return (
    <AuthProvider>
      <BrowserRouter>
        <Routes>
          <Route path="/login" element={<LoginPage />} />
          <Route path="/register" element={<RegisterPage />} />
          
          <Route
            path="/"
            element={
              <ProtectedRoute>
                <WorkspaceProvider>
                  <AppLayout />
                </WorkspaceProvider>
              </ProtectedRoute>
            }
          >
            <Route index element={<Navigate to="/dashboard" replace />} />
            <Route path="dashboard" element={<DashboardPage />} />
            <Route path="transactions" element={<TransactionsPage />} />
            <Route path="forecast" element={<ForecastPage />} />
            <Route path="insights" element={<InsightsPage />} />
            <Route path="payables" element={<PayablesPage />} />
            <Route path="receivables" element={<ReceivablesPage />} />
            <Route path="recurring" element={<RecurringPage />} />
            <Route path="reports" element={<ReportsPage />} />
            <Route path="assistant" element={<AssistantPage />} />
            <Route path="settings" element={<SettingsPage />} />
          </Route>
        </Routes>
      </BrowserRouter>
    </AuthProvider>
  );
}

export default App;
