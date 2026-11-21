// Forks should point these at their own GitHub Pages site (see TRADEMARKS.md).
export const SITE_URL =
  process.env.EXPO_PUBLIC_SITE_URL ?? 'https://aurimasnav.github.io/atlieku-surinkimo-grafikas';

export const SCHEDULE_URL = `${SITE_URL}/schedule.json`;
/**
 * The region folders the site publishes (pipeline/src/schedule_pipeline/regions.py). The app
 * downloads those in the format of schedule.json next to REGION_URLS, so a new folder needs no
 * app update (lib/regions.ts).
 */
export const REGIONS_URL = `${SITE_URL}/regions.json`;
/** Only downloaded when the user asks to find their address by GPS. */
export const ADDRESSES_URL = `${SITE_URL}/addresses.json`;
/**
 * Kauno r. and Kaišiadorių r. (UAB „Kauno švara“): schedule.json and addresses/<eldership>.json.
 * The folder is named after Kauno r., which came first.
 */
export const KAUNO_URL = `${SITE_URL}/kauno-r`;
/** Only downloaded when the user asks to find their address by GPS. */
export const KAUNO_POINTS_URL = `${KAUNO_URL}/points.json`;
export const KAUNO_SOURCE_PAGE_URL = 'https://grafikai.svara.lt/';
/**
 * Glass and packaging in Kauno r. are emptied by UAB „Ekonovus“; its schedules are only on its
 * site. The company is also licensed to collect glass packaging in Kaišiadorių r., so the link is
 * shown for every address of the Kauno švara data.
 */
export const EKONOVUS_SCHEDULES_URL = 'https://www.ekonovus.lt/aptarnavimo-grafikai/';
/**
 * Regions published as their own files in the format of schedule.json: <url>/schedule.json and,
 * for "use my location", <url>/addresses.json. Each file lists its companies (`providers`), with
 * their names and official schedule pages:
 * - mazeikiu-r: Mažeikių r., Telšių r., Plungės r. and Rietavo sav., from the files of the regional
 *   waste centre of Telšiai county (UAB „Telšių regiono atliekų tvarkymo centras“), a provider per
 *   municipality;
 * - klaipedos-r: Klaipėdos r., from the spreadsheet of VšĮ „Gargždų švara“;
 * - jurbarko-r: Jurbarko r., Tauragės r., Šilalės r. and Pagėgių sav., from the PDFs of the
 *   regional waste centre of Tauragė county (UAB „Tauragės regiono atliekų tvarkymo centras“), a
 *   provider per municipality;
 * - sratc: Šiaulių r., Akmenės r., Joniškio r., Kelmės r. and Pakruojo r., and Radviliškio r. as a
 *   provider of its own, from the PDFs of the regional waste centre of Šiauliai county (UAB
 *   „Šiaulių regiono atliekų tvarkymo centras“);
 * - alytaus-ratc: Alytaus r., Prienų r., Lazdijų r., Varėnos r., Druskininkų sav. and Birštono
 *   sav., from the PDFs of the regional waste centre of Alytus county (UAB „Alytaus regiono atliekų
 *   tvarkymo centras“).
 *
 * Built in, so the app finds them without regions.json (offline, or before it was published);
 * folders added later come from regions.json only: panevezio-ratc (Pasvalio r., Rokiškio r.,
 * Biržų r., and the packaging and glass of Panevėžio r.) and maatc (Marijampolės sav.,
 * Vilkaviškio r., Kalvarijos sav., Kazlų Rūdos sav. and Šakių r.).
 */
export const REGION_URLS = ['mazeikiu-r', 'klaipedos-r', 'jurbarko-r', 'sratc', 'alytaus-ratc'].map(
  (folder) => `${SITE_URL}/${folder}`,
);
export const PRIVACY_URL = `${SITE_URL}/privacy/`;
export const REPOSITORY_URL = 'https://github.com/AurimasNav/atlieku-surinkimo-grafikas';
/**
 * UAB „Nemenčinės komunalininkas“: places in schedule.json without a `provider`. The pages of the
 * other companies come with the data (`providers`).
 */
export const SOURCE_PAGE_URL =
  'https://www.nemenkom.lt/buitiniu-ir-pakuociu-atlieku-surinkimo-grafikas/';
/**
 * The companies whose schedules the app shows or links to: the publishers, and the companies
 * that collect the waste where the schedules name them. Named in the disclaimer in settings; add a
 * new one here, not to each translation.
 */
export const COMPANIES = [
  'UAB „Nemenčinės komunalininkas“',
  'UAB „Nemėžio komunalininkas“',
  'UAB „Kauno švara“',
  'UAB „Ekonovus“',
  'UAB „Telšių regiono atliekų tvarkymo centras“',
  'UAB „Ecoservice“',
  'UAB „Virginijus ir Ko“',
  'VšĮ „Gargždų švara“',
  'UAB „Tauragės regiono atliekų tvarkymo centras“',
  'UAB „Jurbarko komunalininkas“',
  'UAB „Dunokai“',
  'UAB „Šiaulių regiono atliekų tvarkymo centras“',
  'UAB „Kuršėnų komunalinis ūkis“',
  'UAB „Pakruojo komunalinis ūkis“',
  'UAB „Svarinta“',
  'UAB „Alytaus regiono atliekų tvarkymo centras“',
  'UAB „Panevėžio regiono atliekų tvarkymo centras“',
  'UAB „Marijampolės apskrities atliekų tvarkymo centras“',
];

/** Highest schedule.json schemaVersion this app version understands. */
export const SUPPORTED_SCHEMA_VERSION = 1;
/** Highest regions.json schemaVersion this app version understands; a newer index is ignored. */
export const SUPPORTED_REGIONS_SCHEMA_VERSION = 1;
