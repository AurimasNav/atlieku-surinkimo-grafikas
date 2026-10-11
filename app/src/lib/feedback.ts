import Constants from 'expo-constants';
import * as WebBrowser from 'expo-web-browser';
import { Platform } from 'react-native';

import { REPOSITORY_URL } from './config';

/** Issue forms in .github/ISSUE_TEMPLATE; field ids must match the `id`s there. */
export type IssueTemplate = 'bug_report' | 'crash_report' | 'schedule_problem' | 'feature_request';

/** Browsers and GitHub reject very long URLs; keep well under the ~8k practical limit. */
const MAX_FIELD_LENGTH = 2000;

export function appVersion(): string {
  return Constants.expoConfig?.version ?? 'unknown';
}

/** "Google Pixel 8, Android 16 (API 36)" — no identifiers, just what helps reproduce bugs. */
export function deviceDescription(): string {
  if (Platform.OS === 'android') {
    const c = Platform.constants as { Brand?: string; Model?: string; Release?: string };
    return `${[c.Brand, c.Model].filter(Boolean).join(' ')}, Android ${c.Release ?? ''} (API ${Platform.Version})`.trim();
  }
  return `${Platform.OS} ${Platform.Version}`;
}

export function issueUrl(template: IssueTemplate, fields: Record<string, string | undefined> = {}): string {
  const params = new URLSearchParams({ template: `${template}.yml` });
  for (const [key, value] of Object.entries(fields)) {
    if (!value) continue;
    params.set(key, value.length > MAX_FIELD_LENGTH ? `${value.slice(0, MAX_FIELD_LENGTH)}\n…(truncated)` : value);
  }
  return `${REPOSITORY_URL}/issues/new?${params.toString()}`;
}

/**
 * Opens a prefilled GitHub issue form. Nothing is sent until the user reviews the form and
 * submits it on GitHub (which needs a GitHub account).
 */
export function openIssue(template: IssueTemplate, fields: Record<string, string | undefined> = {}) {
  return WebBrowser.openBrowserAsync(
    issueUrl(template, { 'app-version': appVersion(), device: deviceDescription(), ...fields }),
  );
}

export function formatError(error: unknown): string {
  if (error instanceof Error) return `${error.name}: ${error.message}\n\n${error.stack ?? ''}`.trim();
  return String(error);
}
