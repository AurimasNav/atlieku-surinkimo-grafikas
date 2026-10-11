import type { Href } from 'expo-router';

import { toIsoDate } from './dates';
import { pendingKinds, type Place, resolvePlace } from './resolve';
import type { ScheduleData } from './schedule';

/** Where setup goes next after the user picks a location, a street or a row. */
export function nextSetupStep(data: ScheduleData | null, place: Place | null): Href {
  const resolved = resolvePlace(data, place, toIsoDate(new Date()));
  // street === undefined: not asked yet; '' means "my street isn't listed".
  if (resolved.location?.streets && place?.street === undefined) return '/setup/street';
  const kind = pendingKinds(resolved)[0];
  if (kind) return { pathname: '/setup/choose/[kind]', params: { kind } };
  return '/setup/done';
}
