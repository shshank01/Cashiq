import client from './client';
import { DashboardData } from '../types';

export const dashboardApi = {
  get: async (wid: string): Promise<DashboardData> => {
    const res = await client.get(`/workspaces/${wid}/dashboard`);
    return res.data;
  },
};
