import client from './client';
import { Payable, Receivable } from '../types';

export const payablesApi = {
  list: async (wid: string) => {
    const res = await client.get(`/workspaces/${wid}/payables`);
    return res.data;
  },
  create: async (wid: string, data: any) => {
    const res = await client.post(`/workspaces/${wid}/payables`, data);
    return res.data;
  }
};

export const receivablesApi = {
  list: async (wid: string) => {
    const res = await client.get(`/workspaces/${wid}/receivables`);
    return res.data;
  },
  create: async (wid: string, data: any) => {
    const res = await client.post(`/workspaces/${wid}/receivables`, data);
    return res.data;
  }
};
