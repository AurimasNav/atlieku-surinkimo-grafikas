import {
  advise,
  availableKinds,
  GUIDE_CATEGORIES,
  GUIDE_LANGUAGES,
  guideItem,
  guideLanguage,
  isKind,
  locationsUrl,
  normalizeGuide,
  OFF_CURB,
  POPULAR,
  REGIONS,
  regionOf,
  searchGuide,
} from './guide';
import { GUIDE_ITEMS } from './guide-items';
import { kaunoKey } from './kauno';
import { type Place, type Resolved, resolvePlace } from './resolve';
import type { Area, Location, ScheduleData, WasteKind } from './schedule';

const item = (id: string) => {
  const found = guideItem(id);
  if (!found) throw new Error(`no guide item ${id}`);
  return found;
};
const ids = (items: { id: string }[]) => items.map((i) => i.id);
const kinds = (...list: WasteKind[]) => new Set<WasteKind>(list);

describe('normalizeGuide', () => {
  it('ignores case and Lithuanian, Polish and Russian diacritics', () => {
    expect(normalizeGuide('Picos DĖŽUTĖ')).toBe('picos dezute');
    expect(normalizeGuide('Łupiny orzechów, żółć')).toBe('lupiny orzechow zolc');
    expect(normalizeGuide('Ёлка, йогурт')).toBe(normalizeGuide('елка иогурт'));
  });

  it('turns punctuation into single spaces', () => {
    expect(normalizeGuide('  el. cigaretė / e-cigarette ')).toBe('el cigarete e cigarette');
  });
});

describe('searchGuide', () => {
  it('finds names without diacritics', () => {
    expect(ids(searchGuide('dezute', 'lt'))).toEqual(expect.arrayContaining(['pizza-box', 'egg-cartons']));
    expect(ids(searchGuide('picos dezute', 'lt'))[0]).toBe('pizza-box');
    expect(ids(searchGuide('lupiny', 'pl'))[0]).toBe('nutshells');
  });

  it('puts exact and leading matches first, ignoring case', () => {
    expect(ids(searchGuide('Pizza box', 'en'))[0]).toBe('pizza-box');
    expect(ids(searchGuide('BATTERIES', 'en'))[0]).toBe('batteries');
    expect(ids(searchGuide('TETRA', 'en'))[0]).toBe('tetra-pak');
    expect(ids(searchGuide('батарейки', 'ru'))[0]).toBe('batteries');
    expect(ids(searchGuide('baterie', 'pl'))[0]).toBe('batteries');
    expect(ids(searchGuide('yogurt cup', 'en'))[0]).toBe('yogurt-cup');
    expect(ids(searchGuide('light bulb', 'en'))[0]).toBe('light-bulbs');
  });

  it('matches every word, in any order and by word start', () => {
    expect(ids(searchGuide('box pizza', 'en'))).toContain('pizza-box');
    expect(ids(searchGuide('pizza battery', 'en'))).toEqual([]);
  });

  it('searches every language when the app language finds nothing', () => {
    expect(ids(searchGuide('battery', 'lt'))[0]).toBe('batteries');
    expect(ids(searchGuide('baterijos', 'en'))[0]).toBe('batteries');
  });

  it('lists a category alphabetically, filters search by it, and returns nothing for no query', () => {
    const garden = searchGuide('', 'en', 'garden');
    expect(garden.length).toBeGreaterThan(3);
    expect(garden.every((i) => i.category === 'garden')).toBe(true);
    expect(garden.map((i) => i.names.en[0])).toEqual([...garden.map((i) => i.names.en[0])].sort((a, b) => a.localeCompare(b)));
    expect(ids(searchGuide('box', 'en', 'paper'))).not.toContain('food-trays');
    expect(searchGuide('  ', 'en')).toEqual([]);
  });
});

describe('guide data', () => {
  it('has enough items, with unique ids and names in every language', () => {
    expect(GUIDE_ITEMS.length).toBeGreaterThanOrEqual(80);
    expect(new Set(ids(GUIDE_ITEMS)).size).toBe(GUIDE_ITEMS.length);
    for (const entry of GUIDE_ITEMS) {
      for (const language of GUIDE_LANGUAGES) {
        expect([entry.id, language, entry.names[language]?.length > 0]).toEqual([entry.id, language, true]);
        expect(entry.names[language].every((name) => name.trim().length > 0)).toBe(true);
      }
    }
  });

  it('uses known categories, destinations and regions, and translates every tip', () => {
    const destinations = new Set<string>([...OFF_CURB, 'household', 'packaging', 'glass', 'food', 'green']);
    const rules = GUIDE_ITEMS.flatMap((entry) => [entry, ...Object.values(entry.regions ?? {})]);
    for (const entry of GUIDE_ITEMS) {
      expect(GUIDE_CATEGORIES).toContain(entry.category);
      expect(entry.to.length).toBeGreaterThan(0);
      for (const region of Object.keys(entry.regions ?? {})) expect(REGIONS).toContain(region);
    }
    for (const rule of rules) {
      for (const destination of [...(rule.to ?? []), ...(rule.fallback ?? [])]) expect(destinations).toContain(destination);
      if (rule.tip) for (const language of GUIDE_LANGUAGES) expect(rule.tip[language]?.trim()).toBeTruthy();
    }
    for (const category of GUIDE_CATEGORIES) expect(GUIDE_ITEMS.some((entry) => entry.category === category)).toBe(true);
  });

  it('lists only existing items as popular', () => {
    expect(POPULAR.every((id) => guideItem(id))).toBe(true);
  });
});

describe('advise', () => {
  it('gives the item rule when the place has the container', () => {
    expect(advise(item('peels'), 'kauno', kinds('household', 'food'))).toMatchObject({ to: ['food'], missing: undefined });
    expect(advise(item('batteries'), 'nemencine', kinds('household'))).toMatchObject({ to: ['shop', 'site'] });
  });

  it('falls back to home compost and the orange bag for food waste in Vilniaus r.', () => {
    const vilnius = kinds('household', 'packaging', 'glass');
    expect(advise(item('peels'), 'nemencine', vilnius)).toMatchObject({ to: ['compost', 'orangeBag'], missing: 'food' });
    // Meat isn't for a compost heap.
    expect(advise(item('meat-fish'), 'nemezio', vilnius)).toMatchObject({ to: ['orangeBag'], missing: 'food' });
  });

  it('falls back to mixed waste for food elsewhere, and uses an item fallback if it has one', () => {
    const village = kinds('household', 'packaging', 'glass');
    expect(advise(item('leftovers'), 'mazeikiai', village).to).toEqual(['household']);
    expect(advise(item('peels'), undefined, village).to).toEqual(['compost', 'household']);
    expect(advise(item('pizza-box'), 'nemencine', village)).toMatchObject({ to: ['household'], missing: 'food' });
  });

  it('falls back for green waste and for a container the user said they lack', () => {
    expect(advise(item('grass'), 'kauno', kinds('household', 'food')).to).toEqual(['compost', 'greenSite']);
    expect(advise(item('plastic-bottle'), 'nemencine', kinds('household', 'glass'))).toMatchObject({
      to: ['deposit', 'site'],
      missing: 'packaging',
    });
  });

  it("applies a company's own rule", () => {
    const all = kinds('household', 'packaging', 'glass', 'food');
    expect(advise(item('aerosol'), 'mazeikiai', all).to).toEqual(['packaging']);
    expect(advise(item('aerosol'), 'nemencine', all).to).toEqual(['site']);
    expect(advise(item('styrofoam'), 'nemezio', all).to).toEqual(['site']);
    expect(advise(item('styrofoam'), 'nemencine', all).to).toEqual(['packaging']);
    expect(advise(item('meat-fish'), 'mazeikiai', all).to).toEqual(['household']);
    expect(advise(item('meat-fish'), 'kauno', all).tip).toBe(item('meat-fish').regions?.kauno?.tip);
    expect(advise(item('leftovers'), 'nemencine', all).tip).toBe(item('leftovers').tip);
  });

  it("gives Kauno švara's food waste bag tip only where the address has a food waste bin", () => {
    const bag = item('peels').regions?.kauno?.tip;
    expect(advise(item('peels'), 'kauno', kinds('household', 'food', 'packaging', 'glass')).tip).toBe(bag);
    // Kaišiadorių r.: mixed waste only (and Ekonovus' glass and packaging).
    const kaisiadorys = kinds('household', 'packaging', 'glass');
    expect(advise(item('peels'), 'kauno', kaisiadorys)).toMatchObject({ to: ['compost', 'household'], tip: undefined });
    expect(advise(item('meat-fish'), 'kauno', kaisiadorys).tip).toBeUndefined();
    expect(advise(item('leftovers'), 'kauno', kaisiadorys).tip).toBe(item('leftovers').tip);
    // Not a tip about the food waste bin.
    expect(advise(item('tyres'), 'kauno', kaisiadorys).tip).toBe(item('tyres').regions?.kauno?.tip);
  });

  it("says what to do without the container when the place's containers are unknown", () => {
    expect(advise(item('peels'), undefined, undefined)).toMatchObject({
      to: ['food'],
      otherwise: { kind: 'food', to: ['compost', 'household'] },
    });
    expect(advise(item('peels'), 'nemezio', undefined).otherwise?.to).toEqual(['compost', 'orangeBag']);
    expect(advise(item('diapers'), undefined, undefined).otherwise).toBeUndefined();
    expect(advise(item('medicines'), undefined, undefined).otherwise).toBeUndefined();
  });

  it('never sends anything to a container the place lacks', () => {
    const minimal = kinds('household');
    for (const entry of GUIDE_ITEMS) {
      for (const region of [undefined, ...REGIONS]) {
        const { to } = advise(entry, region, minimal);
        expect([entry.id, to.filter((d) => isKind(d) && d !== 'household')]).toEqual([entry.id, []]);
        expect(new Set(to).size).toBe(to.length);
      }
    }
  });
});

// --- Places -----------------------------------------------------------------------------------

const today = '2026-11-21';
const area = (id: string, kind: Area['kind'], extra: Partial<Area> = {}): Area => ({
  id,
  kind,
  name: id,
  dates: ['2026-12-01'],
  ...extra,
});
const locations: Location[] = [
  { id: 'riese', name: 'Riešė', type: 'k.', district: 'Riešės', schedule: { household: { area: 'h' }, packaging: { area: 'p' }, glass: { area: 'g' } } },
  { id: 'nemezis', name: 'Nemėžis', type: 'k.', district: 'Nemėžio', provider: 'nemezio', schedule: { household: { area: 'nh' } } },
  {
    id: 'mazeikiai',
    name: 'Mažeikiai',
    type: 'm.',
    district: 'Mažeikių',
    provider: 'mazeikiai',
    schedule: { household: { area: 'mh' }, food: { area: 'mf' } },
  },
  { id: 'elsewhere', name: 'Kitur', type: 'k.', district: 'Kitur', provider: 'someone-new', schedule: { household: { area: 'xh' } } },
  {
    id: 'plunge',
    name: 'Plungė',
    type: 'm.',
    district: 'Plungės miesto',
    provider: 'plunge',
    schedule: { household: { area: 'ph' }, packaging: { area: 'pp' } },
  },
  { id: 'simnas', name: 'Simnas', type: 'm.', district: 'Simno', provider: 'alytus', schedule: { household: { area: 'ah' } } },
];
const data: ScheduleData = {
  schemaVersion: 1,
  generatedAt: '',
  source: '',
  coverage: {},
  areas: [
    area('h', 'household'),
    area('p', 'packaging'),
    area('g', 'glass'),
    area('nh', 'household', { provider: 'nemezio' }),
    area('mh', 'household', { provider: 'mazeikiai' }),
    area('mf', 'food', { provider: 'mazeikiai' }),
    area('xh', 'household', { provider: 'someone-new' }),
    area('ph', 'household', { provider: 'plunge' }),
    area('pp', 'packaging', { provider: 'plunge' }),
    area('ah', 'household', { provider: 'alytus' }),
  ],
  locations,
  personal: { key: '', areas: [] },
};
const at = (place: Place | null): [Place | null, Resolved] => [place, resolvePlace(data, place, today)];
const kaunoPlace: Place = {
  kauno: { eldership: 'ringaudu', eldershipName: 'Ringaudų sen.', town: 'Karkiškių k.', street: '', house: '' },
  choices: {},
};

describe('regionOf', () => {
  it('tells the company from the location, its rows or the Kauno r. address', () => {
    expect(regionOf(...at({ locationId: 'riese', choices: {} }))).toBe('nemencine');
    expect(regionOf(...at({ locationId: 'nemezis', choices: {} }))).toBe('nemezio');
    expect(regionOf(...at({ locationId: 'mazeikiai', choices: {} }))).toBe('mazeikiai');
    expect(regionOf(...at({ choices: { household: 'mh' } }))).toBe('mazeikiai');
    expect(regionOf(...at(kaunoPlace))).toBe('kauno');
  });

  it("doesn't guess for no place, own schedules only or a company it doesn't know", () => {
    expect(regionOf(...at(null))).toBeUndefined();
    expect(regionOf(...at({ choices: {}, custom: { household: { start: '2026-11-24', every: 2, unit: 'week' } } }))).toBeUndefined();
    expect(regionOf(...at({ locationId: 'elsewhere', choices: {} }))).toBeUndefined();
    // A regional centre without rules of its own here: the general advice.
    expect(regionOf(...at({ locationId: 'simnas', choices: {} }))).toBeUndefined();
    expect(advise(item('aerosol'), regionOf(...at({ locationId: 'simnas', choices: {} })), kinds('household')).to).toEqual(['site']);
  });

  it('gives the general advice in the regions added later', () => {
    const ids = ['radviliskis', 'pasvalys', 'rokiskis', 'birzai', 'panevezio-r', 'taurage', 'silale', 'pagegiai'];
    ids.push('marijampole', 'vilkaviskis', 'kalvarija', 'kazluruda', 'sakiai');
    for (const provider of ids) {
      const location: Location = { id: provider, name: provider, type: 'k.', district: provider, provider, schedule: { glass: { area: `${provider}-g` } } };
      const more = { ...data, areas: [...data.areas, area(`${provider}-g`, 'glass', { provider })], locations: [...data.locations!, location] };
      const place: Place = { locationId: provider, choices: {} };
      const resolved = resolvePlace(more, place, today);
      const region = regionOf(place, resolved);
      const available = availableKinds(place, resolved);
      expect([provider, region]).toEqual([provider, undefined]);
      // Panevėžio r. has no mixed waste data: the container every home has is still there.
      expect(available).toEqual(kinds('household', 'glass'));
      expect(advise(item('aerosol'), region, available).to).toEqual(['site']);
      expect(advise(item('peels'), region, available)).toMatchObject({ to: ['compost', 'household'], missing: 'food' });
      expect(locationsUrl('site', region)).toBeUndefined();
    }
  });

  it("gives TRATC's rules in all four of its municipalities", () => {
    const plunge = at({ locationId: 'plunge', choices: {} });
    expect(regionOf(...plunge)).toBe('mazeikiai');
    expect(regionOf(...at({ choices: { household: 'ph' } }))).toBe('mazeikiai');
    expect(advise(item('aerosol'), regionOf(...plunge), availableKinds(...plunge)).to).toEqual(['packaging']);
    expect(locationsUrl('site', regionOf(...plunge))).toContain('tratc.lt');
  });
});

describe('availableKinds', () => {
  it("lists the place's containers, without the ones it lacks or the user doesn't have", () => {
    expect(availableKinds(...at({ locationId: 'riese', choices: {} }))).toEqual(kinds('household', 'packaging', 'glass'));
    expect(availableKinds(...at({ locationId: 'riese', choices: { glass: null } }))).toEqual(kinds('household', 'packaging'));
    expect(availableKinds(...at({ locationId: 'mazeikiai', choices: {} }))).toEqual(kinds('household', 'food'));
  });

  it("counts Ekonovus' glass and packaging bins in Kauno r.", () => {
    const personal = { key: kaunoKey(kaunoPlace.kauno!), areas: [area('kh', 'household'), area('kf', 'food')] };
    const resolved = resolvePlace({ ...data, personal }, kaunoPlace, today);
    expect(availableKinds(kaunoPlace, resolved)).toEqual(kinds('household', 'food', 'packaging', 'glass'));
    const noGlass: Place = { ...kaunoPlace, choices: { glass: null } };
    expect(availableKinds(noGlass, resolvePlace({ ...data, personal }, noGlass, today))).toEqual(
      kinds('household', 'food', 'packaging'),
    );
  });

  it('has no food waste bin at a Kaišiadorių r. address, so no food waste bag tip', () => {
    const place: Place = {
      kauno: { eldership: 'ziezmariu', eldershipName: 'Žiežmarių sen.', town: 'Žiežmarių mstl.', street: 'Vytauto g.', house: '1' },
      choices: {},
    };
    const personal = { key: kaunoKey(place.kauno!), areas: [area('kh', 'household')] };
    const resolved = resolvePlace({ ...data, personal }, place, today);
    const available = availableKinds(place, resolved);
    expect(available).toEqual(kinds('household', 'packaging', 'glass'));
    expect(advise(item('peels'), regionOf(place, resolved), available)).toMatchObject({ missing: 'food', tip: undefined });
  });

  it("knows nothing without a place or before the place's schedules are loaded", () => {
    expect(availableKinds(...at(null))).toBeUndefined();
    expect(availableKinds(...at({ choices: {} }))).toBeUndefined();
    // The schedules of a Kauno r. address that aren't on the phone yet.
    expect(availableKinds(...at(kaunoPlace))).toBeUndefined();
  });
});

describe('locationsUrl', () => {
  it("links the regional centre's list of sites, and the deposit map everywhere", () => {
    expect(locationsUrl('site', 'nemezio')).toContain('vaatc.lt');
    expect(locationsUrl('greenSite', 'kauno')).toContain('kaunoratc.lt/zaka');
    expect(locationsUrl('site', 'mazeikiai')).toContain('tratc.lt');
    expect(locationsUrl('deposit', undefined)).toContain('grazintiverta.lt');
    expect(locationsUrl('site', undefined)).toBeUndefined();
    expect(locationsUrl('pharmacy', 'kauno')).toBeUndefined();
  });
});

describe('guideLanguage', () => {
  it('maps the app language and falls back to English', () => {
    expect(guideLanguage('lt')).toBe('lt');
    expect(guideLanguage('pl-PL')).toBe('pl');
    expect(guideLanguage('de')).toBe('en');
  });
});
