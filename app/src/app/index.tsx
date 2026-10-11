import { Ionicons } from '@expo/vector-icons';
import { LinearGradient } from 'expo-linear-gradient';
import { Redirect, router } from 'expo-router';
import { useEffect, useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { ActivityIndicator, Linking, RefreshControl, ScrollView, StyleSheet, View } from 'react-native';
import Animated, { FadeIn, FadeInDown, LinearTransition } from 'react-native-reanimated';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { AppText, Button, Chip, IconButton, KindBadge, KindIcon, Notice, PressableScale } from '@/components/ui';
import { toIsoDate } from '@/lib/dates';
import { formatTime, useDateFormat } from '@/lib/format';
import { hasNotificationPermission } from '@/lib/notifications';
import { type Pickup, upcomingPickups } from '@/lib/reminders';
import { pendingKinds, resolvePlace } from '@/lib/resolve';
import { WASTE_KINDS, type WasteKind } from '@/lib/schedule';
import { useSchedule } from '@/store/schedule';
import { useSettings } from '@/store/settings';
import { fonts, kindPalette, radius, spacing, useTheme } from '@/theme';

type Filter = 'all' | WasteKind;

const UPCOMING_LIMIT = 30;

export default function Home() {
  const { t, i18n } = useTranslation();
  const theme = useTheme();
  const insets = useSafeAreaInsets();
  const date = useDateFormat();
  const onboarded = useSettings((s) => s.onboarded);
  const place = useSettings((s) => s.place);
  const reminder = useSettings((s) => s.reminder);
  const { data, refreshing, error, refresh } = useSchedule();
  const [filter, setFilter] = useState<Filter>('all');
  const [notificationsOn, setNotificationsOn] = useState(true);

  useEffect(() => {
    hasNotificationPermission().then(setNotificationsOn);
  }, [data]);

  const resolved = useMemo(() => resolvePlace(data, place, toIsoDate(new Date())), [data, place]);
  const activeKinds = WASTE_KINDS.filter((kind) => resolved.kinds[kind].status === 'ok');
  const allPickups = useMemo(() => upcomingPickups(resolved.areas, new Date()), [resolved]);
  const pickups = useMemo(
    () =>
      (filter === 'all'
        ? allPickups
        : allPickups.filter((p) => p.kinds.includes(filter)).map((p) => ({ ...p, kinds: [filter] }))
      ).slice(0, UPCOMING_LIMIT),
    [allPickups, filter],
  );

  if (!onboarded) return <Redirect href="/onboarding" />;

  const [next, ...rest] = pickups;
  const pending = pendingKinds(resolved);
  const placeName = resolved.location?.name ?? t('home.choosePlace');
  const notes = resolved.areas.filter((area) => area.note && !area.dates.length);
  const reminderText = t(reminder.daysBefore === 1 ? 'home.reminderEvening' : 'home.reminderMorning', {
    time: formatTime(reminder.hour, reminder.minute),
  });

  // Group the remaining pickups by month for section headers.
  const months: { key: string; label: string; items: Pickup[] }[] = [];
  for (const pickup of rest) {
    const key = pickup.date.slice(0, 7);
    if (months.at(-1)?.key !== key) months.push({ key, label: date.month(pickup.date), items: [] });
    months.at(-1)!.items.push(pickup);
  }

  return (
    <View style={styles.screen}>
      <ScrollView
        contentContainerStyle={[styles.content, { paddingTop: insets.top + spacing.sm, paddingBottom: insets.bottom + spacing.xl }]}
        refreshControl={<RefreshControl refreshing={refreshing} onRefresh={refresh} tintColor={theme.primary} />}>
        {/* Top bar: where you are, and settings */}
        <View style={styles.topBar}>
          <PressableScale
            haptic="light"
            onPress={() => router.push('/setup/location')}
            accessibilityRole="button"
            wrapperStyle={styles.placeWrapper}
            style={[styles.placePill, { backgroundColor: theme.surface }]}>
            <Ionicons name="location" size={16} color={theme.primary} />
            <AppText variant="label" numberOfLines={1} style={styles.placeText}>
              {placeName}
            </AppText>
            <Ionicons name="chevron-down" size={16} color={theme.textMuted} />
          </PressableScale>
          <IconButton icon="settings-outline" label={t('home.settings')} onPress={() => router.push('/settings')} />
        </View>

        {!data ? (
          <View style={styles.center}>
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
        ) : (
          <>
            {/* Things that need attention */}
            {!notificationsOn && (
              <Notice action={<Button variant="secondary" title={t('common.openSettings')} onPress={() => Linking.openSettings()} />}>
                {t('home.notificationsOff')}
              </Notice>
            )}
            {pending.length > 0 && (
              <Notice
                action={
                  <Button
                    variant="secondary"
                    title={t('common.continue')}
                    onPress={() =>
                      resolved.kinds[pending[0]].status === 'missing'
                        ? router.push('/setup/location')
                        : router.push({ pathname: '/setup/choose/[kind]', params: { kind: pending[0] } })
                    }
                  />
                }>
                {resolved.kinds[pending[0]].status === 'missing'
                  ? t('home.placeMissing')
                  : t('home.choosePending', { kind: t(`kinds.${pending[0]}`).toLowerCase() })}
              </Notice>
            )}
            {notes.map((area) => (
              <Notice key={area.id} tone="info">
                {t('home.noteOnly', { kind: t(`kinds.${area.kind}`), note: area.note })}
              </Notice>
            ))}
            {error && <Notice>{error === 'unsupported' ? t('errors.unsupported') : t('home.refreshFailed')}</Notice>}

            {/* Hero: the next pickup */}
            {next ? (
              <Animated.View key={`${filter}-${next.date}`} entering={FadeIn.duration(350)}>
                <LinearGradient
                  colors={theme.dark ? ['#11402C', '#0A2A1D'] : ['#0F6B47', '#0A4A31']}
                  start={{ x: 0, y: 0 }}
                  end={{ x: 1, y: 1 }}
                  style={styles.hero}>
                  <View style={styles.heroGlow} />
                  <AppText variant="overline" style={styles.heroEyebrow}>
                    {t('home.nextPickup')}
                  </AppText>
                  <AppText variant="display" style={styles.heroTitle}>
                    {date.relative(next.date)}
                  </AppText>
                  <AppText variant="heading" style={styles.heroDate}>
                    {date.long(next.date)}
                  </AppText>
                  <View style={styles.heroKinds}>
                    {next.kinds.map((kind) => (
                      <KindBadge key={kind} kind={kind} label={t(`kinds.${kind}`)} />
                    ))}
                  </View>
                  <View style={styles.heroFooter}>
                    <Ionicons name={notificationsOn ? 'notifications' : 'notifications-off'} size={16} color="#C8F169" />
                    <AppText variant="caption" style={styles.heroReminder}>
                      {reminderText}
                    </AppText>
                  </View>
                </LinearGradient>
              </Animated.View>
            ) : (
              <View style={[styles.emptyCard, { backgroundColor: theme.surface }]}>
                <AppText muted>
                  {filter === 'all' ? t('home.nothingUpcoming') : t('home.nothingForKind', { kind: t(`kinds.${filter}`).toLowerCase() })}
                </AppText>
              </View>
            )}

            {/* Filter by waste type */}
            {activeKinds.length > 1 && (
              <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={styles.filters}>
                <Chip label={t('home.filterAll')} selected={filter === 'all'} onPress={() => setFilter('all')} />
                {activeKinds.map((kind) => (
                  <Chip
                    key={kind}
                    label={t(`kinds.${kind}`)}
                    color={kindPalette[kind].solid}
                    count={allPickups.filter((p) => p.kinds.includes(kind)).length}
                    selected={filter === kind}
                    onPress={() => setFilter(filter === kind ? 'all' : kind)}
                  />
                ))}
              </ScrollView>
            )}

            {/* Timeline */}
            {months.map((month) => (
              <Animated.View key={`${filter}-${month.key}`} layout={LinearTransition.springify()} style={styles.month}>
                <AppText variant="overline" muted style={styles.monthTitle}>
                  {month.label}
                </AppText>
                <View style={[styles.timeline, { backgroundColor: theme.surface }]}>
                  {month.items.map((pickup, index) => (
                    <Animated.View
                      key={pickup.date}
                      entering={FadeInDown.delay(Math.min(index, 8) * 35).duration(320)}
                      style={[
                        styles.item,
                        index > 0 && { borderTopWidth: StyleSheet.hairlineWidth, borderTopColor: theme.border },
                      ]}>
                      <View style={[styles.dateTile, { backgroundColor: theme.surfaceMuted }]}>
                        <AppText style={styles.dateDay}>{date.day(pickup.date)}</AppText>
                        <AppText variant="caption" muted style={styles.dateWeekday}>
                          {date.weekday(pickup.date)}
                        </AppText>
                      </View>
                      <View style={styles.itemBody}>
                        <View style={styles.itemKinds}>
                          {pickup.kinds.map((kind) => (
                            <View key={kind} style={styles.itemKind}>
                              <KindIcon kind={kind} size={26} />
                              <AppText variant="label">{t(`kinds.${kind}`)}</AppText>
                            </View>
                          ))}
                        </View>
                        <AppText variant="caption" muted>
                          {date.relative(pickup.date)}
                        </AppText>
                      </View>
                    </Animated.View>
                  ))}
                </View>
              </Animated.View>
            ))}

            <AppText variant="caption" muted style={styles.footer}>
              {t('home.updated', {
                date: new Intl.DateTimeFormat(i18n.language, { dateStyle: 'medium' }).format(new Date(data.generatedAt)),
              })}
            </AppText>
          </>
        )}
      </ScrollView>
    </View>
  );
}

const styles = StyleSheet.create({
  screen: { flex: 1 },
  content: { paddingHorizontal: spacing.lg, gap: spacing.md },
  topBar: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', gap: spacing.md, marginBottom: spacing.sm },
  placePill: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
    height: 44,
    paddingHorizontal: spacing.md,
    borderRadius: radius.pill,
  },
  placeWrapper: { flexShrink: 1 },
  placeText: { flexShrink: 1 },
  center: { minHeight: 300, alignItems: 'center', justifyContent: 'center', gap: spacing.md },
  centerText: { textAlign: 'center' },
  hero: { borderRadius: radius.xl, padding: spacing.lg, paddingTop: spacing.lg + 4, gap: 6, overflow: 'hidden' },
  heroGlow: {
    position: 'absolute',
    width: 260,
    height: 260,
    borderRadius: 130,
    right: -90,
    top: -110,
    backgroundColor: 'rgba(200,241,105,0.16)',
  },
  heroEyebrow: { color: '#C8F169' },
  heroTitle: { color: '#FFFFFF', fontSize: 56, lineHeight: 60 },
  heroDate: { color: 'rgba(255,255,255,0.85)', fontFamily: fonts.medium },
  heroKinds: { flexDirection: 'row', flexWrap: 'wrap', gap: spacing.sm, marginTop: spacing.md },
  heroFooter: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.sm,
    marginTop: spacing.md,
    paddingTop: spacing.md,
    borderTopWidth: StyleSheet.hairlineWidth,
    borderTopColor: 'rgba(255,255,255,0.18)',
  },
  heroReminder: { color: 'rgba(255,255,255,0.85)', fontFamily: fonts.medium },
  emptyCard: { borderRadius: radius.lg, padding: spacing.lg },
  filters: { gap: spacing.sm, paddingVertical: spacing.xs },
  month: { gap: spacing.sm },
  monthTitle: { marginLeft: spacing.xs, marginTop: spacing.sm },
  timeline: { borderRadius: radius.lg, paddingHorizontal: spacing.md },
  item: { flexDirection: 'row', alignItems: 'center', gap: spacing.md, paddingVertical: spacing.md },
  dateTile: { width: 56, height: 60, borderRadius: radius.md, alignItems: 'center', justifyContent: 'center' },
  dateDay: { fontFamily: fonts.heavy, fontSize: 24, lineHeight: 28 },
  dateWeekday: { fontFamily: fonts.bold, fontSize: 12, lineHeight: 14 },
  itemBody: { flex: 1, gap: 6 },
  itemKinds: { gap: 6 },
  itemKind: { flexDirection: 'row', alignItems: 'center', gap: spacing.sm },
  footer: { textAlign: 'center', marginTop: spacing.md },
});
