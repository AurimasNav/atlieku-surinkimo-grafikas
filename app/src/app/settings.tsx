import { Ionicons } from '@expo/vector-icons';
import Constants from 'expo-constants';
import { router } from 'expo-router';
import * as WebBrowser from 'expo-web-browser';
import type { ReactNode } from 'react';
import { useTranslation } from 'react-i18next';
import { ScrollView, StyleSheet, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { ReminderPicker } from '@/components/reminder-picker';
import { AppText, Button, Card, Chip, KindIcon, ListRow, ScreenHeader } from '@/components/ui';
import { LANGUAGE_NAMES, LANGUAGES, type Language } from '@/i18n';
import { PRIVACY_URL, REPOSITORY_URL, SOURCE_PAGE_URL } from '@/lib/config';
import { toIsoDate } from '@/lib/dates';
import { openIssue } from '@/lib/feedback';
import { resolvePlace } from '@/lib/resolve';
import { WASTE_KINDS } from '@/lib/schedule';
import { useSchedule } from '@/store/schedule';
import { useSettings } from '@/store/settings';
import { radius, spacing, useTheme } from '@/theme';

export default function Settings() {
  const { t, i18n } = useTranslation();
  const theme = useTheme();
  const insets = useSafeAreaInsets();
  const { place, language, setLanguage } = useSettings();
  const data = useSchedule((s) => s.data);
  const resolved = resolvePlace(data, place, toIsoDate(new Date()));
  const location = resolved.location;
  const street =
    place?.street === ''
      ? t('settings.streetNotListed')
      : location?.streets?.find(([key]) => key === place?.street)?.[1];

  return (
    <ScrollView contentContainerStyle={{ paddingBottom: insets.bottom + spacing.xl }}>
      <ScreenHeader title={t('settings.title')} />
      <View style={styles.content}>
        <Section title={t('settings.location')}>
          <Card style={styles.placeCard}>
            <View style={styles.placeRow}>
              <View style={[styles.pin, { backgroundColor: theme.primary }]}>
                <Ionicons name="location" size={22} color={theme.onPrimary} />
              </View>
              <View style={styles.placeText}>
                <AppText variant="heading">{location?.name ?? t('settings.notSelected')}</AppText>
                <AppText variant="caption" muted>
                  {[street, location && `${location.district} sen.`].filter(Boolean).join(' · ')}
                </AppText>
              </View>
            </View>
            <View style={styles.kinds}>
              {WASTE_KINDS.map((kind) => {
                const status = resolved.kinds[kind];
                return (
                  <View key={kind} style={[styles.kindRow, { opacity: status.status === 'ok' ? 1 : 0.5 }]}>
                    <KindIcon kind={kind} size={28} />
                    <AppText variant="caption" numberOfLines={2} style={styles.kindText}>
                      {status.status === 'ok' ? status.area.name : t('setup.notCollected')}
                    </AppText>
                  </View>
                );
              })}
            </View>
            <Button variant="secondary" icon="swap-horizontal" title={t('settings.changeLocation')} onPress={() => router.push('/setup/location')} />
          </Card>
        </Section>

        <Section title={t('settings.reminder')}>
          <ReminderPicker />
        </Section>

        <Section title={t('settings.language')}>
          <View style={styles.chips}>
            {(['system', ...LANGUAGES] as (Language | 'system')[]).map((code) => (
              <Chip
                key={code}
                label={code === 'system' ? t('settings.systemLanguage') : LANGUAGE_NAMES[code]}
                selected={language === code}
                onPress={() => setLanguage(code)}
              />
            ))}
          </View>
        </Section>

        <Section title={t('feedback.title')}>
          <View style={styles.links}>
            <ListRow
              icon={<Ionicons name="bug" size={22} color={theme.primary} />}
              title={t('feedback.bug')}
              onPress={() => openIssue('bug_report', { language: i18n.language })}
            />
            <ListRow
              icon={<Ionicons name="calendar-clear" size={22} color={theme.primary} />}
              title={t('feedback.schedule')}
              onPress={() =>
                openIssue('schedule_problem', {
                  place: [location?.name, street].filter(Boolean).join(', '),
                  'data-date': data?.generatedAt.slice(0, 10),
                })
              }
            />
            <ListRow
              icon={<Ionicons name="bulb" size={22} color={theme.primary} />}
              title={t('feedback.idea')}
              onPress={() => openIssue('feature_request')}
            />
          </View>
          <AppText variant="caption" muted>
            {t('feedback.githubNote')}
          </AppText>
        </Section>

        <Section title={t('settings.about')}>
          <View style={styles.links}>
            <ListRow
              icon={<Ionicons name="shield-checkmark" size={22} color={theme.primary} />}
              title={t('settings.privacy')}
              onPress={() => WebBrowser.openBrowserAsync(PRIVACY_URL)}
            />
            <ListRow
              icon={<Ionicons name="calendar" size={22} color={theme.primary} />}
              title={t('settings.source')}
              onPress={() => WebBrowser.openBrowserAsync(SOURCE_PAGE_URL)}
            />
            <ListRow
              icon={<Ionicons name="logo-github" size={22} color={theme.primary} />}
              title={t('settings.sourceCode')}
              onPress={() => WebBrowser.openBrowserAsync(REPOSITORY_URL)}
            />
          </View>
        </Section>

        <Card>
          <AppText variant="label">{t('settings.disclaimerTitle')}</AppText>
          <AppText variant="caption" muted>
            {t('settings.disclaimer')}
          </AppText>
        </Card>

        <View style={styles.meta}>
          {data?.locations && (
            <AppText variant="caption" muted style={styles.center}>
              {t('settings.addressSource', { source: 'Adresų registras, VĮ Registrų centras' })}
            </AppText>
          )}
          <AppText variant="caption" muted style={styles.center}>
            {t('settings.version', { version: Constants.expoConfig?.version ?? '?' })}
          </AppText>
        </View>
      </View>
    </ScrollView>
  );
}

function Section({ title, children }: { title: string; children: ReactNode }) {
  return (
    <View style={styles.section}>
      <AppText variant="overline" muted>
        {title}
      </AppText>
      {children}
    </View>
  );
}

const styles = StyleSheet.create({
  content: { paddingHorizontal: spacing.lg, gap: spacing.xl },
  section: { gap: spacing.sm + 2 },
  placeCard: { gap: spacing.md },
  placeRow: { flexDirection: 'row', alignItems: 'center', gap: spacing.md },
  pin: { width: 48, height: 48, borderRadius: radius.md, alignItems: 'center', justifyContent: 'center' },
  placeText: { flex: 1, gap: 2 },
  kinds: { gap: spacing.sm },
  kindRow: { flexDirection: 'row', alignItems: 'center', gap: spacing.sm },
  kindText: { flex: 1 },
  chips: { flexDirection: 'row', flexWrap: 'wrap', gap: spacing.sm },
  links: { gap: spacing.sm },
  meta: { gap: spacing.xs },
  center: { textAlign: 'center' },
});
