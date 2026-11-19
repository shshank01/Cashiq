import client from './client';

export const documentsApi = {
  upload: async (wid: string, file: File) => {
    const formData = new FormData();
    formData.append('file', file);
    const res = await client.post(`/workspaces/${wid}/documents/upload`, formData, {
      headers: {
        'Content-Type': 'multipart/form-data',
      },
    });
    return res.data;
  },
  confirm: async (wid: string, documentId: string, drafts: any[]) => {
    const res = await client.post(`/workspaces/${wid}/documents/${documentId}/confirm`, {
      drafts,
    });
    return res.data;
  },
};
