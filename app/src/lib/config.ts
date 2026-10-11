// Forks should point these at their own GitHub Pages site (see TRADEMARKS.md).
const SITE_URL =
  process.env.EXPO_PUBLIC_SITE_URL ?? 'https://aurimasnav.github.io/atlieku-surinkimo-grafikas';

export const SCHEDULE_URL = `${SITE_URL}/schedule.json`;
/** Only downloaded when the user asks to find their address by GPS. */
export const ADDRESSES_URL = `${SITE_URL}/addresses.json`;
export const PRIVACY_URL = `${SITE_URL}/privacy/`;
export const REPOSITORY_URL = 'https://github.com/AurimasNav/atlieku-surinkimo-grafikas';
export const SOURCE_PAGE_URL =
  'https://www.nemenkom.lt/buitiniu-ir-pakuociu-atlieku-surinkimo-grafikas/';

/** Highest schedule.json schemaVersion this app version understands. */
export const SUPPORTED_SCHEMA_VERSION = 1;
