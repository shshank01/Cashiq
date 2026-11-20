import client from './client';
import { SimulationResponse, SavedScenario } from '../types';

export const simulatorApi = {
  run: async (
    workspaceId: string,
    params: {
      revenue_change_pct: number;
      expense_change_pct: number;
      delayed_receivables_days: number;
      months: number;
      custom_events?: any[];
    }
  ): Promise<SimulationResponse> => {
    const res = await client.post(`/workspaces/${workspaceId}/simulation/run`, params);
    return res.data;
  },

  listScenarios: async (workspaceId: string): Promise<SavedScenario[]> => {
    const res = await client.get(`/workspaces/${workspaceId}/simulation/scenarios`);
    return res.data;
  },

  saveScenario: async (
    workspaceId: string,
    payload: {
      name: string;
      description?: string;
      parameters: any;
      results: any;
    }
  ): Promise<SavedScenario> => {
    const res = await client.post(`/workspaces/${workspaceId}/simulation/scenarios`, payload);
    return res.data;
  },

  deleteScenario: async (workspaceId: string, scenarioId: string): Promise<void> => {
    await client.delete(`/workspaces/${workspaceId}/simulation/scenarios/${scenarioId}`);
  },
};
