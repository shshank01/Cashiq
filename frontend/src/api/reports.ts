import client from './client';

export const reportsApi = {
  getIncomeExpense: async (wid: string, params: any) => {
    const res = await client.get(`/workspaces/${wid}/reports/income-expense`, { params });
    return res.data;
  },
  getCategorySpend: async (wid: string, params: any) => {
    const res = await client.get(`/workspaces/${wid}/reports/category-spend`, { params });
    return res.data;
  },
  getCashFlow: async (wid: string, params: any) => {
    const res = await client.get(`/workspaces/${wid}/reports/cash-flow`, { params });
    return res.data;
  },
  getSummary: async (wid: string, params: any) => {
    const res = await client.get(`/workspaces/${wid}/reports/summary`, { params });
    return res.data;
  },
  downloadExcel: async (wid: string, params: any): Promise<Blob> => {
    const res = await client.get(`/workspaces/${wid}/reports/export/excel`, {
      params,
      responseType: 'blob',
    });
    return res.data;
  },
  downloadPdf: async (wid: string, params: any): Promise<Blob> => {
    const res = await client.get(`/workspaces/${wid}/reports/export/pdf`, {
      params,
      responseType: 'blob',
    });
    return res.data;
  },
};
