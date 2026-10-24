import React, { createContext, useContext, useState, useEffect, useCallback } from 'react';
import { Workspace } from '../types';
import { workspacesApi } from '../api/workspaces';
import { fxApi } from '../api/fx';
import { useAuth } from './AuthContext';
import { DEFAULT_USD_TO_INR, convertAndFormatMoney, convertMoneyMinor, formatMoney } from '../utils/format';

interface WorkspaceContextType {
  currentWorkspace: Workspace | null;
  workspaces: Workspace[];
  currency: string;
  setCurrency: (currency: 'USD' | 'INR') => Promise<void>;
  setCurrentWorkspace: (workspace: Workspace) => void;
  fxRate: number;
  setFxRate: (rate: number) => void;
  convertWithFx: boolean;
  setConvertWithFx: (enabled: boolean) => void;
  formatConverted: (amountMinor: number | undefined | null, originalCurrency?: string) => string;
  convertAmount: (amount: number, fromCurrency: string, toCurrency: string) => number;
  isLoading: boolean;
  refreshWorkspaces: () => Promise<void>;
}

const WorkspaceContext = createContext<WorkspaceContextType | undefined>(undefined);

export const WorkspaceProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const { isAuthenticated } = useAuth();
  const [workspaces, setWorkspaces] = useState<Workspace[]>([]);
  const [currentWorkspace, setCurrentWorkspaceState] = useState<Workspace | null>(null);
  const [isLoading, setIsLoading] = useState(false);

  // FX state
  const [fxRate, setFxRateState] = useState<number>(() => {
    const stored = localStorage.getItem('cashiq_fx_rate');
    return stored ? parseFloat(stored) : DEFAULT_USD_TO_INR;
  });

  const [convertWithFx, setConvertWithFxState] = useState<boolean>(() => {
    const stored = localStorage.getItem('cashiq_convert_fx');
    return stored !== null ? stored === 'true' : true;
  });

  // Display currency state ('USD' | 'INR')
  const [displayCurrency, setDisplayCurrency] = useState<'USD' | 'INR'>(() => {
    const stored = localStorage.getItem('preferredCurrency');
    return stored === 'INR' ? 'INR' : 'USD';
  });

  // Fetch live market FX rates from backend
  useEffect(() => {
    const fetchRates = async () => {
      try {
        const data = await fxApi.getRates();
        if (data.usd_to_inr && data.usd_to_inr > 0) {
          // If user hasn't overridden with a custom rate, sync live rate
          const isCustom = localStorage.getItem('cashiq_fx_rate_custom');
          if (!isCustom) {
            setFxRateState(data.usd_to_inr);
          }
        }
      } catch (err) {
        // Fall back to default
      }
    };
    fetchRates();
  }, []);

  const setFxRate = (rate: number) => {
    const valid = rate > 0 ? rate : DEFAULT_USD_TO_INR;
    setFxRateState(valid);
    localStorage.setItem('cashiq_fx_rate', String(valid));
    localStorage.setItem('cashiq_fx_rate_custom', 'true');
  };

  const setConvertWithFx = (enabled: boolean) => {
    setConvertWithFxState(enabled);
    localStorage.setItem('cashiq_convert_fx', String(enabled));
  };

  const refreshWorkspaces = async () => {
    if (!isAuthenticated) return;
    try {
      setIsLoading(true);
      const data = await workspacesApi.list();
      setWorkspaces(data.workspaces);
      
      const storedId = localStorage.getItem('workspaceId');

      if (storedId && data.workspaces.find(w => w.id === storedId)) {
        const found = data.workspaces.find(w => w.id === storedId)!;
        setCurrentWorkspaceState({ ...found });
      } else if (data.workspaces.length > 0) {
        setCurrentWorkspace(data.workspaces[0]);
      }
    } catch (error) {
      console.error('Failed to fetch workspaces', error);
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    if (isAuthenticated) {
      refreshWorkspaces();
    } else {
      setWorkspaces([]);
      setCurrentWorkspaceState(null);
    }
  }, [isAuthenticated]);

  const setCurrentWorkspace = (workspace: Workspace) => {
    localStorage.setItem('workspaceId', workspace.id);
    setCurrentWorkspaceState(workspace);
  };

  const setCurrency = async (newCurr: 'USD' | 'INR') => {
    localStorage.setItem('preferredCurrency', newCurr);
    setDisplayCurrency(newCurr);
  };

  // Helper to convert arbitrary amounts
  const convertAmount = useCallback((amount: number, fromCurrency: string, toCurrency: string): number => {
    const fromNorm = (fromCurrency || 'USD').toUpperCase();
    const toNorm = (toCurrency || 'USD').toUpperCase();
    if (fromNorm === toNorm) return amount;
    if (fromNorm === 'USD' && toNorm === 'INR') return amount * fxRate;
    if (fromNorm === 'INR' && toNorm === 'USD') return amount / fxRate;
    return amount;
  }, [fxRate]);

  // Helper to format minor unit with automatic base -> active currency conversion
  const formatConverted = useCallback((amountMinor: number | undefined | null, originalCurrency?: string): string => {
    const base = (originalCurrency || 'USD').toUpperCase();
    const target = displayCurrency.toUpperCase();
    return convertAndFormatMoney(amountMinor, base, target, convertWithFx, fxRate);
  }, [displayCurrency, convertWithFx, fxRate]);

  return (
    <WorkspaceContext.Provider value={{
      currentWorkspace,
      workspaces,
      currency: displayCurrency,
      setCurrency,
      setCurrentWorkspace,
      fxRate,
      setFxRate,
      convertWithFx,
      setConvertWithFx,
      formatConverted,
      convertAmount,
      isLoading,
      refreshWorkspaces
    }}>
      {children}
    </WorkspaceContext.Provider>
  );
};

export const useWorkspace = () => {
  const context = useContext(WorkspaceContext);
  if (context === undefined) {
    throw new Error('useWorkspace must be used within a WorkspaceProvider');
  }
  return context;
};
