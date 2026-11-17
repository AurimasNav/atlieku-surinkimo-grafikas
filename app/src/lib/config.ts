// Forks should point these at their own GitHub Pages site (see TRADEMARKS.md).
const SITE_URL =
  process.env.EXPO_PUBLIC_SITE_URL ?? 'https://aurimasnav.github.io/atlieku-surinkimo-grafikas';

export const SCHEDULE_URL = `${SITE_URL}/schedule.json`;
/** Only downloaded when the user asks to find their address by GPS. */
export const ADDRESSES_URL = `${SITE_URL}/addresses.json`;
/** Kauno r. (UAB „Kauno švara“): schedule.json and addresses/<eldership>.json. */
export const KAUNO_URL = `${SITE_URL}/kauno-r`;
/** Only downloaded when the user asks to find their address by GPS. */
export const KAUNO_POINTS_URL = `${KAUNO_URL}/points.json`;
export const KAUNO_SOURCE_PAGE_URL = 'https://grafikai.svara.lt/';
/** Glass and packaging in Kauno r. are emptied by UAB „Ekonovus“; its schedules are only on its site. */
export const EKONOVUS_SCHEDULES_URL = 'https://www.ekonovus.lt/aptarnavimo-grafikai/';
/**
 * Regions published as their own files in the format of schedule.json: <url>/schedule.json and,
 * for "use my location", <url>/addresses.json. Mažeikių r., from the files of the regional
 * waste centre (UAB „Telšių regiono atliekų tvarkymo centras“).
 */
export const REGION_URLS = [`${SITE_URL}/mazeikiu-r`];
export const PRIVACY_URL = `${SITE_URL}/privacy/`;
export const REPOSITORY_URL = 'https://github.com/AurimasNav/atlieku-surinkimo-grafikas';
/**
 * UAB „Nemenčinės komunalininkas“: places in schedule.json without a `provider`. The pages of the
 * other companies come with the data (`providers`).
 */
export const SOURCE_PAGE_URL =
  'https://www.nemenkom.lt/buitiniu-ir-pakuociu-atlieku-surinkimo-grafikas/';

/** Highest schedule.json schemaVersion this app version understands. */
export const SUPPORTED_SCHEMA_VERSION = 1;
