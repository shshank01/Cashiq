import client from './client';
import { Transaction, TransactionsResponse } from '../types';

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
};
