import client from './client';
import { Transaction, TransactionsResponse, MLStatusResponse } from '../types';

export const transactionsApi = {
  list: async (wid: string, params: any): Promise<TransactionsResponse> => {
    const res = await client.get(`/workspaces/${wid}/transactions`, { params });
    return res.data;
  },
  create: async (wid: string, data: any): Promise<Transaction> => {
    const res = await client.post(`/workspaces/${wid}/transactions`, data);
    return res.data;
  },
  update: async (wid: string, id: string, data: any): Promise<Transaction> => {
    const res = await client.put(`/workspaces/${wid}/transactions/${id}`, data);
    return res.data;
  },
  delete: async (wid: string, id: string): Promise<void> => {
    await client.delete(`/workspaces/${wid}/transactions/${id}`);
  },
  confirmCategory: async (wid: string, id: string, categoryName?: string): Promise<Transaction> => {
    const res = await client.post(`/workspaces/${wid}/transactions/${id}/confirm-category`, categoryName ? { category_name: categoryName } : {});
    return res.data;
  },
  submitAnomalyFeedback: async (
    wid: string,
    id: string,
    feedback: 'legitimate' | 'incorrect_category' | 'genuine_anomaly' | 'suspicious',
    notes?: string,
    confirmedCategory?: string
  ): Promise<any> => {
    const res = await client.post(`/workspaces/${wid}/transactions/${id}/anomaly-feedback`, {
      feedback,
      notes,
      confirmed_category: confirmedCategory,
    });
    return res.data;
  },
  getMLStatus: async (wid: string): Promise<MLStatusResponse> => {
    const res = await client.get(`/workspaces/${wid}/ml/status`);
    return res.data;
  },
  triggerRetraining: async (wid: string): Promise<any> => {
    const res = await client.post(`/workspaces/${wid}/ml/retrain`);
    return res.data;
  },
  scanAnomalies: async (wid: string): Promise<any> => {
    const res = await client.post(`/workspaces/${wid}/ml/scan-anomalies`);
    return res.data;
  },
  listAnomalies: async (
    wid: string,
    params?: { severity?: string; feedback_status?: string; page?: number; per_page?: number }
  ): Promise<{ items: Transaction[]; total: number; page: number; per_page: number; total_pages: number }> => {
    const res = await client.get(`/workspaces/${wid}/anomalies`, { params });
    return res.data;
  },
};
