import React, { useEffect } from 'react';
import { X } from 'lucide-react';

export interface ModalProps {
  isOpen: boolean;
  onClose: () => void;
  title: string;
  children: React.ReactNode;
  footer?: React.ReactNode;
}

export const Modal: React.FC<ModalProps> = ({ isOpen, onClose, title, children, footer }) => {
  useEffect(() => {
    if (isOpen) {
      document.body.style.overflow = 'hidden';
    } else {
      document.body.style.overflow = 'unset';
    }
    return () => { document.body.style.overflow = 'unset'; };
  }, [isOpen]);

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 sm:p-0">
      <div className="fixed inset-0 bg-stone-900/40 backdrop-blur-xs transition-opacity" onClick={onClose}></div>
      
      <div className="bg-white rounded-lg border border-stone-200 shadow-lg w-full max-w-lg transform transition-all relative z-10 flex flex-col max-h-[90vh]">
        <div className="flex items-center justify-between p-5 border-b border-stone-100">
          <h3 className="text-base font-semibold text-stone-900">{title}</h3>
          <button 
            onClick={onClose}
            className="text-stone-400 hover:text-stone-600 hover:bg-stone-100 p-1 rounded-md transition-colors"
          >
            <X className="w-5 h-5" />
          </button>
        </div>
        
        <div className="p-5 overflow-y-auto flex-1">
          {children}
        </div>
        
        {footer && (
          <div className="p-4 border-t border-stone-100 bg-stone-50 rounded-b-lg flex justify-end gap-3">
            {footer}
          </div>
        )}
      </div>
    </div>
  );
};

export default Modal;
