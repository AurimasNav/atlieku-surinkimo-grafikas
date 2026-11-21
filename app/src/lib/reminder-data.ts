import type { Pickup } from './reminders';
import { WASTE_KINDS } from './schedule';

/** What a pickup reminder carries, so its buttons know which pickup they're about. */
export type PickupData = { type: 'pickup'; date: string; kinds: string[] };

/**
 * The pickup a reminder is about, from the content of the notification a button was pressed on.
 * In the app the content has `data`; the background task (Android, app closed) gets the raw
 * content from native code, where a scheduled notification's data is a JSON string in
 * `dataString`.
 */
export function pickupFromContent(content: { data?: unknown; dataString?: unknown } | undefined): Pickup | undefined {
  let data = content?.data as Partial<PickupData> | undefined;
  if (!data && typeof content?.dataString === 'string') {
    try {
      data = JSON.parse(content.dataString) as Partial<PickupData>;
    } catch {
      return undefined;
    }
  }
  if (data?.type !== 'pickup' || typeof data.date !== 'string' || !Array.isArray(data.kinds)) return undefined;
  return { date: data.date, kinds: WASTE_KINDS.filter((kind) => data.kinds!.includes(kind)) };
}
