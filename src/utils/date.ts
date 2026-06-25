import dayjs from 'dayjs';
import utc from 'dayjs/plugin/utc';

dayjs.extend(utc);

/**
 * Parse date string from backend (UTC) and convert to local time
 * Backend returns dates without timezone info, but they are UTC
 */
export function parseUTCDate(dateStr: string): dayjs.Dayjs {
  if (!dateStr) return dayjs();
  // Parse as UTC by appending Z if no timezone info
  if (!dateStr.endsWith('Z') && !dateStr.includes('+') && !dateStr.includes('-', 10)) {
    return dayjs.utc(dateStr + 'Z').local();
  }
  return dayjs.utc(dateStr).local();
}

export function formatUTCDate(dateStr: string, format: string = 'YYYY-MM-DD'): string {
  if (!dateStr) return '-';
  return parseUTCDate(dateStr).format(format);
}
