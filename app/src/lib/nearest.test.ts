import { type AddressTable, findNearest } from './nearest';

const table: AddressTable = {
  generatedAt: '',
  source: '',
  places: [
    ['g10937', 's1559497', 'Durpių g.'],
    ['g10937', 's1648908', 'Akacijų aklg.'],
    ['g10214', '', ''],
  ],
  points: [
    [5480000, 2525000, 0, '12'], // Durpių g. 12
    [5480050, 2525100, 1, '3'], // Akacijų aklg. 3, ~60 m north-east
    [5490000, 2530000, 2, '7'], // a village address without a street, ~12 km away
  ],
};

describe('findNearest', () => {
  it('returns the closest address with its street', () => {
    const hit = findNearest(table, 54.80001, 25.25001);
    expect(hit).toMatchObject({ locationId: 'g10937', street: 's1559497', streetLabel: 'Durpių g.', number: '12' });
    expect(hit!.distance).toBeLessThan(5);
  });

  it('accounts for longitude shrinking with latitude', () => {
    // 0.0006° east is ~38 m at this latitude, 0.0004° north is ~45 m: east wins.
    const east = { ...table, points: [[5480000, 2525060, 0, 'E'], [5480040, 2525000, 1, 'N']] as AddressTable['points'] };
    expect(findNearest(east, 54.8, 25.25)!.number).toBe('E');
  });

  it('reports villages without streets and the distance to them', () => {
    const hit = findNearest(table, 54.9, 25.3);
    expect(hit).toMatchObject({ locationId: 'g10214', street: undefined, number: '7' });
    expect(hit!.distance).toBeLessThan(5);
  });

  it('handles an empty table', () => {
    expect(findNearest({ ...table, points: [] }, 54.8, 25.25)).toBeNull();
  });
});
