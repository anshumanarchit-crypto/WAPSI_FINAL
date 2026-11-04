/**
 * Formats a number to Indian currency format (e.g. ₹7.82L or ₹2.48Cr or ₹8,999)
 */
export function formatINR(amount: number, compact: boolean = false): string {
  if (compact) {
    if (amount >= 10000000) {
      return `₹${(amount / 10000000).toFixed(2)}Cr`;
    }
    if (amount >= 100000) {
      return `₹${(amount / 100000).toFixed(2)}L`;
    }
    if (amount >= 1000) {
      return `₹${(amount / 1000).toFixed(1)}k`;
    }
  }
  return new Intl.NumberFormat('en-IN', {
    style: 'currency',
    currency: 'INR',
    maximumFractionDigits: 0,
  }).format(amount);
}

/**
 * Formats percentage with sign (e.g. +37.2% or -12.4%)
 */
export function formatPercent(value: number, includeSign: boolean = true): string {
  const sign = includeSign && value > 0 ? '+' : '';
  return `${sign}${value.toFixed(1)}%`;
}

/**
 * Formats integers with comma separation
 */
export function formatNumber(value: number): string {
  return new Intl.NumberFormat('en-IN').format(value);
}
