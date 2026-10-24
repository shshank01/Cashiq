import React, { useState } from 'react';
import { Search, Building2, CheckCircle2, ArrowLeftRight } from 'lucide-react';
import { useAuth } from '../../contexts/AuthContext';
import { useWorkspace } from '../../contexts/WorkspaceContext';
import { CurrencyConverterModal } from '../CurrencyConverterModal';

export const TopBar: React.FC = () => {
  const { user } = useAuth();
  const { currentWorkspace, workspaces, setCurrentWorkspace, currency, setCurrency, fxRate } = useWorkspace();
  const [isConverterOpen, setIsConverterOpen] = useState(false);

  return (
    <>
      <header className="h-16 bg-white border-b border-stone-200 flex items-center justify-between px-6 z-10">
        <div className="flex items-center gap-3.5 flex-1">
          {/* Workspace Switcher */}
          <div className="relative">
            <div className="flex items-center gap-2 px-3 py-1.5 bg-stone-50 border border-stone-200 rounded-lg text-sm">
              <Building2 className="w-4 h-4 text-teal-700" />
              <select
                value={currentWorkspace?.id || ''}
                onChange={(e) => {
                  const target = workspaces.find((w) => w.id === e.target.value);
                  if (target) setCurrentWorkspace(target);
                }}
                className="bg-transparent font-medium text-stone-800 focus:outline-none cursor-pointer pr-4 text-xs sm:text-sm"
              >
                {workspaces.map((w) => (
                  <option key={w.id} value={w.id}>
                    {w.name} ({w.currency || 'USD'})
                  </option>
                ))}
              </select>
            </div>
          </div>

          {/* Currency Switcher: Rupee (₹) vs Dollar ($) */}
          <div className="flex items-center bg-stone-100 p-0.5 rounded-lg border border-stone-200" title="Switch reporting currency between US Dollar and Indian Rupee">
            <button
              type="button"
              onClick={() => setCurrency('USD')}
              className={`flex items-center gap-1 px-2.5 py-1 text-xs font-medium rounded-md transition-all ${
                currency === 'USD'
                  ? 'bg-white text-stone-900 shadow-xs border border-stone-200/80 font-bold'
                  : 'text-stone-500 hover:text-stone-800'
              }`}
            >
              <span className="font-semibold">$</span>
              <span>USD</span>
            </button>
            <button
              type="button"
              onClick={() => setCurrency('INR')}
              className={`flex items-center gap-1 px-2.5 py-1 text-xs font-medium rounded-md transition-all ${
                currency === 'INR'
                  ? 'bg-white text-teal-800 shadow-xs border border-stone-200/80 font-bold'
                  : 'text-stone-500 hover:text-stone-800'
              }`}
            >
              <span className="font-semibold">₹</span>
              <span>INR</span>
            </button>
          </div>

          {/* Quick FX Converter Modal Trigger */}
          <button
            type="button"
            onClick={() => setIsConverterOpen(true)}
            className="flex items-center gap-1.5 px-2.5 py-1.5 text-xs font-medium text-stone-600 hover:text-teal-800 bg-stone-50 hover:bg-stone-100 border border-stone-200 rounded-lg transition-colors shadow-2xs"
            title={`USD ⇄ INR Converter Tool (Active rate: 1 USD = ₹${fxRate.toFixed(2)})`}
          >
            <ArrowLeftRight className="w-3.5 h-3.5 text-teal-600" />
            <span className="hidden sm:inline">USD ⇄ INR</span>
          </button>

          {/* Global Search Bar */}
          <div className="relative w-56 md:w-72 hidden md:block">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-stone-400" />
            <input 
              type="text" 
              placeholder="Search records, categories, vendors..." 
              className="w-full pl-9 pr-4 py-1.5 bg-stone-50 border border-stone-200 rounded-lg text-xs md:text-sm focus:outline-none focus:ring-1 focus:ring-teal-600 focus:border-teal-600 transition-all text-stone-800 placeholder-stone-400"
            />
          </div>
        </div>
        
        <div className="flex items-center gap-4">
          {/* Ledger Integrity Indicator */}
          <div className="hidden lg:flex items-center gap-1.5 px-2.5 py-1 bg-emerald-50 border border-emerald-200/80 rounded-full text-emerald-800 text-xs font-medium">
            <CheckCircle2 className="w-3.5 h-3.5 text-emerald-600" />
            <span>Ledger Isolated</span>
          </div>

          <div className="h-6 w-px bg-stone-200"></div>

          {/* User Profile Badge */}
          <div className="flex items-center gap-2.5">
            <div className="w-8 h-8 bg-teal-100 border border-teal-200 rounded-full flex items-center justify-center text-teal-800 font-semibold text-xs shadow-xs">
              {user?.full_name ? user.full_name.charAt(0).toUpperCase() : 'U'}
            </div>
            <div className="text-xs text-left hidden sm:block">
              <p className="font-semibold text-stone-800 leading-none">{user?.full_name || 'Business User'}</p>
              <p className="text-[11px] text-stone-400 mt-0.5">{user?.email}</p>
            </div>
          </div>
        </div>
      </header>

      {/* Converter Modal */}
      <CurrencyConverterModal
        isOpen={isConverterOpen}
        onClose={() => setIsConverterOpen(false)}
      />
    </>
  );
};

export default TopBar;
