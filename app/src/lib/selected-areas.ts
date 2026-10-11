import type { Selections } from '@/store/settings';

import { type Area, type ScheduleData, WASTE_KINDS, type WasteKind } from './schedule';

export type SelectionStatus = {
  /** Areas the user picked that exist in the current data. */
  areas: Area[];
  /** Kinds whose picked area disappeared in a newer schedule, so the user must pick again. */
  missing: WasteKind[];
};

export function resolveSelections(data: ScheduleData | null, selections: Selections): SelectionStatus {
  const byId = new Map(data?.areas.map((area) => [area.id, area]));
  const areas: Area[] = [];
  const missing: WasteKind[] = [];
  for (const kind of WASTE_KINDS) {
    const id = selections[kind];
    if (!id) continue;
    const area = byId.get(id);
    if (area) areas.push(area);
    else if (data) missing.push(kind);
  }
  return { areas, missing };
}
