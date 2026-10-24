import { format, parseISO } from 'date-fns';

export const DEFAULT_USD_TO_INR = 83.50;

export function getCurrencySymbol(currency: string = 'USD'): string {
  const norm = (currency || 'USD').toUpperCase();
  if (norm === 'INR') return '₹';
  if (norm === 'EUR') return '€';
  if (norm === 'GBP') return '£';
  return '$';
}

/**
 * Converts minor integer units (cents/paise) between currencies using the given USD/INR exchange rate.
 */
export function convertMoneyMinor(
  amountMinor: number | undefined | null,
  fromCurrency: string = 'USD',
  toCurrency: string = 'USD',
  fxRate: number = DEFAULT_USD_TO_INR
): number {
  const minor = typeof amountMinor === 'number' && !isNaN(amountMinor) ? amountMinor : 0;
  const fromNorm = (fromCurrency || 'USD').toUpperCase();
  const toNorm = (toCurrency || 'USD').toUpperCase();
  const rate = fxRate > 0 ? fxRate : DEFAULT_USD_TO_INR;

  if (fromNorm === toNorm) {
    return minor;
  }
  if (fromNorm === 'USD' && toNorm === 'INR') {
    return Math.round(minor * rate);
  }
  if (fromNorm === 'INR' && toNorm === 'USD') {
    return Math.round(minor / rate);
  }
  return minor;
}

/**
 * Formats minor units into localized currency strings with standard fractional digits.
 */
export function formatMoney(amountMinor: number | undefined | null, currency: string = 'USD'): string {
  const validMinor = typeof amountMinor === 'number' && !isNaN(amountMinor) ? amountMinor : 0;
  const amount = validMinor / 100;
  const norm = (currency || 'USD').toUpperCase();
  const locale = norm === 'INR' ? 'en-IN' : 'en-US';

  try {
    return new Intl.NumberFormat(locale, {
      style: 'currency',
      currency: norm,
      minimumFractionDigits: 2,
      maximumFractionDigits: 2,
    }).format(amount);
  } catch {
    const symbol = getCurrencySymbol(norm);
    return `${symbol}${amount.toLocaleString(locale, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
  }
}

/**
 * Converts from base ledger currency to user's selected display currency and formats.
 */
export function convertAndFormatMoney(
  amountMinor: number | undefined | null,
  baseCurrency: string = 'USD',
  displayCurrency: string = 'USD',
  applyFx: boolean = true,
  fxRate: number = DEFAULT_USD_TO_INR
): string {
  if (!applyFx || (baseCurrency || 'USD').toUpperCase() === (displayCurrency || 'USD').toUpperCase()) {
    return formatMoney(amountMinor, displayCurrency);
  }
  const convertedMinor = convertMoneyMinor(amountMinor, baseCurrency, displayCurrency, fxRate);
  return formatMoney(convertedMinor, displayCurrency);
}

export function formatDate(dateString: string): string {
  if (!dateString) return '';
  return format(parseISO(dateString), 'MMM d, yyyy');
}

export function formatDateTime(dateString: string): string {
  if (!dateString) return '';
  return format(parseISO(dateString), 'MMM d, yyyy h:mm a');
}
