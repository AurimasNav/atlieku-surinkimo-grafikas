import type { Area, ScheduleData } from './schedule';
import { searchAreas } from './schedule';
import { resolveSelections } from './selected-areas';

const today = '2026-10-11';

const area = (id: string, name: string, dates: string[], extra: Partial<Area> = {}): Area => ({
  id,
  kind: 'glass',
  name,
  dates,
  ...extra,
});

const data = (areas: Area[], coverageTo = '2026-12-31'): ScheduleData => ({
  schemaVersion: 1,
  generatedAt: '2026-10-11T00:00:00Z',
  source: '',
  coverage: { glass: { from: '2026-09-01', to: coverageTo } },
  areas,
});

describe('searchAreas', () => {
  const areas = [
    area('old', 'Riešės k. (Q3 text)', ['2026-09-29']),
    area('new', 'Riešės k. (Q4 text)', ['2026-10-29']),
    area('rule', 'Skersabaliai', [], { note: 'kas antras mėnesio trečiadienis' }),
  ];

  it('ignores diacritics and case', () => {
    expect(searchAreas(areas, 'glass', 'rieses', today).map((a) => a.id)).toEqual(['new']);
  });

  it('hides rows whose dates are all in the past, but keeps text-only rules', () => {
    expect(searchAreas(areas, 'glass', '', today).map((a) => a.id)).toEqual(['new', 'rule']);
  });
});

describe('resolveSelections', () => {
  it('asks to pick again when the chosen row is outdated and a newer schedule exists', () => {
    const result = resolveSelections(
      data([area('old', 'A', ['2026-09-29']), area('new', 'A2', ['2026-10-29'])]),
      { glass: 'old' },
      today,
    );
    expect(result).toEqual({ areas: [], missing: ['glass'] });
  });

  it('keeps the chosen row while no newer schedule has been published', () => {
    const result = resolveSelections(data([area('old', 'A', ['2026-09-29'])], '2026-09-29'), { glass: 'old' }, today);
    expect(result.missing).toEqual([]);
    expect(result.areas.map((a) => a.id)).toEqual(['old']);
  });

  it('asks to pick again when the chosen row disappeared', () => {
    expect(resolveSelections(data([]), { glass: 'gone' }, today).missing).toEqual(['glass']);
  });

  it('ignores kinds the user skipped', () => {
    expect(resolveSelections(data([]), { glass: null }, today)).toEqual({ areas: [], missing: [] });
  });
});
