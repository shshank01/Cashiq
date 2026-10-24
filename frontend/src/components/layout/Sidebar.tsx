import React from 'react';
import { 
  LayoutDashboard, 
  ArrowLeftRight, 
  TrendingUp, 
  Sparkles, 
  ArrowDownLeft, 
  ArrowUpRight, 
  RefreshCw, 
  FileText, 
  MessageSquare, 
  Settings, 
  LogOut,
  Building2
} from 'lucide-react';
import { Link, useLocation } from 'react-router-dom';
import { useAuth } from '../../contexts/AuthContext';
import { useWorkspace } from '../../contexts/WorkspaceContext';

const navItems = [
  { icon: LayoutDashboard, label: 'Dashboard', path: '/dashboard' },
  { icon: ArrowLeftRight, label: 'Transactions', path: '/transactions' },
  { icon: TrendingUp, label: 'Forecast', path: '/forecast' },
  { icon: Sparkles, label: 'Insights', path: '/insights' },
  { icon: ArrowDownLeft, label: 'Payables', path: '/payables' },
  { icon: ArrowUpRight, label: 'Receivables', path: '/receivables' },
  { icon: RefreshCw, label: 'Recurring', path: '/recurring' },
  { icon: FileText, label: 'Reports', path: '/reports' },
  { icon: MessageSquare, label: 'AI Assistant', path: '/assistant' },
  { icon: Settings, label: 'Settings', path: '/settings' },
];

export const Sidebar: React.FC = () => {
  const location = useLocation();
  const { user, logout } = useAuth();
  const { currentWorkspace } = useWorkspace();

  return (
    <aside className="w-64 bg-white text-stone-800 flex flex-col h-full border-r border-stone-200 select-none">
      {/* Brand Header */}
      <div className="p-6 border-b border-stone-100">
        <Link to="/dashboard" className="flex items-center gap-2.5">
          <div className="w-8 h-8 rounded-lg bg-teal-600 flex items-center justify-center text-white font-serif font-bold text-lg shadow-sm">
            Q
          </div>
          <div>
            <h1 className="text-xl font-serif font-bold tracking-tight text-stone-900 leading-none">
              Cash<span className="text-teal-700">IQ</span>
            </h1>
            <p className="text-[11px] font-sans font-medium text-stone-400 mt-1 uppercase tracking-wider">
              Financial Intelligence
            </p>
          </div>
        </Link>
      </div>

      {/* Current Workspace Pill */}
      {currentWorkspace && (
        <div className="px-4 py-3 mx-3 my-2 bg-stone-50 border border-stone-200 rounded-lg flex items-center gap-2.5">
          <Building2 className="w-4 h-4 text-teal-700 shrink-0" />
          <div className="min-w-0 flex-1">
            <p className="text-xs font-semibold text-stone-800 truncate">{currentWorkspace.name}</p>
            <p className="text-[10px] text-stone-500 font-mono">{currentWorkspace.currency || 'USD'} Account</p>
          </div>
        </div>
      )}
      
      {/* Navigation List */}
      <nav className="flex-1 px-3 py-2 space-y-1 overflow-y-auto">
        {navItems.map((item) => {
          const Icon = item.icon;
          const isActive = location.pathname === item.path || 
            (item.path === '/dashboard' && location.pathname === '/');
          return (
            <Link
              key={item.path}
              to={item.path}
              className={`flex items-center gap-3 px-3 py-2 rounded-lg text-sm font-medium transition-colors ${
                isActive 
                  ? 'bg-teal-50 text-teal-800 font-semibold border-l-2 border-teal-600' 
                  : 'text-stone-600 hover:text-stone-900 hover:bg-stone-50'
              }`}
            >
              <Icon className={`w-4 h-4 ${isActive ? 'text-teal-700' : 'text-stone-400'}`} />
              <span>{item.label}</span>
            </Link>
          );
        })}
      </nav>

      {/* User Footer */}
      <div className="p-3 border-t border-stone-200 bg-stone-50/60">
        <div className="flex items-center justify-between px-2 py-2">
          <div className="min-w-0 flex-1 mr-2">
            <p className="text-xs font-semibold text-stone-800 truncate">{user?.full_name || 'Business User'}</p>
            <p className="text-[11px] text-stone-400 truncate">{user?.email}</p>
          </div>
          <button 
            onClick={logout}
            title="Log out"
            className="p-1.5 text-stone-400 hover:text-red-600 hover:bg-red-50 rounded-md transition-colors"
          >
            <LogOut className="w-4 h-4" />
          </button>
        </div>
      </div>
    </aside>
  );
};

export default Sidebar;
