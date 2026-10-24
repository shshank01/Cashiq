import client from './client';
import { AssistantResponse } from '../types';

export interface AssistantConfig {
  is_configured: boolean;
  provider: 'openai' | 'gemini';
  model: string;
  has_openai_key: boolean;
  has_gemini_key: boolean;
  masked_key: string;
}

export const assistantApi = {
  chat: async (wid: string, data: { message: string, conversation_id?: string }): Promise<AssistantResponse> => {
    const res = await client.post(`/workspaces/${wid}/assistant/chat`, data);
    return res.data;
  },
  getConfig: async (): Promise<AssistantConfig> => {
    const res = await client.get('/assistant/config');
    return res.data;
  },
  updateConfig: async (data: { provider: string; api_key?: string; model?: string }) => {
    const res = await client.post('/assistant/config', data);
    return res.data;
  },
  testKey: async (data: { provider: string; api_key?: string; model?: string }) => {
    const res = await client.post('/assistant/test-key', data);
    return res.data;
  },
};

