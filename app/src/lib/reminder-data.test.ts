import { pickupFromContent } from './reminder-data';

describe('pickupFromContent', () => {
  const data = { type: 'pickup', date: '2026-11-26', kinds: ['glass', 'household', 'mystery'] };

  it('reads the data the app gets', () => {
    expect(pickupFromContent({ data })).toEqual({ date: '2026-11-26', kinds: ['household', 'glass'] });
  });

  it('reads the JSON string the background task gets', () => {
    expect(pickupFromContent({ dataString: JSON.stringify(data) })).toEqual({ date: '2026-11-26', kinds: ['household', 'glass'] });
  });

  it('ignores other notifications and broken data', () => {
    expect(pickupFromContent({ data: { type: 'changes' } })).toBeUndefined();
    expect(pickupFromContent({ dataString: '{not json' })).toBeUndefined();
    expect(pickupFromContent(undefined)).toBeUndefined();
  });
});
