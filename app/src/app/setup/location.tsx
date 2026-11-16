import { Ionicons } from '@expo/vector-icons';
import { router } from 'expo-router';
import { useDeferredValue, useEffect, useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { ActivityIndicator, FlatList, StyleSheet, View } from 'react-native';
import Animated, {
  cancelAnimation,
  Easing,
  FadeIn,
  FadeInDown,
  useAnimatedStyle,
  useReducedMotion,
  useSharedValue,
  withRepeat,
  withTiming,
} from 'react-native-reanimated';

import { AppText, Button, ListRow, PressableScale, ScreenHeader, SearchField } from '@/components/ui';
import { type GeolocateResult, locateHome } from '@/lib/geolocate';
import { searchLocations } from '@/lib/schedule';
import { nextSetupStep } from '@/lib/setup-flow';
import { useMotion } from '@/lib/motion';
import { useSchedule } from '@/store/schedule';
import { useSettings } from '@/store/settings';
import { fonts, radius, spacing, useTheme } from '@/theme';

const MAX_RESULTS = 50;

export default function ChooseLocation() {
  const motion = useMotion();
  const { t } = useTranslation();
  const theme = useTheme();
  const { data, error, refresh } = useSchedule();
  const current = useSettings((s) => s.place?.locationId);
  const [query, setQuery] = useState('');
  const deferred = useDeferredValue(query);
  const [locating, setLocating] = useState(false);
  const [gps, setGps] = useState<GeolocateResult | null>(null);

  const results = useMemo(
    () => searchLocations(data?.locations ?? [], deferred).slice(0, MAX_RESULTS),
    [data, deferred],
  );

  const pick = (locationId: string, street?: string) => {
    useSettings.getState().setLocation(locationId, street);
    router.push(nextSetupStep(useSchedule.getState().data, useSettings.getState().place));
  };

  const locate = async () => {
    setGps(null);
    setLocating(true);
    try {
      setGps(await locateHome());
    } finally {
      setLocating(false);
    }
  };

  const found = gps?.ok ? gps : null;
  const foundLocation = found && data?.locations?.find((loc) => loc.id === found.address.locationId);
  const confirmFound = () => {
    if (!found) return;
    // Only pass the street when we trust it; otherwise the street step asks.
    pick(found.address.locationId, found.streetConfident ? found.address.street : undefined);
  };

  const gpsCard = (
    <View style={styles.gps}>
      {found && foundLocation ? (
        <Animated.View entering={motion(FadeInDown.duration(300))} style={[styles.found, { backgroundColor: theme.surface, borderColor: theme.primary }]}>
          <AppText variant="overline" style={{ color: theme.primary }}>
            {t('setup.foundTitle')}
          </AppText>
          <AppText variant="title">
            {[found.address.streetLabel, found.address.number].filter(Boolean).join(' ') || foundLocation.name}
          </AppText>
          <AppText muted>
            {foundLocation.name}, {foundLocation.district} sen.
          </AppText>
          {!found.streetConfident && (
            <AppText variant="caption" muted>
              {t('setup.foundStreetUnsure')}
            </AppText>
          )}
          <View style={styles.foundActions}>
            <Button icon="checkmark" title={t('setup.confirmHome')} onPress={confirmFound} />
            <Button variant="ghost" title={t('setup.notHome')} onPress={() => setGps(null)} />
          </View>
        </Animated.View>
      ) : (
        // Testers read the solid green card (the colour of the app's banners) as information and
        // went straight to the search field. A white row with a green border, a pulsing icon and
        // a chevron looks like the tappable rows on this screen, but stands out from them.
        <PressableScale
          haptic="light"
          onPress={locate}
          disabled={locating}
          accessibilityRole="button"
          accessibilityLabel={t('setup.useLocation')}
          style={[styles.locate, { backgroundColor: theme.surface, borderColor: theme.primary }]}>
          <View style={styles.locateIcon}>
            {!locating && <Pulse color={theme.primary} />}
            <View style={[styles.locateCircle, { backgroundColor: theme.primary }]}>
              {locating ? (
                <ActivityIndicator color={theme.onPrimary} />
              ) : (
                <Ionicons name="navigate" size={20} color={theme.onPrimary} />
              )}
            </View>
          </View>
          <View style={styles.locateText}>
            <AppText variant="label" style={{ fontSize: 16 }}>
              {locating ? t('setup.locating') : t('setup.useLocation')}
            </AppText>
            <AppText variant="caption" muted>
              {t('setup.useLocationHint')}
            </AppText>
          </View>
          <Ionicons name="chevron-forward" size={20} color={theme.primary} />
        </PressableScale>
      )}
      {gps && !gps.ok && (
        <Animated.View entering={motion(FadeIn.duration(200))}>
          <AppText variant="caption" style={{ color: theme.warning, fontFamily: fonts.medium }}>
            {
              {
                denied: t('setup.locationDenied'),
                servicesOff: t('setup.locationServicesOff'),
                unavailable: t('setup.locationUnavailable'),
                offline: t('setup.locationOffline'),
                far: t('setup.locationFar'),
              }[gps.reason]
            }
          </AppText>
        </Animated.View>
      )}
      {!found && (
        <AppText variant="overline" muted style={styles.or}>
          {t('setup.orSearch')}
        </AppText>
      )}
    </View>
  );

  return (
    <View style={styles.screen}>
      <ScreenHeader title={t('setup.locationTitle')} subtitle={t('setup.locationHint')} />

      {!data ? (
        <View style={styles.center}>
          {error ? <Button title={t('common.retry')} onPress={refresh} /> : <ActivityIndicator color={theme.primary} />}
        </View>
      ) : (
        <FlatList
          data={found ? [] : results}
          keyExtractor={(loc) => loc.id}
          keyboardShouldPersistTaps="handled"
          contentContainerStyle={styles.list}
          ListHeaderComponent={
            <View style={styles.header}>
              {gpsCard}
              {!found && <SearchField value={query} onChangeText={setQuery} placeholder={t('setup.locationPlaceholder')} />}
            </View>
          }
          renderItem={({ item }) => (
            <Animated.View entering={motion(FadeIn.duration(180))}>
              <ListRow
                title={item.name}
                subtitle={`${item.district} sen. · ${item.type}`}
                selected={item.id === current}
                onPress={() => pick(item.id)}
                icon={
                  <View style={[styles.pin, { backgroundColor: theme.surfaceMuted }]}>
                    <Ionicons name="location" size={18} color={theme.primary} />
                  </View>
                }
              />
            </Animated.View>
          )}
          ListEmptyComponent={
            deferred && !found ? (
              <AppText muted style={styles.empty}>
                {t('setup.locationNone')}
              </AppText>
            ) : undefined
          }
          ListFooterComponent={
            found ? undefined : (
              <View style={styles.manual}>
                <Button
                  variant="secondary"
                  icon="calendar"
                  title={t('custom.notListed')}
                  onPress={() => {
                    useSettings.getState().startCustomPlace();
                    router.push('/setup/custom');
                  }}
                />
                <Button
                  variant="ghost"
                  title={t('setup.manualLink')}
                  onPress={() => router.push({ pathname: '/select/[kind]', params: { kind: 'household', flow: 'manual' } })}
                />
              </View>
            )
          }
        />
      )}
    </View>
  );
}

/**
 * A ring that keeps growing out of the location icon and fading, to draw the eye to the button.
 * None when the phone's animations are off.
 */
function Pulse({ color }: { color: string }) {
  const reduced = useReducedMotion();
  const progress = useSharedValue(0);
  useEffect(() => {
    if (reduced) return;
    progress.value = withRepeat(withTiming(1, { duration: 1600, easing: Easing.out(Easing.quad) }), -1, false);
    return () => cancelAnimation(progress);
  }, [reduced, progress]);
  const style = useAnimatedStyle(() => ({
    opacity: 0.45 * (1 - progress.value),
    transform: [{ scale: 1 + progress.value * 0.7 }],
  }));
  if (reduced) return null;
  return <Animated.View pointerEvents="none" style={[styles.pulse, { backgroundColor: color }, style]} />;
}

const styles = StyleSheet.create({
  screen: { flex: 1 },
  header: { gap: spacing.md, marginBottom: spacing.xs },
  gps: { gap: spacing.sm + 2 },
  locate: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.md,
    padding: spacing.md,
    borderRadius: radius.lg,
    borderWidth: 2,
  },
  locateIcon: { width: 44, height: 44, alignItems: 'center', justifyContent: 'center' },
  locateCircle: { width: 44, height: 44, borderRadius: 22, alignItems: 'center', justifyContent: 'center' },
  locateText: { flex: 1, gap: 2 },
  pulse: { position: 'absolute', top: 0, right: 0, bottom: 0, left: 0, borderRadius: 22 },
  found: { gap: spacing.xs, padding: spacing.lg, borderRadius: radius.lg, borderWidth: 2 },
  foundActions: { gap: spacing.xs, marginTop: spacing.md },
  or: { textAlign: 'center', marginTop: spacing.xs },
  list: { paddingHorizontal: spacing.lg, paddingBottom: spacing.xxl, gap: spacing.sm },
  pin: { width: 40, height: 40, borderRadius: radius.sm, alignItems: 'center', justifyContent: 'center' },
  center: { flex: 1, alignItems: 'center', justifyContent: 'center' },
  empty: { paddingVertical: spacing.md },
  manual: { marginTop: spacing.md, gap: spacing.xs },
});
