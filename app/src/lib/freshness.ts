import { KAUNO_SOURCE_PAGE_URL, SOURCE_PAGE_URL } from './config';
import { isCustomArea, isWebPage, type Place, type Resolved } from './resolve';
import { kaunoKey } from './kauno';
import { personalsOf, type ScheduleData } from './schedule';

/** The daily job rebuilds every source; a week without a new build means its source broke. */
export const STALE_DATA_DAYS = 7;
/** The app checks on every start and in the background; days without a check mean it can't. */
export const CHECK_OVERDUE_DAYS = 3;

const DAY = 86_400_000;

/** A company whose schedules the user relies on, and since when they couldn't be updated. */
export type StaleSource = { name: string; url: string; since: string };

const older = (iso: string | undefined, days: number, now: Date) =>
  Boolean(iso) && now.getTime() - Date.parse(iso!) > days * DAY;

/**
 * The companies behind the user's schedules whose data hasn't been rebuilt for a week. Each
 * region file lists its companies with their names and official pages (`providers`), so a new
 * one needs nothing here.
 */
export function staleSources(data: ScheduleData | null, place: Place | null, resolved: Resolved, now: Date): StaleSource[] {
  if (!data) return [];
  if (place?.kauno) {
    // Kauno r. and Kaišiadorių r.: one file, built from one source.
    const key = kaunoKey(place.kauno);
    const since = personalsOf(data).find((p) => p.key === key)?.generatedAt;
    return older(since, STALE_DATA_DAYS, now) ? [{ name: 'UAB „Kauno švara“', url: KAUNO_SOURCE_PAGE_URL, since: since! }] : [];
  }
  // Rows without a provider are Nemenčinės komunalininkas', as in data published before.
  const ids = new Set(resolved.areas.filter((area) => !isCustomArea(area)).map((area) => area.provider ?? 'nemencine'));
  return [...ids].flatMap((id): StaleSource[] => {
    const provider = data.providers?.find((p) => p.id === id);
    // A company the data doesn't list: nothing to say when, or whose, it was built.
    if (!provider && id !== 'nemencine') return [];
    const since = provider ? provider.generatedAt : data.generatedAt;
    if (!older(since, STALE_DATA_DAYS, now)) return [];
    const url = provider && isWebPage(provider.url) ? provider.url : SOURCE_PAGE_URL;
    return [{ name: provider?.name ?? 'UAB „Nemenčinės komunalininkas“', url, since: since! }];
  });
}

/** Whether the app hasn't managed to check for a new schedule for days. */
export const checkOverdue = (lastChecked: string | undefined, now: Date) => older(lastChecked, CHECK_OVERDUE_DAYS, now);
