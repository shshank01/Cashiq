import React from 'react';
import { ChevronLeft, ChevronRight } from 'lucide-react';
import { Button } from './Button';

export interface PaginationProps {
  currentPage: number;
  totalPages: number;
  onPageChange: (page: number) => void;
}

export const Pagination: React.FC<PaginationProps> = ({ 
  currentPage, 
  totalPages, 
  onPageChange 
}) => {
  if (totalPages <= 1) return null;

  return (
    <div className="flex items-center justify-between px-4 py-3 sm:px-6 border-t border-stone-200 mt-4">
      <div className="hidden sm:flex-1 sm:flex sm:items-center sm:justify-between">
        <div>
          <p className="text-sm text-stone-600">
            Showing page <span className="font-semibold text-stone-900">{currentPage}</span> of <span className="font-semibold text-stone-900">{totalPages}</span>
          </p>
        </div>
        <div>
          <nav className="relative z-0 inline-flex rounded-md shadow-xs -space-x-px" aria-label="Pagination">
            <Button
              variant="outline"
              size="sm"
              onClick={() => onPageChange(currentPage - 1)}
              disabled={currentPage === 1}
              className="rounded-l-md rounded-r-none border-r-0"
              icon={<ChevronLeft className="h-4 w-4" />}
            >
              Previous
            </Button>
            <div className="px-3.5 py-1.5 border border-stone-300 bg-white text-sm font-medium text-stone-700 flex items-center">
              {currentPage}
            </div>
            <Button
              variant="outline"
              size="sm"
              onClick={() => onPageChange(currentPage + 1)}
              disabled={currentPage === totalPages}
              className="rounded-r-md rounded-l-none border-l-0"
            >
              Next
              <ChevronRight className="h-4 w-4 ml-1" />
            </Button>
          </nav>
        </div>
      </div>
    </div>
  );
};

export default Pagination;
