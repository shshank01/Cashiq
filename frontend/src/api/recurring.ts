import client from './client';
import { RecurringPayment } from '../types';

export interface DetectResponse {
  recurring_payments: RecurringPayment[];
  detected_count?: number;
  transactions_analyzed?: number;
  message?: string;
}

export const recurringApi = {
  list: async (wid: string): Promise<{ recurring_payments: RecurringPayment[] }> => {
    const res = await client.get(`/workspaces/${wid}/recurring`);
    return res.data;
  },
  detect: async (wid: string): Promise<DetectResponse> => {
    const res = await client.post(`/workspaces/${wid}/recurring/detect`);
    return res.data;
  },
  create: async (wid: string, payload: Partial<RecurringPayment>): Promise<{ recurring_payments: RecurringPayment[] }> => {
    const res = await client.post(`/workspaces/${wid}/recurring`, payload);
    return res.data;
  },
  delete: async (wid: string, ruleId: string): Promise<{ recurring_payments: RecurringPayment[] }> => {
    const res = await client.delete(`/workspaces/${wid}/recurring/${ruleId}`);
    return res.data;
  },
  toggleStatus: async (wid: string, ruleId: string): Promise<{ recurring_payments: RecurringPayment[] }> => {
    const res = await client.post(`/workspaces/${wid}/recurring/${ruleId}/toggle`);
    return res.data;
  },
  seedDemo: async (wid: string): Promise<DetectResponse> => {
    const res = await client.post(`/workspaces/${wid}/recurring/seed-demo`);
    return res.data;
  }
};
