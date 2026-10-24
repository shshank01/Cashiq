import client from './client';
import { ForecastData } from '../types';

export const forecastApi = {
  get: async (wid: string): Promise<ForecastData> => {
    const res = await client.get(`/workspaces/${wid}/forecast`);
    return res.data;
  },
  generate: async (wid: string, days: number = 30): Promise<ForecastData> => {
    const res = await client.post(`/workspaces/${wid}/forecast/generate`, { days });
    return res.data;
  },
};

export default forecastApi;
