import type { Selections } from '@/store/settings';

import { type Area, isCurrent, type ScheduleData, WASTE_KINDS, type WasteKind } from './schedule';

export type SelectionStatus = {
  /** Areas the user picked that exist in the current data. */
  areas: Area[];
  /**
   * Kinds whose picked area is gone or outdated in a newer schedule, so the user must pick
   * again. An area that merely ran out of dates because no new schedule is out yet is fine.
   */
  missing: WasteKind[];
};

export function resolveSelections(
  data: ScheduleData | null,
  selections: Selections,
  today: string,
): SelectionStatus {
  const byId = new Map(data?.areas.map((area) => [area.id, area]));
  const areas: Area[] = [];
  const missing: WasteKind[] = [];
  for (const kind of WASTE_KINDS) {
    const id = selections[kind];
    if (!id) continue;
    const area = byId.get(id);
    const newerScheduleExists = (data?.coverage[kind]?.to ?? '') >= today;
    if (area && (isCurrent(area, today) || !newerScheduleExists)) areas.push(area);
    else if (data) missing.push(kind);
  }
  return { areas, missing };
}
