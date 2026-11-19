import React, { useState, useEffect } from 'react';
import { ArrowLeftRight, Check, Copy, RefreshCw, SlidersHorizontal, Info, Sparkles } from 'lucide-react';
import { useWorkspace } from '../contexts/WorkspaceContext';
import { formatMoney, getCurrencySymbol, DEFAULT_USD_TO_INR } from '../utils/format';
import { Modal } from './ui/Modal';
import { Button } from './ui/Button';

interface CurrencyConverterModalProps {
  isOpen: boolean;
  onClose: () => void;
}

export const CurrencyConverterModal: React.FC<CurrencyConverterModalProps> = ({ isOpen, onClose }) => {
  const { fxRate, setFxRate, convertWithFx, setConvertWithFx } = useWorkspace();

  const [fromCurrency, setFromCurrency] = useState<'USD' | 'INR'>('USD');
  const [toCurrency, setToCurrency] = useState<'USD' | 'INR'>('INR');
  const [inputAmount, setInputAmount] = useState<string>('1000');
  const [customRateInput, setCustomRateInput] = useState<string>(String(fxRate));
  const [isEditingRate, setIsEditingRate] = useState<boolean>(false);
  const [copied, setCopied] = useState<boolean>(false);

  useEffect(() => {
    setCustomRateInput(String(fxRate));
  }, [fxRate]);

  const numAmount = parseFloat(inputAmount) || 0;
  const effectiveRate = parseFloat(customRateInput) || fxRate || DEFAULT_USD_TO_INR;

  const convertedValue = fromCurrency === 'USD'
    ? numAmount * effectiveRate
    : numAmount / effectiveRate;

  const handleSwap = () => {
    setFromCurrency(prev => (prev === 'USD' ? 'INR' : 'USD'));
    setToCurrency(prev => (prev === 'USD' ? 'INR' : 'USD'));
  };

  const handleApplyCustomRate = () => {
    const r = parseFloat(customRateInput);
    if (r && r > 0) {
      setFxRate(r);
      setIsEditingRate(false);
    }
  };

  const handleResetRate = () => {
    setFxRate(DEFAULT_USD_TO_INR);
    setCustomRateInput(String(DEFAULT_USD_TO_INR));
    setIsEditingRate(false);
  };

  const handleCopy = () => {
    const formatted = formatMoney(Math.round(convertedValue * 100), toCurrency);
    navigator.clipboard.writeText(formatted);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const usdPresets = [100, 500, 1000, 5000, 10000];
  const inrPresets = [10000, 50000, 100000, 500000, 1000000];

  return (
    <Modal
      isOpen={isOpen}
      onClose={onClose}
      title="USD ⇄ INR Currency Converter"
      footer={
        <div className="flex items-center justify-between w-full">
          <div className="flex items-center gap-2">
            <input
              type="checkbox"
              id="convertLedgerToggle"
              checked={convertWithFx}
              onChange={(e) => setConvertWithFx(e.target.checked)}
              className="rounded border-stone-300 text-teal-600 focus:ring-teal-500 cursor-pointer h-4 w-4"
            />
            <label htmlFor="convertLedgerToggle" className="text-xs text-stone-600 cursor-pointer select-none">
              Apply live conversion across workspace ledger
            </label>
          </div>
          <Button variant="primary" onClick={onClose} className="text-xs">
            Done
          </Button>
        </div>
      }
    >
      <div className="space-y-5">
        {/* Conversion Cards */}
        <div className="space-y-3">
          {/* Source Amount */}
          <div className="p-4 bg-stone-50 border border-stone-200 rounded-xl">
            <div className="flex items-center justify-between mb-2">
              <span className="text-xs font-semibold uppercase tracking-wider text-stone-500">You Send / Enter</span>
              <div className="flex items-center gap-1 bg-white border border-stone-200 rounded-lg p-0.5">
                <button
                  type="button"
                  onClick={() => { setFromCurrency('USD'); setToCurrency('INR'); }}
                  className={`px-2.5 py-1 text-xs font-semibold rounded-md transition-all ${
                    fromCurrency === 'USD' ? 'bg-stone-900 text-white shadow-xs' : 'text-stone-500 hover:text-stone-800'
                  }`}
                >
                  $ USD
                </button>
                <button
                  type="button"
                  onClick={() => { setFromCurrency('INR'); setToCurrency('USD'); }}
                  className={`px-2.5 py-1 text-xs font-semibold rounded-md transition-all ${
                    fromCurrency === 'INR' ? 'bg-teal-700 text-white shadow-xs' : 'text-stone-500 hover:text-stone-800'
                  }`}
                >
                  ₹ INR
                </button>
              </div>
            </div>

            <div className="flex items-center gap-3">
              <span className="text-2xl font-bold font-mono text-stone-700">
                {getCurrencySymbol(fromCurrency)}
              </span>
              <input
                type="number"
                min="0"
                step="any"
                value={inputAmount}
                onChange={(e) => setInputAmount(e.target.value)}
                placeholder="0.00"
                className="w-full text-2xl font-bold font-mono text-stone-900 bg-transparent focus:outline-none"
              />
            </div>
          </div>

          {/* Swap Button Divider */}
          <div className="flex items-center justify-center -my-1">
            <button
              type="button"
              onClick={handleSwap}
              className="p-2 bg-white border border-stone-200 rounded-full text-stone-600 hover:text-teal-700 hover:border-teal-500 shadow-xs hover:shadow transition-all"
              title="Reverse conversion direction"
            >
              <ArrowLeftRight className="w-4 h-4" />
            </button>
          </div>

          {/* Target Amount */}
          <div className="p-4 bg-teal-50/50 border border-teal-200 rounded-xl">
            <div className="flex items-center justify-between mb-2">
              <span className="text-xs font-semibold uppercase tracking-wider text-teal-800">Equivalent In</span>
              <span className="text-xs font-bold text-teal-900 px-2.5 py-0.5 bg-teal-100 rounded-md">
                {toCurrency}
              </span>
            </div>

            <div className="flex items-center justify-between gap-3">
              <div className="flex items-center gap-3">
                <span className="text-2xl font-bold font-mono text-teal-800">
                  {getCurrencySymbol(toCurrency)}
                </span>
                <span className="text-2xl font-bold font-mono text-teal-950">
                  {toCurrency === 'INR'
                    ? convertedValue.toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
                    : convertedValue.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                </span>
              </div>

              <button
                type="button"
                onClick={handleCopy}
                className="p-2 text-teal-700 hover:text-teal-900 hover:bg-teal-100/60 rounded-lg transition-colors"
                title="Copy converted value"
              >
                {copied ? <Check className="w-4 h-4 text-emerald-600" /> : <Copy className="w-4 h-4" />}
              </button>
            </div>
          </div>
        </div>

        {/* Quick Amount Presets */}
        <div>
          <p className="text-xs font-medium text-stone-500 mb-2">Quick Presets ({fromCurrency}):</p>
          <div className="flex flex-wrap gap-1.5">
            {(fromCurrency === 'USD' ? usdPresets : inrPresets).map((preset) => (
              <button
                key={preset}
                type="button"
                onClick={() => setInputAmount(String(preset))}
                className="px-2.5 py-1 text-xs bg-stone-100 hover:bg-stone-200 text-stone-700 rounded-md font-mono transition-colors"
              >
                {fromCurrency === 'USD' ? `$${preset.toLocaleString()}` : `₹${preset.toLocaleString('en-IN')}`}
              </button>
            ))}
          </div>
        </div>

        {/* Exchange Rate Card & Override */}
        <div className="p-3.5 bg-stone-50 rounded-lg border border-stone-200 text-xs space-y-2.5">
          <div className="flex items-center justify-between">
            <span className="text-stone-500 font-medium flex items-center gap-1.5">
              <Sparkles className="w-3.5 h-3.5 text-teal-600" />
              Active Exchange Rate:
            </span>
            <div className="flex items-center gap-2">
              <span className="font-mono font-bold text-stone-900">
                1 USD = ₹{effectiveRate.toFixed(2)} INR
              </span>
              <button
                type="button"
                onClick={() => setIsEditingRate(!isEditingRate)}
                className="text-stone-500 hover:text-teal-700 text-[11px] underline"
              >
                {isEditingRate ? 'Cancel' : 'Edit Rate'}
              </button>
            </div>
          </div>

          {isEditingRate && (
            <div className="pt-2 border-t border-stone-200/80 flex items-center gap-2">
              <div className="flex-1 flex items-center gap-1 bg-white border border-stone-300 rounded px-2 py-1">
                <span className="text-stone-400 font-mono">₹</span>
                <input
                  type="number"
                  step="0.01"
                  value={customRateInput}
                  onChange={(e) => setCustomRateInput(e.target.value)}
                  className="w-full text-xs font-mono focus:outline-none"
                  placeholder="83.50"
                />
              </div>
              <Button variant="primary" onClick={handleApplyCustomRate} className="py-1 px-3 text-xs">
                Save
              </Button>
              <Button variant="outline" onClick={handleResetRate} className="py-1 px-2 text-xs">
                Reset
              </Button>
            </div>
          )}

          <div className="text-[11px] text-stone-400 flex items-center gap-1">
            <Info className="w-3 h-3 text-stone-400 shrink-0" />
            <span>Inverse rate: 1 INR ≈ ${(1 / effectiveRate).toFixed(4)} USD (Real-time RBI standard benchmark)</span>
          </div>
        </div>
      </div>
    </Modal>
  );
};

export default CurrencyConverterModal;
