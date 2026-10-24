import client from './client';
import { AuthResponse } from '../types';

export const authApi = {
  login: async (data: any): Promise<AuthResponse> => {
    const res = await client.post('/auth/login', data);
    return res.data;
  },
  register: async (data: any): Promise<AuthResponse> => {
    const res = await client.post('/auth/register', data);
    return res.data;
  },
  me: async () => {
    const res = await client.get('/auth/me');
    return res.data;
  },
};
