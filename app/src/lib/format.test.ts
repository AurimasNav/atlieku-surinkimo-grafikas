import { capitalize, longDate } from './format';

describe('longDate', () => {
  // 2026-11-16 is a Monday.
  it('keeps each language’s own case, so it reads right after "Next:"', () => {
    expect(longDate('en', '2026-11-16')).toBe('Monday, November 16');
    expect(longDate('lt', '2026-11-16')).toBe('lapkričio 16 d., pirmadienis');
    expect(longDate('ru', '2026-11-16')).toBe('понедельник, 16 ноября');
    expect(longDate('pl', '2026-11-16')).toBe('poniedziałek, 16 listopada');
  });

  it('is capitalised where it stands on its own', () => {
    expect(capitalize(longDate('lt', '2026-11-16'))).toBe('Lapkričio 16 d., pirmadienis');
    expect(capitalize(longDate('ru', '2026-11-16'))).toBe('Понедельник, 16 ноября');
  });
});
