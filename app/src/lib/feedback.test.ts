import { formatError, issueUrl } from './feedback';

jest.mock('expo-web-browser', () => ({ openBrowserAsync: jest.fn() }));

describe('issueUrl', () => {
  it('selects the form in the given language and prefills fields by id', () => {
    const url = new URL(
      issueUrl('schedule_problem', 'lt', { place: 'Avižieniai, Durpių g.', 'data-date': '2026-10-11' }),
    );
    expect(url.pathname).toBe('/AurimasNav/atlieku-surinkimo-grafikas/issues/new');
    expect(url.searchParams.get('template')).toBe('lt-schedule_problem.yml');
    expect(url.searchParams.get('place')).toBe('Avižieniai, Durpių g.');
    expect(url.searchParams.get('data-date')).toBe('2026-10-11');
  });

  it('falls back to the English form', () => {
    expect(new URL(issueUrl('feature_request', 'de')).searchParams.get('template')).toBe('en-feature_request.yml');
  });

  it('skips empty fields and truncates long ones', () => {
    const url = new URL(issueUrl('crash_report', 'en', { error: 'x'.repeat(5000), device: undefined }));
    expect(url.searchParams.has('device')).toBe(false);
    expect(url.searchParams.get('error')!.length).toBeLessThan(2100);
    expect(url.toString().length).toBeLessThan(8000);
  });
});

describe('formatError', () => {
  it('includes name, message and stack', () => {
    const error = new TypeError('boom');
    expect(formatError(error)).toMatch(/^TypeError: boom\n\n.*boom/s);
    expect(formatError('plain')).toBe('plain');
  });
});
