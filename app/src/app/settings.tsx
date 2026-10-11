import Constants from 'expo-constants';
import { router } from 'expo-router';
import * as WebBrowser from 'expo-web-browser';
import { useTranslation } from 'react-i18next';
import { Pressable, ScrollView, StyleSheet, View } from 'react-native';

import { AppText, Card, ListRow } from '@/components/ui';
import { LANGUAGE_NAMES, LANGUAGES, type Language } from '@/i18n';
import { PRIVACY_URL, REPOSITORY_URL, SOURCE_PAGE_URL } from '@/lib/config';
import type { ReminderSettings } from '@/lib/reminders';
import { WASTE_KINDS } from '@/lib/schedule';
import { useSchedule } from '@/store/schedule';
import { useSettings } from '@/store/settings';
import { radius, spacing, useTheme } from '@/theme';

// Bins must be out by 7:00 on collection day, so morning options stay before that.
const TIMES: Record<ReminderSettings['daysBefore'], [number, number][]> = {
  1: [
    [17, 0],
    [18, 0],
    [19, 0],
    [20, 0],
    [21, 0],
  ],
  0: [
    [5, 30],
    [6, 0],
    [6, 30],
  ],
};

const formatTime = (hour: number, minute: number) => `${hour}:${String(minute).padStart(2, '0')}`;

export default function Settings() {
  const { t } = useTranslation();
  const { selections, reminder, language, setReminder, setLanguage } = useSettings();
  const areas = useSchedule((s) => s.data?.areas);

  const areaName = (id: string | null | undefined) => {
    if (!id) return t('settings.notSelected');
    return areas?.find((a) => a.id === id)?.name ?? t('settings.notSelected');
  };

  const setDaysBefore = (daysBefore: ReminderSettings['daysBefore']) => {
    const [hour, minute] = TIMES[daysBefore][daysBefore === 1 ? 2 : 1];
    setReminder({ daysBefore, hour, minute });
  };

  return (
    <ScrollView contentContainerStyle={styles.content}>
      <Section title={t('settings.areas')}>
        {WASTE_KINDS.map((kind) => (
          <ListRow
            key={kind}
            title={t(`kinds.${kind}`)}
            subtitle={areaName(selections[kind])}
            onPress={() => router.push({ pathname: '/select/[kind]', params: { kind } })}
          />
        ))}
      </Section>

      <Section title={t('settings.reminder')}>
        <Chips
          options={[
            { key: 1, label: t('settings.eveningBefore') },
            { key: 0, label: t('settings.morningOf') },
          ]}
          value={reminder.daysBefore}
          onChange={setDaysBefore}
        />
        <AppText variant="caption" muted>
          {t('settings.time')}
        </AppText>
        <Chips
          options={TIMES[reminder.daysBefore].map(([h, m]) => ({ key: formatTime(h, m), label: formatTime(h, m) }))}
          value={formatTime(reminder.hour, reminder.minute)}
          onChange={(value) => {
            const [hour, minute] = value.split(':').map(Number);
            setReminder({ ...reminder, hour, minute });
          }}
        />
      </Section>

      <Section title={t('settings.language')}>
        <Chips<Language | 'system'>
          options={[
            { key: 'system', label: t('settings.systemLanguage') },
            ...LANGUAGES.map((code) => ({ key: code, label: LANGUAGE_NAMES[code] })),
          ]}
          value={language}
          onChange={setLanguage}
        />
      </Section>

      <Section title={t('settings.about')}>
        <ListRow icon="shield-checkmark-outline" title={t('settings.privacy')} onPress={() => WebBrowser.openBrowserAsync(PRIVACY_URL)} />
        <ListRow icon="calendar-outline" title={t('settings.source')} onPress={() => WebBrowser.openBrowserAsync(SOURCE_PAGE_URL)} />
        <ListRow icon="logo-github" title={t('settings.sourceCode')} onPress={() => WebBrowser.openBrowserAsync(REPOSITORY_URL)} />
      </Section>

      <Card>
        <AppText variant="label">{t('settings.disclaimerTitle')}</AppText>
        <AppText variant="caption" muted>
          {t('settings.disclaimer')}
        </AppText>
      </Card>

      <AppText variant="caption" muted style={styles.version}>
        {t('settings.version', { version: Constants.expoConfig?.version ?? '?' })}
      </AppText>
    </ScrollView>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <View style={styles.section}>
      <AppText variant="heading">{title}</AppText>
      <Card style={styles.sectionCard}>{children}</Card>
    </View>
  );
}

function Chips<T extends string | number>({
  options,
  value,
  onChange,
}: {
  options: { key: T; label: string }[];
  value: T;
  onChange: (key: T) => void;
}) {
  const theme = useTheme();
  return (
    <View style={styles.chips}>
      {options.map((option) => {
        const selected = option.key === value;
        return (
          <Pressable
            key={String(option.key)}
            onPress={() => onChange(option.key)}
            accessibilityRole="radio"
            accessibilityState={{ selected }}
            style={[
              styles.chip,
              { backgroundColor: selected ? theme.primary : theme.surfaceMuted },
            ]}>
            <AppText variant="caption" style={{ color: selected ? theme.onPrimary : theme.text, fontWeight: '600' }}>
              {option.label}
            </AppText>
          </Pressable>
        );
      })}
    </View>
  );
}

const styles = StyleSheet.create({
  content: { padding: spacing.md, gap: spacing.lg, paddingBottom: spacing.xl },
  section: { gap: spacing.sm },
  sectionCard: { paddingVertical: spacing.sm },
  chips: { flexDirection: 'row', flexWrap: 'wrap', gap: spacing.sm, paddingVertical: spacing.xs },
  chip: { borderRadius: radius.pill, paddingHorizontal: 14, paddingVertical: 8 },
  version: { textAlign: 'center' },
});
