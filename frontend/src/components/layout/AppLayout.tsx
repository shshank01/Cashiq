import React from 'react';
import { Outlet } from 'react-router-dom';
import { Sidebar } from './Sidebar';
import { TopBar } from './TopBar';
import { ErrorBoundary } from '../ui/ErrorBoundary';

export const AppLayout: React.FC<{ children?: React.ReactNode }> = ({ children }) => {
  return (
    <div className="flex h-screen bg-[#FBFBFA] overflow-hidden font-sans text-stone-900">
      <Sidebar />
      <div className="flex-1 flex flex-col h-full overflow-hidden">
        <TopBar />
        <main className="flex-1 overflow-y-auto p-6 lg:p-8">
          <div className="max-w-7xl mx-auto">
            <ErrorBoundary>
              {children || <Outlet />}
            </ErrorBoundary>
          </div>
        </main>
      </div>
    </div>
  );
};

export default AppLayout;
