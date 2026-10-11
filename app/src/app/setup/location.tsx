import { Ionicons } from '@expo/vector-icons';
import { router } from 'expo-router';
import { useDeferredValue, useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { ActivityIndicator, FlatList, StyleSheet, View } from 'react-native';
import Animated, { FadeIn } from 'react-native-reanimated';

import { AppText, Button, ListRow, ScreenHeader, SearchField } from '@/components/ui';
import { searchLocations } from '@/lib/schedule';
import { nextSetupStep } from '@/lib/setup-flow';
import { useSchedule } from '@/store/schedule';
import { useSettings } from '@/store/settings';
import { radius, spacing, useTheme } from '@/theme';

const MAX_RESULTS = 50;

export default function ChooseLocation() {
  const { t } = useTranslation();
  const theme = useTheme();
  const { data, error, refresh } = useSchedule();
  const current = useSettings((s) => s.place?.locationId);
  const [query, setQuery] = useState('');
  const deferred = useDeferredValue(query);

  const results = useMemo(
    () => searchLocations(data?.locations ?? [], deferred).slice(0, MAX_RESULTS),
    [data, deferred],
  );

  const pick = (locationId: string) => {
    useSettings.getState().setLocation(locationId);
    router.push(nextSetupStep(useSchedule.getState().data, useSettings.getState().place));
  };

  return (
    <View style={styles.screen}>
      <ScreenHeader title={t('setup.locationTitle')} subtitle={t('setup.locationHint')} />
      <View style={styles.search}>
        <SearchField value={query} onChangeText={setQuery} placeholder={t('setup.locationPlaceholder')} autoFocus />
      </View>

      {!data ? (
        <View style={styles.center}>
          {error ? <Button title={t('common.retry')} onPress={refresh} /> : <ActivityIndicator color={theme.primary} />}
        </View>
      ) : (
        <FlatList
          data={results}
          keyExtractor={(loc) => loc.id}
          keyboardShouldPersistTaps="handled"
          contentContainerStyle={styles.list}
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
            deferred ? (
              <AppText muted style={styles.empty}>
                {t('setup.locationNone')}
              </AppText>
            ) : null
          }
          ListFooterComponent={
            <Button
              variant="ghost"
              title={t('setup.manualLink')}
              onPress={() => router.push({ pathname: '/select/[kind]', params: { kind: 'household', flow: 'manual' } })}
              style={styles.manual}
            />
          }
        />
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  screen: { flex: 1 },
  search: { paddingHorizontal: spacing.lg, paddingBottom: spacing.md },
  list: { paddingHorizontal: spacing.lg, paddingBottom: spacing.xxl, gap: spacing.sm },
  pin: { width: 40, height: 40, borderRadius: radius.sm, alignItems: 'center', justifyContent: 'center' },
  center: { flex: 1, alignItems: 'center', justifyContent: 'center' },
  empty: { paddingVertical: spacing.md },
  manual: { marginTop: spacing.md },
});
