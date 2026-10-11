import { Ionicons } from '@expo/vector-icons';
import { Link, Redirect, router, Stack } from 'expo-router';
import { useEffect, useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { ActivityIndicator, Linking, Pressable, RefreshControl, ScrollView, StyleSheet, View } from 'react-native';

import { AppText, Banner, Button, Card, KindBadge } from '@/components/ui';
import { daysBetween, parseIsoDate } from '@/lib/dates';
import { hasNotificationPermission } from '@/lib/notifications';
import { type Pickup, upcomingPickups } from '@/lib/reminders';
import { resolveSelections } from '@/lib/selected-areas';
import { useSchedule } from '@/store/schedule';
import { useSettings } from '@/store/settings';
import { spacing, useTheme } from '@/theme';

const UPCOMING_COUNT = 12;

export default function Home() {
  const { t, i18n } = useTranslation();
  const theme = useTheme();
  const onboarded = useSettings((s) => s.onboarded);
  const selections = useSettings((s) => s.selections);
  const { data, refreshing, error, refresh } = useSchedule();
  const [notificationsOn, setNotificationsOn] = useState(true);

  useEffect(() => {
    hasNotificationPermission().then(setNotificationsOn);
  }, [data]);

  const { areas, missing } = useMemo(() => resolveSelections(data, selections), [data, selections]);
  const pickups = useMemo(() => upcomingPickups(areas, new Date()).slice(0, UPCOMING_COUNT), [areas]);

  if (!onboarded) return <Redirect href="/onboarding" />;

  const formatDate = (iso: string) =>
    new Intl.DateTimeFormat(i18n.language, { weekday: 'long', month: 'long', day: 'numeric' }).format(
      parseIsoDate(iso),
    );
  const relative = (iso: string) => {
    const days = daysBetween(new Date(), parseIsoDate(iso));
    if (days === 0) return t('home.today');
    if (days === 1) return t('home.tomorrow');
    return t('home.inDays', { count: days });
  };

  const header = (
    <Stack.Screen
      options={{
        headerRight: () => (
          <Link href="/settings" asChild>
            <Pressable accessibilityLabel={t('home.settings')} hitSlop={12}>
              <Ionicons name="settings-outline" size={24} color={theme.text} />
            </Pressable>
          </Link>
        ),
      }}
    />
  );

  if (!data) {
    return (
      <View style={styles.center}>
        {header}
        {error ? (
          <>
            <AppText muted style={styles.centerText}>
              {t(`errors.${error}`)}
            </AppText>
            <Button title={t('common.retry')} onPress={refresh} />
          </>
        ) : (
          <ActivityIndicator color={theme.primary} />
        )}
      </View>
    );
  }

  const [next, ...rest] = pickups;
  const notes = areas.filter((area) => area.note && !area.dates.length);

  return (
    <ScrollView
      contentContainerStyle={styles.content}
      refreshControl={<RefreshControl refreshing={refreshing} onRefresh={refresh} tintColor={theme.primary} />}>
      {header}

      {!notificationsOn && (
        <Banner action={<Button variant="secondary" title={t('common.openSettings')} onPress={() => Linking.openSettings()} />}>
          {t('home.notificationsOff')}
        </Banner>
      )}
      {missing.map((kind) => (
        <Banner
          key={kind}
          action={
            <Button
              variant="secondary"
              title={t('settings.areas')}
              onPress={() => router.push({ pathname: '/select/[kind]', params: { kind } })}
            />
          }>
          {t('home.areaMissing', { kind: t(`kinds.${kind}`) })}
        </Banner>
      ))}
      {notes.map((area) => (
        <Banner key={area.id}>{t('home.noteOnly', { kind: t(`kinds.${area.kind}`), note: area.note })}</Banner>
      ))}
      {error && <Banner>{error === 'unsupported' ? t('errors.unsupported') : t('home.refreshFailed')}</Banner>}

      {next ? (
        <Card style={[styles.hero, { backgroundColor: theme.primary, borderColor: theme.primary }]}>
          <AppText variant="caption" style={{ color: theme.onPrimary, opacity: 0.85 }}>
            {t('home.nextPickup')}
          </AppText>
          <AppText variant="title" style={{ color: theme.onPrimary }}>
            {relative(next.date)}
          </AppText>
          <AppText style={{ color: theme.onPrimary }}>{formatDate(next.date)}</AppText>
          <Kinds pickup={next} />
        </Card>
      ) : (
        <Card>
          <AppText muted>{t('home.nothingUpcoming')}</AppText>
        </Card>
      )}

      {rest.length > 0 && (
        <>
          <AppText variant="heading" style={styles.sectionTitle}>
            {t('home.upcoming')}
          </AppText>
          <Card style={styles.list}>
            {rest.map((pickup, index) => (
              <View
                key={pickup.date}
                style={[styles.listItem, index > 0 && { borderTopColor: theme.border, borderTopWidth: StyleSheet.hairlineWidth }]}>
                <View style={styles.listDate}>
                  <AppText>{formatDate(pickup.date)}</AppText>
                  <AppText variant="caption" muted>
                    {relative(pickup.date)}
                  </AppText>
                </View>
                <Kinds pickup={pickup} />
              </View>
            ))}
          </Card>
        </>
      )}

      <AppText variant="caption" muted style={styles.footer}>
        {t('home.updated', {
          date: new Intl.DateTimeFormat(i18n.language, { dateStyle: 'medium' }).format(new Date(data.generatedAt)),
        })}
      </AppText>
    </ScrollView>
  );
}

function Kinds({ pickup }: { pickup: Pickup }) {
  const { t } = useTranslation();
  return (
    <View style={styles.kinds}>
      {pickup.kinds.map((kind) => (
        <KindBadge key={kind} kind={kind} label={t(`kinds.${kind}`)} />
      ))}
    </View>
  );
}

const styles = StyleSheet.create({
  content: { padding: spacing.md, gap: spacing.md, paddingBottom: spacing.xl },
  center: { flex: 1, alignItems: 'center', justifyContent: 'center', padding: spacing.lg, gap: spacing.md },
  centerText: { textAlign: 'center' },
  hero: { paddingVertical: spacing.lg, gap: spacing.xs },
  sectionTitle: { marginTop: spacing.sm },
  list: { paddingVertical: 0 },
  listItem: { paddingVertical: spacing.md, gap: spacing.sm },
  listDate: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'baseline', gap: spacing.sm },
  kinds: { flexDirection: 'row', flexWrap: 'wrap', gap: spacing.xs, marginTop: spacing.xs },
  footer: { textAlign: 'center' },
});
