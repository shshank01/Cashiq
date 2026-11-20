import client from './client';
import { HealthScoreData } from '../types';

export const healthScoreApi = {
  get: async (workspaceId: string): Promise<HealthScoreData> => {
    const res = await client.get(`/workspaces/${workspaceId}/health-score`);
    return res.data;
  },
};
