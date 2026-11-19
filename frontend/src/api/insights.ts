import client from './client';
import { Insight } from '../types';

export const insightsApi = {
  list: async (wid: string): Promise<{ insights: Insight[] }> => {
    const res = await client.get(`/workspaces/${wid}/insights`);
    return res.data;
  },
  generate: async (wid: string): Promise<{ insights: Insight[] }> => {
    const res = await client.post(`/workspaces/${wid}/insights/generate`);
    return res.data;
  },
};
