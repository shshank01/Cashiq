import client from './client';
import { ReconciliationSessionData } from '../types';

export const reconciliationApi = {
  upload: async (
    workspaceId: string,
    file: File,
    accountId?: string
  ): Promise<any> => {
    const formData = new FormData();
    formData.append('file', file);
    if (accountId) formData.append('account_id', accountId);

    const res = await client.post(`/workspaces/${workspaceId}/reconciliation/upload`, formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
    });
    return res.data;
  },

  listSessions: async (workspaceId: string): Promise<any[]> => {
    const res = await client.get(`/workspaces/${workspaceId}/reconciliation/sessions`);
    return res.data;
  },

  getSession: async (workspaceId: string, sessionId: string): Promise<ReconciliationSessionData> => {
    const res = await client.get(`/workspaces/${workspaceId}/reconciliation/sessions/${sessionId}`);
    return res.data;
  },

  approveMatch: async (workspaceId: string, sessionId: string, itemId: string): Promise<void> => {
    await client.post(`/workspaces/${workspaceId}/reconciliation/sessions/${sessionId}/approve`, {
      item_id: itemId,
    });
  },

  importUnmatched: async (workspaceId: string, sessionId: string, itemIds: string[]): Promise<any> => {
    const res = await client.post(
      `/workspaces/${workspaceId}/reconciliation/sessions/${sessionId}/import-unmatched`,
      { item_ids: itemIds }
    );
    return res.data;
  },

  exportReport: async (workspaceId: string, sessionId: string): Promise<Blob> => {
    const res = await client.get(
      `/workspaces/${workspaceId}/reconciliation/sessions/${sessionId}/export-report`,
      { responseType: 'blob' }
    );
    return res.data;
  },
};
