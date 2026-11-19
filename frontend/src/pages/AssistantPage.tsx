import React, { useState, useRef, useEffect } from 'react';
import { Link } from 'react-router-dom';
import { useWorkspace } from '../contexts/WorkspaceContext';
import { assistantApi, AssistantConfig } from '../api/assistant';
import { Send, Bot, User, Loader2, Sparkles, Database, ShieldCheck, Settings as SettingsIcon, AlertCircle } from 'lucide-react';
import Button from '../components/ui/Button';
import Input from '../components/ui/Input';

interface Message {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  tools_executed?: string[];
  model_used?: string;
  provider?: string;
}

const PRESET_QUERIES = [
  "Why did my expenses increase this month?",
  "What was my biggest expense?",
  "What is EBITDA and how does it relate to cash flow?",
  "What payments are due next month?",
  "What is my expected cash runway and position?",
  "Give me an executive dashboard summary"
];

export function AssistantPage() {
  const { currentWorkspace } = useWorkspace();
  const [messages, setMessages] = useState<Message[]>([
    {
      id: 'welcome',
      role: 'assistant',
      content: `Hello! I am your CashIQ Financial Assistant for **${currentWorkspace?.name || 'your workspace'}**.\n\nI combine verified workspace records with financial intelligence to answer questions about your numbers, forecasts, or general financial strategy. Ask any question or click a prompt below:`
    }
  ]);
  const [input, setInput] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [conversationId, setConversationId] = useState<string | undefined>(undefined);
  const [aiConfig, setAiConfig] = useState<AssistantConfig | null>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    assistantApi.getConfig().then(setAiConfig).catch(() => {});
  }, []);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages]);

  const handleSend = async (queryText: string) => {
    const trimmed = queryText.trim();
    if (!trimmed || !currentWorkspace || isLoading) return;

    const userMessage: Message = { id: Date.now().toString(), role: 'user', content: trimmed };
    setMessages(prev => [...prev, userMessage]);
    setInput('');
    setIsLoading(true);

    try {
      const response = await assistantApi.chat(currentWorkspace.id, {
        message: trimmed,
        conversation_id: conversationId
      });
      
      if (response.conversation_id) {
        setConversationId(response.conversation_id);
      }
      
      const assistantMessage: Message = { 
        id: (Date.now() + 1).toString(), 
        role: 'assistant', 
        content: response.response,
        tools_executed: (response as any).tools_executed || [],
        model_used: (response as any).model_used,
        provider: (response as any).provider
      };
      setMessages(prev => [...prev, assistantMessage]);
    } catch (err: any) {
      const errorMessage: Message = {
        id: (Date.now() + 1).toString(),
        role: 'assistant',
        content: `Error retrieving financial data: ${err.message || 'Service temporarily unavailable.'}`
      };
      setMessages(prev => [...prev, errorMessage]);
    } finally {
      setIsLoading(false);
    }
  };

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    handleSend(input);
  };

  if (!currentWorkspace) return null;

  return (
    <div className="flex flex-col h-[calc(100vh-7.5rem)] space-y-4">
      {/* Header bar */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 border-b border-stone-200 pb-4">
        <div>
          <h1 className="text-2xl font-serif font-bold text-stone-900 tracking-tight flex items-center gap-2">
            AI Financial Assistant
          </h1>
          <p className="text-xs text-stone-500 font-sans mt-0.5">
            Controlled retrieval across verified accounts, payables, receivables, and forecasts for <span className="font-semibold text-stone-700">{currentWorkspace.name}</span>.
          </p>
        </div>
        <div className="flex items-center gap-2">
          {aiConfig?.is_configured ? (
            <Link
              to="/settings"
              className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium bg-emerald-50 text-emerald-800 border border-emerald-200 hover:bg-emerald-100 transition-colors"
            >
              <Sparkles className="w-3.5 h-3.5 text-emerald-600" />
              <span>Active: {aiConfig.model}</span>
              <SettingsIcon className="w-3 h-3 text-emerald-600 ml-0.5" />
            </Link>
          ) : (
            <Link
              to="/settings"
              className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium bg-amber-50 text-amber-800 border border-amber-200 hover:bg-amber-100 transition-colors"
            >
              <Bot className="w-3.5 h-3.5 text-amber-600" />
              <span>Configure AI Key</span>
              <SettingsIcon className="w-3 h-3 text-amber-600 ml-0.5" />
            </Link>
          )}

          <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium bg-teal-50 text-teal-800 border border-teal-200">
            <ShieldCheck className="w-3.5 h-3.5 text-teal-600" />
            Verified Tool Grounding
          </span>
        </div>
      </div>

      {/* Chat Messages scroll area */}
      <div className="flex-1 overflow-y-auto px-4 py-3 space-y-4 bg-white border border-stone-200 rounded-xl shadow-xs">
        {!aiConfig?.is_configured && (
          <div className="p-3 bg-amber-50/70 border border-amber-200/80 rounded-lg text-xs text-amber-900 flex items-center justify-between gap-3">
            <div className="flex items-center gap-2">
              <AlertCircle className="w-4 h-4 text-amber-600 shrink-0" />
              <span>
                Running in deterministic fallback mode. To answer all general financial queries and strategic analysis, configure your API key.
              </span>
            </div>
            <Link
              to="/settings"
              className="px-2.5 py-1 bg-white border border-amber-300 rounded text-amber-800 font-medium hover:bg-amber-50 text-xs shrink-0 inline-flex items-center gap-1"
            >
              <span>Setup Key</span>
            </Link>
          </div>
        )}
        {messages.map((msg) => (
          <div key={msg.id} className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}>
            <div className={`flex items-start gap-3 max-w-[85%] ${msg.role === 'user' ? 'flex-row-reverse' : 'flex-row'}`}>
              <div className={`p-2 rounded-lg shrink-0 ${msg.role === 'user' ? 'bg-stone-800 text-white' : 'bg-teal-50 text-teal-700 border border-teal-200'}`}>
                {msg.role === 'user' ? <User className="h-4 w-4" /> : <Bot className="h-4 w-4" />}
              </div>
              <div className={`p-4 rounded-xl text-xs sm:text-sm leading-relaxed whitespace-pre-wrap ${
                msg.role === 'user' 
                  ? 'bg-stone-900 text-white font-sans' 
                  : 'bg-stone-50 border border-stone-200 text-stone-800 font-sans'
              }`}>
                {msg.content}

                {msg.tools_executed && msg.tools_executed.length > 0 && (
                  <div className="mt-3 pt-2.5 border-t border-stone-200/70 flex flex-wrap items-center gap-1.5">
                    <span className="text-[10px] text-stone-500 font-medium uppercase tracking-wider flex items-center gap-1">
                      <Database className="w-3 h-3 text-teal-700" />
                      Tools Executed:
                    </span>
                    {msg.tools_executed.map((tool, idx) => (
                      <span key={idx} className="px-2 py-0.5 bg-white border border-stone-200 rounded text-[11px] font-mono text-teal-800">
                        {tool}
                      </span>
                    ))}
                    {msg.model_used && (
                      <span className="ml-auto px-2 py-0.5 bg-stone-100 rounded text-[10px] font-mono text-stone-500">
                        {msg.model_used}
                      </span>
                    )}
                  </div>
                )}
              </div>
            </div>
          </div>
        ))}

        {isLoading && (
          <div className="flex justify-start">
            <div className="flex items-start gap-3">
              <div className="p-2 rounded-lg bg-teal-50 text-teal-700 border border-teal-200">
                <Bot className="h-4 w-4" />
              </div>
              <div className="p-3.5 rounded-xl bg-stone-50 border border-stone-200 text-stone-600 text-xs sm:text-sm flex items-center gap-2.5">
                <Loader2 className="h-4 w-4 animate-spin text-teal-600" />
                <span>Executing controlled financial tools & querying verified ledger...</span>
              </div>
            </div>
          </div>
        )}
        <div ref={messagesEndRef} />
      </div>

      {/* Preset Queries Pills */}
      <div className="flex items-center gap-2 overflow-x-auto pb-1 pt-0.5 no-scrollbar">
        <span className="text-xs font-medium text-stone-400 shrink-0 flex items-center gap-1">
          <Sparkles className="w-3.5 h-3.5 text-teal-600" /> Suggested:
        </span>
        {PRESET_QUERIES.map((preset, idx) => (
          <button
            key={idx}
            onClick={() => handleSend(preset)}
            disabled={isLoading}
            className="px-2.5 py-1 bg-white hover:bg-stone-100 border border-stone-200 rounded-lg text-xs text-stone-700 whitespace-nowrap transition-colors shrink-0 disabled:opacity-50"
          >
            {preset}
          </button>
        ))}
      </div>

      {/* Input Form */}
      <div className="p-3 bg-white border border-stone-200 rounded-xl shadow-xs">
        <form onSubmit={handleSubmit} className="flex gap-2">
          <Input
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder="Ask about burn rate, payables, category spend, cash position..."
            className="flex-1 text-xs sm:text-sm"
            disabled={isLoading}
          />
          <Button type="submit" disabled={isLoading || !input.trim()} icon={<Send className="h-4 w-4" />}>
            Ask Assistant
          </Button>
        </form>
      </div>
    </div>
  );
}

export default AssistantPage;
