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
  getBusinessProfile: async (id: string): Promise<BusinessProfile> => {
    const res = await client.get(`/workspaces/${id}/business-profile`);
    return res.data;
  },
  updateBusinessProfile: async (id: string, data: any): Promise<{ workspace: Workspace; profile: BusinessProfile }> => {
    const res = await client.put(`/workspaces/${id}/business-profile`, data);
    return res.data;
  },
  getIndustryTaxonomy: async (): Promise<{ industries: any[]; categories: string[] }> => {
    const res = await client.get('/ml/industry-taxonomy');
    return res.data;
  },
};
