import React, { useState, useEffect } from 'react';
import { useWorkspace } from '../contexts/WorkspaceContext';
import { useAuth } from '../contexts/AuthContext';
import { workspacesApi } from '../api/workspaces';
import { Button } from '../components/ui/Button';
import { Input } from '../components/ui/Input';
import { Card } from '../components/ui/Card';
import { Building, User as UserIcon, Shield, Check, ArrowLeftRight, Sparkles, Bot, Eye, EyeOff, ExternalLink, CheckCircle2, AlertCircle, RefreshCw } from 'lucide-react';
import { CurrencyConverterModal } from '../components/CurrencyConverterModal';
import { assistantApi, AssistantConfig } from '../api/assistant';

export function SettingsPage() {
  const { 
    currentWorkspace, 
    currency, 
    setCurrency, 
    refreshWorkspaces,
    fxRate,
    setFxRate,
    convertWithFx,
    setConvertWithFx 
  } = useWorkspace();
  const { user } = useAuth();

  const [workspaceName, setWorkspaceName] = useState(currentWorkspace?.name || '');
  const [selectedCurrency, setSelectedCurrency] = useState<'USD' | 'INR'>((currency as 'USD' | 'INR') || 'USD');
  const [rateInput, setRateInput] = useState<string>(String(fxRate));
  const [isSaving, setIsSaving] = useState(false);
  const [isSaved, setIsSaved] = useState(false);
  const [isConverterOpen, setIsConverterOpen] = useState(false);

  // AI Assistant configuration state
  const [aiConfig, setAiConfig] = useState<AssistantConfig | null>(null);
  const [aiProvider, setAiProvider] = useState<'openai' | 'gemini'>('openai');
  const [aiApiKey, setAiApiKey] = useState('');
  const [aiModel, setAiModel] = useState('gpt-4o-mini');
  const [showApiKey, setShowApiKey] = useState(false);
  const [isTestingKey, setIsTestingKey] = useState(false);
  const [testResult, setTestResult] = useState<{ success?: boolean; message?: string; error?: string } | null>(null);
  const [isSavingAi, setIsSavingAi] = useState(false);
  const [isAiSaved, setIsAiSaved] = useState(false);

  const loadAiConfig = async () => {
    try {
      const cfg = await assistantApi.getConfig();
      setAiConfig(cfg);
      if (cfg.provider) {
        setAiProvider(cfg.provider);
      }
      if (cfg.model) {
        setAiModel(cfg.model);
      }
    } catch (e) {
      console.error('Failed to load AI config:', e);
    }
  };

  useEffect(() => {
    loadAiConfig();
  }, []);

  const handleTestKey = async () => {
    setIsTestingKey(true);
    setTestResult(null);
    try {
      const res = await assistantApi.testKey({
        provider: aiProvider,
        api_key: aiApiKey || undefined,
        model: aiModel
      });
      setTestResult(res);
      if (res.success && res.model) {
        setAiModel(res.model);
        await loadAiConfig();
      }
    } catch (err: any) {
      setTestResult({
        success: false,
        error: err.response?.data?.detail || err.message || 'Verification failed.'
      });
    } finally {
      setIsTestingKey(false);
    }
  };

  const handleSaveAiConfig = async (e: React.FormEvent) => {
    e.preventDefault();
    setIsSavingAi(true);
    try {
      await assistantApi.updateConfig({
        provider: aiProvider,
        api_key: aiApiKey || undefined,
        model: aiModel
      });
      await loadAiConfig();
      setAiApiKey('');
      setIsAiSaved(true);
      setTimeout(() => setIsAiSaved(false), 3000);
    } catch (err) {
      console.error('Failed to update AI configuration:', err);
    } finally {
      setIsSavingAi(false);
    }
  };

  useEffect(() => {
    if (currentWorkspace?.name) {
      setWorkspaceName(currentWorkspace.name);
    }
    if (currency) {
      setSelectedCurrency((currency.toUpperCase() === 'INR' ? 'INR' : 'USD'));
    }
    setRateInput(String(fxRate));
  }, [currentWorkspace, currency, fxRate]);

  const handleSaveWorkspace = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!currentWorkspace) return;

    setIsSaving(true);
    try {
      const numRate = parseFloat(rateInput);
      if (numRate && numRate > 0) {
        setFxRate(numRate);
      }

      await workspacesApi.update(currentWorkspace.id, {
        name: workspaceName,
        currency: selectedCurrency,
      });
      await setCurrency(selectedCurrency);
      await refreshWorkspaces();
      setIsSaved(true);
      setTimeout(() => setIsSaved(false), 3000);
    } catch (err) {
      console.error('Failed to update workspace settings:', err);
    } finally {
      setIsSaving(false);
    }
  };

  return (
    <div className="space-y-6 max-w-4xl pb-10">
      <div>
        <h1 className="text-2xl font-bold text-stone-900 font-serif">Workspace & Account Settings</h1>
        <p className="text-sm text-stone-500 mt-1">
          Manage entity information, accounting currency defaults, exchange rates, and security configurations.
        </p>
      </div>

      {/* Workspace Configuration */}
      <Card className="p-6">
        <div className="flex items-center gap-3 border-b border-stone-100 pb-4 mb-5">
          <Building className="w-5 h-5 text-teal-600" />
          <h2 className="text-base font-semibold text-stone-900">Workspace Configuration</h2>
        </div>

        <form onSubmit={handleSaveWorkspace} className="space-y-5 max-w-lg">
          <Input
            label="Organization / Business Legal Name"
            value={workspaceName}
            onChange={(e) => setWorkspaceName(e.target.value)}
            placeholder="e.g. Apex Cloud Technologies Inc"
          />

          <div>
            <label className="block text-sm font-medium text-stone-700 mb-1.5">
              Reporting Base Currency
            </label>
            <p className="text-xs text-stone-500 mb-3">
              Choose your primary financial currency. All dashboard KPIs, transactions, forecasts, and recurring schedules will format in this currency.
            </p>
            <div className="grid grid-cols-2 gap-3">
              <button
                type="button"
                onClick={() => setSelectedCurrency('USD')}
                className={`flex items-center justify-between p-3.5 rounded-lg border text-left transition-all ${
                  selectedCurrency === 'USD'
                    ? 'border-teal-600 bg-teal-50/50 text-teal-900 ring-1 ring-teal-600'
                    : 'border-stone-200 hover:border-stone-300 bg-white text-stone-700'
                }`}
              >
                <div>
                  <p className="font-semibold text-sm">US Dollar ($)</p>
                  <p className="text-xs text-stone-500 mt-0.5">USD (Standard En-US)</p>
                </div>
                <span className="text-lg font-bold font-mono">$</span>
              </button>

              <button
                type="button"
                onClick={() => setSelectedCurrency('INR')}
                className={`flex items-center justify-between p-3.5 rounded-lg border text-left transition-all ${
                  selectedCurrency === 'INR'
                    ? 'border-teal-600 bg-teal-50/50 text-teal-900 ring-1 ring-teal-600'
                    : 'border-stone-200 hover:border-stone-300 bg-white text-stone-700'
                }`}
              >
                <div>
                  <p className="font-semibold text-sm">Indian Rupee (₹)</p>
                  <p className="text-xs text-stone-500 mt-0.5">INR (Lakhs / Crores En-IN)</p>
                </div>
                <span className="text-lg font-bold font-mono">₹</span>
              </button>
            </div>
          </div>

          <div className="flex items-center gap-3 pt-2">
            <Button type="submit" variant="primary" disabled={isSaving}>
              {isSaving ? 'Saving Changes...' : 'Save Changes'}
            </Button>
            {isSaved && (
              <span className="flex items-center gap-1.5 text-xs text-teal-600 font-medium">
                <Check className="w-4 h-4" /> Preferences updated successfully
              </span>
            )}
          </div>
        </form>
      </Card>

      {/* Currency Conversion & Exchange Rate Configuration */}
      <Card className="p-6">
        <div className="flex items-center justify-between border-b border-stone-100 pb-4 mb-5">
          <div className="flex items-center gap-3">
            <ArrowLeftRight className="w-5 h-5 text-teal-600" />
            <div>
              <h2 className="text-base font-semibold text-stone-900">Exchange Rate & FX Conversion</h2>
              <p className="text-xs text-stone-500 mt-0.5">Configure live exchange rates between US Dollar and Indian Rupee.</p>
            </div>
          </div>
          <Button 
            variant="outline" 
            onClick={() => setIsConverterOpen(true)}
            className="flex items-center gap-1.5 text-xs"
          >
            <Sparkles className="w-3.5 h-3.5 text-teal-600" />
            <span>Open Converter</span>
          </Button>
        </div>

        <div className="space-y-4 max-w-lg">
          <div className="p-3.5 bg-stone-50 border border-stone-200 rounded-lg flex items-center justify-between">
            <div>
              <span className="text-xs text-stone-500 font-medium">Benchmark Rate</span>
              <p className="font-mono text-base font-bold text-stone-900 mt-0.5">
                1 USD = ₹{fxRate.toFixed(2)} INR
              </p>
            </div>
            <span className="text-[11px] text-teal-700 bg-teal-50 px-2.5 py-1 rounded-md border border-teal-200 font-medium">
              1 INR ≈ ${(1 / fxRate).toFixed(4)} USD
            </span>
          </div>

          <div>
            <label className="block text-sm font-medium text-stone-700 mb-1.5">
              Custom USD/INR Conversion Rate
            </label>
            <div className="flex items-center gap-2">
              <div className="flex-1 flex items-center gap-1 bg-white border border-stone-300 rounded-md px-3 py-2">
                <span className="text-stone-400 font-mono text-sm">₹</span>
                <input
                  type="number"
                  step="0.01"
                  value={rateInput}
                  onChange={(e) => setRateInput(e.target.value)}
                  className="w-full text-sm font-mono focus:outline-none"
                  placeholder="83.50"
                />
              </div>
              <Button
                type="button"
                variant="outline"
                onClick={() => {
                  const num = parseFloat(rateInput);
                  if (num && num > 0) setFxRate(num);
                }}
                className="text-xs"
              >
                Apply Rate
              </Button>
            </div>
            <p className="text-[11px] text-stone-400 mt-1">
              Override the standard benchmark with your negotiated bank or transfer rate.
            </p>
          </div>

          <div className="pt-2 border-t border-stone-100">
            <label className="flex items-start gap-2.5 cursor-pointer select-none">
              <input
                type="checkbox"
                checked={convertWithFx}
                onChange={(e) => setConvertWithFx(e.target.checked)}
                className="mt-0.5 rounded border-stone-300 text-teal-600 focus:ring-teal-500 h-4 w-4"
              />
              <div>
                <span className="text-xs font-semibold text-stone-800">
                  Enable Live FX Conversion on All Financial Reports
                </span>
                <p className="text-[11px] text-stone-500 mt-0.5 leading-relaxed">
                  When toggling between USD and INR, automatically convert financial amounts using the exchange rate instead of showing unadjusted nominal currency values.
                </p>
              </div>
            </label>
          </div>
        </div>
      </Card>

      {/* AI Assistant & LLM Configuration */}
      <Card className="p-6">
        <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between border-b border-stone-100 pb-4 mb-5 gap-3">
          <div className="flex items-center gap-3">
            <div className="p-2 rounded-lg bg-teal-50 text-teal-700 border border-teal-200">
              <Bot className="w-5 h-5" />
            </div>
            <div>
              <h2 className="text-base font-semibold text-stone-900">AI Assistant & Intelligence Engine</h2>
              <p className="text-xs text-stone-500 mt-0.5">
                Connect your OpenAI or Google Gemini API key to enable generalized financial Q&A, strategic CFO advice, and deep ledger reasoning.
              </p>
            </div>
          </div>
          <div>
            {aiConfig?.is_configured ? (
              <span className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-medium bg-emerald-50 text-emerald-800 border border-emerald-200">
                <CheckCircle2 className="w-3.5 h-3.5 text-emerald-600" />
                <span>Active: {aiConfig.model} ({aiConfig.provider?.toUpperCase()})</span>
              </span>
            ) : (
              <span className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-medium bg-amber-50 text-amber-800 border border-amber-200">
                <AlertCircle className="w-3.5 h-3.5 text-amber-600" />
                <span>Deterministic Fallback Mode</span>
              </span>
            )}
          </div>
        </div>

        <form onSubmit={handleSaveAiConfig} className="space-y-5 max-w-xl">
          {/* Provider Selection */}
          <div>
            <label className="block text-sm font-medium text-stone-700 mb-1.5">
              LLM Intelligence Provider
            </label>
            <div className="grid grid-cols-2 gap-3">
              <button
                type="button"
                onClick={() => {
                  setAiProvider('openai');
                  setAiModel('gpt-4o-mini');
                  setTestResult(null);
                }}
                className={`flex items-center justify-between p-3.5 rounded-lg border text-left transition-all ${
                  aiProvider === 'openai'
                    ? 'border-teal-600 bg-teal-50/50 text-teal-900 ring-1 ring-teal-600'
                    : 'border-stone-200 hover:border-stone-300 bg-white text-stone-700'
                }`}
              >
                <div>
                  <p className="font-semibold text-sm">OpenAI</p>
                  <p className="text-xs text-stone-500 mt-0.5">GPT-4o-mini & GPT-4o</p>
                </div>
                <span className="text-xs font-bold font-mono bg-stone-100 text-stone-700 px-2 py-0.5 rounded">GPT</span>
              </button>

              <button
                type="button"
                onClick={() => {
                  setAiProvider('gemini');
                  setAiModel('gemini-2.5-flash');
                  setTestResult(null);
                }}
                className={`flex items-center justify-between p-3.5 rounded-lg border text-left transition-all ${
                  aiProvider === 'gemini'
                    ? 'border-teal-600 bg-teal-50/50 text-teal-900 ring-1 ring-teal-600'
                    : 'border-stone-200 hover:border-stone-300 bg-white text-stone-700'
                }`}
              >
                <div>
                  <div className="flex items-center gap-1.5">
                    <p className="font-semibold text-sm">Google Gemini</p>
                    <span className="text-[10px] bg-emerald-100 text-emerald-800 px-1.5 py-0.2 rounded font-semibold">Free Tier</span>
                  </div>
                  <p className="text-xs text-stone-500 mt-0.5">Gemini 2.5 Flash</p>
                </div>
                <Sparkles className="w-4 h-4 text-teal-600" />
              </button>
            </div>
          </div>

          {/* Model selection */}
          <div>
            <label className="block text-sm font-medium text-stone-700 mb-1.5">
              Model Selection
            </label>
            <select
              value={aiModel}
              onChange={(e) => setAiModel(e.target.value)}
              className="w-full text-sm bg-white border border-stone-300 rounded-md px-3 py-2 text-stone-800 focus:outline-none focus:ring-1 focus:ring-teal-500 focus:border-teal-500"
            >
              {aiProvider === 'openai' ? (
                <>
                  <option value="gpt-4o-mini">gpt-4o-mini (Recommended - Fast, Economical & Accurate)</option>
                  <option value="gpt-4o">gpt-4o (Flagship - Deep Complex Reasoning)</option>
                </>
              ) : (
                <>
                  <option value="gemini-2.5-flash">gemini-2.5-flash (Recommended - Free Tier, Fast & Intelligent)</option>
                  <option value="gemini-2.0-flash">gemini-2.0-flash (High Speed Multimodal)</option>
                  <option value="gemini-2.5-pro">gemini-2.5-pro (Flagship Deep Reasoning)</option>
                </>
              )}
            </select>
          </div>

          {/* API Key Input */}
          <div>
            <div className="flex items-center justify-between mb-1.5">
              <label className="block text-sm font-medium text-stone-700">
                {aiProvider === 'openai' ? 'OpenAI Secret API Key' : 'Google Gemini API Key'}
              </label>
              <a
                href={aiProvider === 'openai' ? 'https://platform.openai.com/api-keys' : 'https://aistudio.google.com/app/apikey'}
                target="_blank"
                rel="noreferrer"
                className="text-xs text-teal-700 hover:text-teal-800 flex items-center gap-1 font-medium hover:underline"
              >
                <span>{aiProvider === 'openai' ? 'Get OpenAI Key' : 'Get Free Gemini Key'}</span>
                <ExternalLink className="w-3 h-3" />
              </a>
            </div>

            <div className="relative">
              <input
                type={showApiKey ? 'text' : 'password'}
                value={aiApiKey}
                onChange={(e) => {
                  setAiApiKey(e.target.value);
                  setTestResult(null);
                }}
                placeholder={
                  aiConfig?.masked_key
                    ? `Configured (${aiConfig.masked_key}) — Enter new key to change`
                    : aiProvider === 'openai'
                    ? 'sk-proj-...'
                    : 'AIzaSy... or AQ....'
                }
                className="w-full text-sm font-mono bg-white border border-stone-300 rounded-md px-3 py-2 pr-10 text-stone-800 focus:outline-none focus:ring-1 focus:ring-teal-500 focus:border-teal-500"
              />
              <button
                type="button"
                onClick={() => setShowApiKey(!showApiKey)}
                className="absolute right-2.5 top-2.5 text-stone-400 hover:text-stone-600"
              >
                {showApiKey ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
              </button>
            </div>

            {/* Real-time key formatting hints */}
            {aiApiKey && (
              <div className="mt-1.5 space-y-1">
                {aiProvider === 'gemini' && aiApiKey.startsWith('AIzaSyAQ.') && (
                  <p className="text-[11px] text-rose-600 font-medium flex items-center gap-1">
                    <AlertCircle className="w-3.5 h-3.5 shrink-0" />
                    <span>Accidental prefix detected: Do not prepend 'AIzaSy' to an 'AQ.' key. CashIQ will automatically clean this.</span>
                  </p>
                )}
                {aiProvider === 'gemini' && aiApiKey.includes('.') && !aiApiKey.startsWith('AQ.') && !aiApiKey.startsWith('AIzaSyAQ.') && (
                  <p className="text-[11px] text-rose-600 font-medium flex items-center gap-1">
                    <AlertCircle className="w-3.5 h-3.5 shrink-0" />
                    <span>Standard Gemini keys never contain dots. If you have an Auth Key, it should start with 'AQ.'.</span>
                  </p>
                )}
                {aiProvider === 'gemini' && aiApiKey.startsWith('AQ.') && (
                  <p className="text-[11px] text-stone-600 flex items-center gap-1">
                    <Sparkles className="w-3.5 h-3.5 text-teal-600 shrink-0" />
                    <span>Google AI Studio Auth Key (AQ.) detected.</span>
                  </p>
                )}
                {aiProvider === 'gemini' && aiApiKey.startsWith('sk-') && (
                  <p className="text-[11px] text-amber-600 font-medium flex items-center gap-1">
                    <AlertCircle className="w-3.5 h-3.5 shrink-0" />
                    <span>This looks like an OpenAI key (sk-...). Please select the "OpenAI" provider above.</span>
                  </p>
                )}
                {aiProvider === 'openai' && (aiApiKey.startsWith('AIzaSy') || aiApiKey.startsWith('AQ.')) && (
                  <p className="text-[11px] text-amber-600 font-medium flex items-center gap-1">
                    <AlertCircle className="w-3.5 h-3.5 shrink-0" />
                    <span>This looks like a Google Gemini key. Please select "Google Gemini" above.</span>
                  </p>
                )}
              </div>
            )}

            <div className="mt-2 p-2.5 bg-stone-50 border border-stone-200 rounded-md text-[11px] text-stone-600 space-y-1">
              <p className="font-semibold text-stone-700">💡 Quick Guide for Google AI Studio:</p>
              <p>
                1. Go to <a href="https://aistudio.google.com/app/apikey" target="_blank" rel="noreferrer" className="text-teal-700 underline font-medium">aistudio.google.com/app/apikey</a>.
              </p>
              <p>
                2. Click <span className="font-semibold text-stone-800">"Create API key"</span> and choose <span className="font-semibold text-stone-800">"Create API key in new project"</span> (this generates an unrestricted key that connects instantly with 0 configuration).
              </p>
              <p>
                3. Or if you already have an OpenAI key (<code className="font-mono bg-stone-200 px-1 rounded">sk-proj-...</code>), select OpenAI above and paste it.
              </p>
            </div>
          </div>

          {/* Test connection feedback */}
          {testResult && (
            <div
              className={`p-3.5 rounded-lg border text-xs flex items-start gap-2.5 ${
                testResult.success
                  ? 'bg-emerald-50/80 border-emerald-200 text-emerald-900'
                  : 'bg-rose-50/80 border-rose-200 text-rose-900'
              }`}
            >
              {testResult.success ? (
                <CheckCircle2 className="w-4 h-4 text-emerald-600 shrink-0 mt-0.5" />
              ) : (
                <AlertCircle className="w-4 h-4 text-rose-600 shrink-0 mt-0.5" />
              )}
              <div>
                <p className="font-semibold">{testResult.success ? 'Verification Successful' : 'Connection Failed'}</p>
                <p className="mt-0.5 text-[11px] leading-relaxed">
                  {testResult.success ? testResult.message : testResult.error}
                </p>
              </div>
            </div>
          )}

          {/* Buttons */}
          <div className="flex flex-wrap items-center gap-3 pt-2">
            <Button
              type="button"
              variant="outline"
              disabled={isTestingKey || (!aiApiKey && !aiConfig?.is_configured)}
              onClick={handleTestKey}
              className="text-xs flex items-center gap-1.5"
            >
              {isTestingKey ? (
                <>
                  <RefreshCw className="w-3.5 h-3.5 animate-spin text-teal-600" />
                  <span>Testing Connection...</span>
                </>
              ) : (
                <>
                  <Sparkles className="w-3.5 h-3.5 text-teal-600" />
                  <span>Test Connection</span>
                </>
              )}
            </Button>

            <Button type="submit" variant="primary" disabled={isSavingAi}>
              {isSavingAi ? 'Saving Key...' : 'Save AI Configuration'}
            </Button>

            {isAiSaved && (
              <span className="flex items-center gap-1.5 text-xs text-teal-600 font-medium">
                <Check className="w-4 h-4" /> AI configuration saved & loaded successfully!
              </span>
            )}
          </div>
        </form>
      </Card>

      {/* User Profile */}
      <Card className="p-6">
        <div className="flex items-center gap-3 border-b border-stone-100 pb-4 mb-5">
          <UserIcon className="w-5 h-5 text-teal-600" />
          <h2 className="text-base font-semibold text-stone-900">User Profile</h2>
        </div>

        <div className="space-y-4 max-w-lg">
          <Input
            label="Full Name"
            value={user?.full_name || 'Alex Vance'}
            disabled
          />
          <Input
            label="Authenticated Email"
            value={user?.email || 'demo@cashiq.io'}
            disabled
          />
          <div className="p-3 bg-stone-50 rounded-md border border-stone-200 text-xs text-stone-600 flex items-start gap-2">
            <Shield className="w-4 h-4 text-teal-600 mt-0.5 shrink-0" />
            <span>Authenticated via secure JWT bearer tokens. Multi-workspace isolation is active.</span>
          </div>
        </div>
      </Card>

      {/* Modal */}
      <CurrencyConverterModal
        isOpen={isConverterOpen}
        onClose={() => setIsConverterOpen(false)}
      />
    </div>
  );
}

export default SettingsPage;
