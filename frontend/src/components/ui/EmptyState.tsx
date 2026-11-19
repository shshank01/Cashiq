import React from 'react';
import { FileQuestion } from 'lucide-react';
import { Button } from './Button';

export interface EmptyStateProps {
  icon?: any;
  title: string;
  description?: string;
  message?: string;
  actionLabel?: string;
  actionText?: string;
  onAction?: () => void;
}

export const EmptyState: React.FC<EmptyStateProps> = ({ 
  icon = <FileQuestion className="w-10 h-10 text-stone-300" />, 
  title, 
  description, 
  message,
  actionLabel, 
  actionText,
  onAction 
}) => {
  const desc = description || message;
  const btnLabel = actionLabel || actionText;

  let renderedIcon: React.ReactNode = null;

  if (React.isValidElement(icon)) {
    renderedIcon = icon;
  } else if (icon && (typeof icon === 'function' || typeof icon === 'object')) {
    try {
      renderedIcon = React.createElement(icon as any, { className: 'w-10 h-10 text-stone-400' });
    } catch {
      renderedIcon = <FileQuestion className="w-10 h-10 text-stone-300" />;
    }
  } else {
    renderedIcon = <FileQuestion className="w-10 h-10 text-stone-300" />;
  }

  return (
    <div className="flex flex-col items-center justify-center py-12 px-4 text-center">
      <div className="mb-3 text-stone-400 flex items-center justify-center">
        {renderedIcon}
      </div>
      <h3 className="text-base font-semibold text-stone-900 mb-1">{title}</h3>
      {desc && (
        <p className="text-sm text-stone-500 max-w-sm mb-5">{desc}</p>
      )}
      {btnLabel && onAction && (
        <Button onClick={onAction} variant="primary">
          {btnLabel}
        </Button>
      )}
    </div>
  );
};

export default EmptyState;
