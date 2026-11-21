import { REGION_URLS, SITE_URL } from './config';
import { addressRegionUrls, parseRegionIndex, regionUrls } from './regions';

const index = (regions: unknown[], more: object = {}) => ({ schemaVersion: 1, regions, ...more });

describe('parseRegionIndex', () => {
  it('keeps the regions in the format of schedule.json, without the fields it does not know', () => {
    const parsed = parseRegionIndex(
      index(
        [
          { path: '', kind: 'settlements', files: ['schedule.json', 'addresses.json'], providers: ['nemencine', 'nemezio'] },
          {
            path: 'panevezio-ratc/',
            kind: 'settlements',
            files: ['schedule.json', 'addresses.json', 'streets.json'],
            providers: ['panevezys'],
            municipalities: ['Panevėžio r.', 'Pasvalio r.'],
            bytes: 512_000,
          },
        ],
        { generatedAt: '2026-11-22T04:30:00+00:00', mirrors: ['https://example.org/'] },
      ),
    );
    expect(parsed).toEqual({
      schemaVersion: 1,
      regions: [
        { path: '', kind: 'settlements', files: ['schedule.json', 'addresses.json'], providers: ['nemencine', 'nemezio'] },
        {
          path: 'panevezio-ratc/',
          kind: 'settlements',
          files: ['schedule.json', 'addresses.json', 'streets.json'],
          providers: ['panevezys'],
        },
      ],
    });
  });

  it('skips the regions it cannot read, and keeps the rest', () => {
    const parsed = parseRegionIndex(
      index([
        // Kauno švara's per-address format: the app reads it from kauno-r/ only (lib/kauno.ts).
        {
          path: 'kauno-r/',
          kind: 'addresses',
          files: ['schedule.json', 'points.json'],
          elderships: ['akademijos'],
          providers: ['kauno-svara'],
        },
        { path: 'naujas/', kind: 'routes', files: ['schedule.json', 'routes.json'] },
        { path: 'be-grafiko/', kind: 'settlements', files: ['addresses.json'] },
        { path: '../kitur/', kind: 'settlements', files: ['schedule.json'] },
        { path: 'https://example.org/', kind: 'settlements', files: ['schedule.json'] },
        { path: 'sratc', kind: 'settlements', files: ['schedule.json'] },
        { kind: 'settlements', files: ['schedule.json'] },
        'sratc/',
        null,
        { path: 'sratc/', kind: 'settlements', files: ['schedule.json', 7], providers: ['siauliai', { id: 'x' }] },
      ]),
    );
    expect(parsed?.regions).toEqual([{ path: 'sratc/', kind: 'settlements', files: ['schedule.json'], providers: ['siauliai'] }]);
  });

  it('reads nothing from an index of a newer format, or from something else', () => {
    const sratc = { path: 'sratc/', kind: 'settlements', files: ['schedule.json'] };
    expect(parseRegionIndex({ ...index([sratc]), schemaVersion: 2 })).toBeNull();
    expect(parseRegionIndex({ schemaVersion: '1', regions: [sratc] })).toBeNull();
    expect(parseRegionIndex({ schemaVersion: 1, regions: {} })).toBeNull();
    expect(parseRegionIndex([sratc])).toBeNull();
    expect(parseRegionIndex('<!doctype html>')).toBeNull();
    expect(parseRegionIndex(null)).toBeNull();
  });
});

describe('regionUrls', () => {
  const listed = parseRegionIndex(
    index([
      { path: '', kind: 'settlements', files: ['schedule.json', 'addresses.json'] },
      { path: 'sratc/', kind: 'settlements', files: ['schedule.json', 'addresses.json'] },
      { path: 'jurbarko-r/', kind: 'settlements', files: ['schedule.json'] },
      { path: 'panevezio-ratc/', kind: 'settlements', files: ['schedule.json', 'addresses.json'] },
      { path: 'marijampoles-r/', kind: 'settlements', files: ['schedule.json'] },
    ]),
  );

  it('are the built-in regions, then those only the index lists, and not the site root', () => {
    expect(regionUrls(listed)).toEqual([...REGION_URLS, `${SITE_URL}/panevezio-ratc`, `${SITE_URL}/marijampoles-r`]);
  });

  it('are the built-in regions without an index', () => {
    expect(regionUrls(undefined)).toEqual(REGION_URLS);
    expect(regionUrls(null)).toEqual(REGION_URLS);
  });

  it('for "Use my location", are those the index says have an addresses.json, and the built-in ones it does not list', () => {
    expect(addressRegionUrls(listed)).toEqual([
      ...REGION_URLS.filter((url) => url !== `${SITE_URL}/jurbarko-r`),
      `${SITE_URL}/panevezio-ratc`,
    ]);
    expect(addressRegionUrls(undefined)).toEqual(REGION_URLS);
  });
});
