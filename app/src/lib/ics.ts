import type { Pickup, ReminderTime } from './reminders';
import type { WasteKind } from './schedule';

/**
 * An iCalendar file (RFC 5545) of pickups, to import into any calendar app: one all-day event
 * per pickup day, with alarms at the user's reminder times.
 */
export function buildIcs({
  pickups,
  kindName,
  timesFor,
  description,
  now = new Date(),
}: {
  pickups: Pickup[];
  /** Waste type name in the app's language. */
  kindName: (kind: WasteKind) => string;
  /** The reminders of a waste type; they become the events' alarms. */
  timesFor: (kind: WasteKind) => ReminderTime[];
  description: string;
  now?: Date;
}): string {
  const stamp = now.toISOString().replace(/[-:]/g, '').replace(/\.\d{3}/, '');
  const lines = [
    'BEGIN:VCALENDAR',
    'VERSION:2.0',
    'PRODID:-//Siuksliaveze//Pickups//EN',
    'CALSCALE:GREGORIAN',
    'METHOD:PUBLISH',
  ];
  for (const pickup of pickups) {
    const day = pickup.date.replace(/-/g, '');
    const times = uniqueTimes(pickup.kinds.flatMap(timesFor));
    lines.push(
      'BEGIN:VEVENT',
      // Stable per day and waste types, so importing again updates rather than duplicates.
      `UID:${day}-${pickup.kinds.join('-')}@siuksliaveze`,
      `DTSTAMP:${stamp}`,
      `DTSTART;VALUE=DATE:${day}`,
      `DTEND;VALUE=DATE:${nextDay(pickup.date)}`,
      `SUMMARY:${escapeText(pickup.kinds.map(kindName).join(', '))}`,
      `DESCRIPTION:${escapeText(description)}`,
      'TRANSP:TRANSPARENT',
    );
    for (const time of times) {
      lines.push('BEGIN:VALARM', 'ACTION:DISPLAY', `DESCRIPTION:${escapeText(pickup.kinds.map(kindName).join(', '))}`);
      lines.push(`TRIGGER:${alarmOffset(time)}`, 'END:VALARM');
    }
    lines.push('END:VEVENT');
  }
  lines.push('END:VCALENDAR');
  return lines.map(fold).join('\r\n') + '\r\n';
}

/** An all-day event starts at midnight: the evening before at 19:00 is -PT5H. */
export function alarmOffset(time: ReminderTime): string {
  const minutes = time.hour * 60 + time.minute - time.daysBefore * 24 * 60;
  const sign = minutes < 0 ? '-' : '';
  const abs = Math.abs(minutes);
  const hours = Math.floor(abs / 60);
  const rest = abs % 60;
  return `${sign}PT${hours ? `${hours}H` : ''}${rest || !hours ? `${rest}M` : ''}`;
}

function uniqueTimes(times: ReminderTime[]): ReminderTime[] {
  return [...new Map(times.map((time) => [`${time.daysBefore}|${time.hour}|${time.minute}`, time])).values()];
}

function nextDay(iso: string): string {
  const [year, month, day] = iso.split('-').map(Number);
  const date = new Date(Date.UTC(year, month - 1, day + 1));
  return date.toISOString().slice(0, 10).replace(/-/g, '');
}

function escapeText(text: string): string {
  return text.replace(/\\/g, '\\\\').replace(/;/g, '\\;').replace(/,/g, '\\,').replace(/\r?\n/g, '\\n');
}

/** Lines longer than 75 octets continue on the next line after a space (RFC 5545, 3.1). */
function fold(line: string): string {
  const bytes = new TextEncoder().encode(line);
  if (bytes.length <= 75) return line;
  const parts: string[] = [];
  let current = '';
  let size = 0;
  for (const char of line) {
    const length = new TextEncoder().encode(char).length;
    const limit = parts.length ? 74 : 75;
    if (size + length > limit) {
      parts.push(current);
      current = '';
      size = 0;
    }
    current += char;
    size += length;
  }
  parts.push(current);
  return parts.join('\r\n ');
}
