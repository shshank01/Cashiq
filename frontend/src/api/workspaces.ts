import client from './client';
import { Workspace, BusinessProfile } from '../types';

export const workspacesApi = {
  list: async (): Promise<{ workspaces: Workspace[] }> => {
    const res = await client.get('/workspaces');
    return res.data;
  },
  create: async (data: any): Promise<Workspace> => {
    const res = await client.post('/workspaces', data);
    return res.data;
  },
  update: async (id: string, data: Partial<Workspace>): Promise<Workspace> => {
    const res = await client.patch(`/workspaces/${id}`, data);
    return res.data;
  },
  onboarding: async (id: string, data: any): Promise<{ workspace: Workspace; profile: BusinessProfile }> => {
    const res = await client.post(`/workspaces/${id}/onboarding`, data);
    return res.data;
  },
};
