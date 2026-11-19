import React from 'react';
import { AlertTriangle } from 'lucide-react';
import { Button } from './Button';

export interface ErrorStateProps {
  title?: string;
  message?: string;
  onRetry?: () => void;
}

export const ErrorState: React.FC<ErrorStateProps> = ({ 
  title = 'Something went wrong', 
  message = 'An unexpected error occurred.', 
  onRetry 
}) => {
  return (
    <div className="bg-red-50 border border-red-100 rounded-lg p-6 flex flex-col items-center text-center max-w-md mx-auto my-8">
      <AlertTriangle className="w-9 h-9 text-red-500 mb-2" />
      <h3 className="text-sm font-semibold text-red-900 mb-1">{title}</h3>
      <p className="text-xs text-red-700 mb-4">{message}</p>
      {onRetry && (
        <Button variant="danger" size="sm" onClick={onRetry}>
          Try Again
        </Button>
      )}
    </div>
  );
};

export default ErrorState;
