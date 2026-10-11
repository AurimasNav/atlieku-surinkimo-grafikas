import { Ionicons } from '@expo/vector-icons';
import { router } from 'expo-router';
import { useDeferredValue, useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { ActivityIndicator, FlatList, StyleSheet, View } from 'react-native';
import Animated, { FadeIn, FadeInDown } from 'react-native-reanimated';

import { AppText, Button, ListRow, PressableScale, ScreenHeader, SearchField } from '@/components/ui';
import { type GeolocateResult, locateHome } from '@/lib/geolocate';
import { searchLocations } from '@/lib/schedule';
import { nextSetupStep } from '@/lib/setup-flow';
import { useSchedule } from '@/store/schedule';
import { useSettings } from '@/store/settings';
import { fonts, radius, spacing, useTheme } from '@/theme';

const MAX_RESULTS = 50;

export default function ChooseLocation() {
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
        <Animated.View entering={FadeInDown.duration(300)} style={[styles.found, { backgroundColor: theme.surface, borderColor: theme.primary }]}>
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
        <PressableScale
          haptic="light"
          onPress={locate}
          disabled={locating}
          accessibilityRole="button"
          style={[styles.locate, { backgroundColor: theme.primary }]}>
          <View style={styles.locateIcon}>
            {locating ? (
              <ActivityIndicator color={theme.onPrimary} />
            ) : (
              <Ionicons name="navigate" size={22} color={theme.onPrimary} />
            )}
          </View>
          <View style={styles.locateText}>
            <AppText variant="label" style={{ color: theme.onPrimary, fontSize: 16 }}>
              {locating ? t('setup.locating') : t('setup.useLocation')}
            </AppText>
            <AppText variant="caption" style={{ color: theme.onPrimary, opacity: 0.8 }}>
              {t('setup.useLocationHint')}
            </AppText>
          </View>
        </PressableScale>
      )}
      {gps && !gps.ok && (
        <Animated.View entering={FadeIn.duration(200)}>
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
            <Animated.View entering={FadeIn.duration(180)}>
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
            ) : null
          }
          ListFooterComponent={
            found ? null : (
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
  },
  locateIcon: {
    width: 44,
    height: 44,
    borderRadius: radius.md,
    backgroundColor: 'rgba(255,255,255,0.16)',
    alignItems: 'center',
    justifyContent: 'center',
  },
  locateText: { flex: 1, gap: 2 },
  found: { gap: spacing.xs, padding: spacing.lg, borderRadius: radius.lg, borderWidth: 2 },
  foundActions: { gap: spacing.xs, marginTop: spacing.md },
  or: { textAlign: 'center', marginTop: spacing.xs },
  list: { paddingHorizontal: spacing.lg, paddingBottom: spacing.xxl, gap: spacing.sm },
  pin: { width: 40, height: 40, borderRadius: radius.sm, alignItems: 'center', justifyContent: 'center' },
  center: { flex: 1, alignItems: 'center', justifyContent: 'center' },
  empty: { paddingVertical: spacing.md },
  manual: { marginTop: spacing.md, gap: spacing.xs },
});
