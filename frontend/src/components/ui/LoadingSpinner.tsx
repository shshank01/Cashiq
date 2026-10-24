import React from 'react';
import { Loader2 } from 'lucide-react';

export interface LoadingSpinnerProps {
  size?: 'sm' | 'md' | 'lg';
  className?: string;
  fullScreen?: boolean;
}

export const LoadingSpinner: React.FC<LoadingSpinnerProps> = ({ 
  size = 'md', 
  className = '',
  fullScreen = false
}) => {
  const sizes = {
    sm: 'w-4 h-4',
    md: 'w-8 h-8',
    lg: 'w-12 h-12'
  };

  const spinner = (
    <Loader2 className={`animate-spin text-teal-600 ${sizes[size]} ${className}`} />
  );

  if (fullScreen) {
    return (
      <div className="fixed inset-0 flex items-center justify-center bg-stone-50/80 backdrop-blur-xs z-50">
        {spinner}
      </div>
    );
  }

  return (
    <div className="flex items-center justify-center p-4 w-full h-full min-h-[100px]">
      {spinner}
    </div>
  );
};

export default LoadingSpinner;
