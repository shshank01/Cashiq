import React from 'react';
import { Badge, BadgeVariant } from './Badge';

export type StatusType = string;

export interface StatusBadgeProps {
  status: StatusType;
  children?: React.ReactNode;
}

export const StatusBadge: React.FC<StatusBadgeProps> = ({ status, children }) => {
  const normalizedStatus = (status || '').toLowerCase();

  const getVariant = (): BadgeVariant => {
    switch (normalizedStatus) {
      case 'paid':
      case 'active':
      case 'completed':
      case 'forecast':
        return 'success';
      case 'pending':
      case 'draft':
      case 'processing':
      case 'projected':
        return 'warning';
      case 'overdue':
      case 'cancelled':
      case 'failed':
      case 'critical':
        return 'error';
      case 'estimated':
      case 'info':
        return 'info';
      default:
        return 'default';
    }
  };

  return (
    <Badge variant={getVariant()} className="uppercase tracking-wider text-[10px]">
      {children || status}
    </Badge>
  );
};

export default StatusBadge;
