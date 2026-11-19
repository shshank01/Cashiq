import client from './client';

export interface FxRates {
  base: string;
  rates: Record<string, number>;
  usd_to_inr: number;
  inr_to_usd: number;
  last_updated: string;
}

export interface FxConversionResult {
  amount: number;
  from_currency: string;
  to_currency: string;
  rate: number;
  usd_to_inr_rate: number;
  converted_amount: number;
  converted_amount_minor: number;
  timestamp: string;
}

export const fxApi = {
  getRates: async (): Promise<FxRates> => {
    const res = await client.get('/fx/rates');
    return res.data;
  },
  convert: async (payload: {
    amount: number;
    from_currency: string;
    to_currency: string;
    custom_rate?: number;
  }): Promise<FxConversionResult> => {
    const res = await client.post('/fx/convert', payload);
    return res.data;
  },
};
