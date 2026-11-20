import client from './client';
import { BudgetPerformanceResponse, BudgetSummary } from '../types';

export const budgetsApi = {
  list: async (workspaceId: string): Promise<BudgetSummary[]> => {
    const res = await client.get(`/workspaces/${workspaceId}/budgets`);
    return res.data;
  },

  getPerformance: async (workspaceId: string, month?: string): Promise<BudgetPerformanceResponse> => {
    const res = await client.get(`/workspaces/${workspaceId}/budgets/performance`, {
      params: month ? { month } : {},
    });
    return res.data;
  },

  createOrUpdate: async (
    workspaceId: string,
    payload: {
      month: string;
      name?: string;
      category_limits: Array<{
        category_name: string;
        limit_minor: number;
        alert_threshold_pct?: number;
      }>;
      total_limit_minor?: number;
      currency?: string;
    }
  ): Promise<BudgetPerformanceResponse> => {
    const res = await client.post(`/workspaces/${workspaceId}/budgets`, payload);
    return res.data;
  },

  delete: async (workspaceId: string, budgetId: string): Promise<void> => {
    await client.delete(`/workspaces/${workspaceId}/budgets/${budgetId}`);
  },
};
