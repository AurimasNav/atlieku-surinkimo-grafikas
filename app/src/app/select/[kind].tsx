import { router, useLocalSearchParams } from 'expo-router';
import { useDeferredValue, useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { ActivityIndicator, FlatList, StyleSheet, View } from 'react-native';

import { AppText, Button, KindIcon, ListRow, ScreenHeader, SearchField } from '@/components/ui';
import { toIsoDate } from '@/lib/dates';
import { type Area, searchAreas, WASTE_KINDS, type WasteKind } from '@/lib/schedule';
import { useSchedule } from '@/store/schedule';
import { useSettings } from '@/store/settings';
import { spacing, useTheme } from '@/theme';

/**
 * Fallback for places the automatic matching can't handle: pick each schedule's row by hand.
 * With flow=manual it walks through all three waste types, then finishes setup.
 */
export default function SelectRow() {
  const { kind, flow } = useLocalSearchParams<{ kind: WasteKind; flow?: 'manual' }>();
  const { t } = useTranslation();
  const theme = useTheme();
  const { data, error, refresh } = useSchedule();
  const current = useSettings((s) => s.place?.choices[kind]);
  const [query, setQuery] = useState('');
  const deferred = useDeferredValue(query);

  const results = useMemo(
    () => (data ? searchAreas(data.areas, kind, deferred, toIsoDate(new Date())) : []),
    [data, kind, deferred],
  );

  const answer = (areaId: string | null) => {
    const settings = useSettings.getState();
    // Picking rows by hand replaces any automatic location.
    if (settings.place?.locationId) useSettings.setState({ place: { choices: {} } });
    useSettings.getState().choose(kind, areaId);
    if (flow !== 'manual') return router.back();
    const nextKind = WASTE_KINDS[WASTE_KINDS.indexOf(kind) + 1];
    if (nextKind) router.push({ pathname: '/select/[kind]', params: { kind: nextKind, flow } });
    else router.push('/setup/done');
  };

  return (
    <View style={styles.screen}>
      <ScreenHeader title={t('select.title', { kind: t(`kinds.${kind}`) })} subtitle={t('select.hint')} />
      <View style={styles.search}>
        <SearchField value={query} onChangeText={setQuery} placeholder={t('select.searchPlaceholder')} />
        {data && (
          <AppText variant="caption" muted>
            {t('select.count', { count: results.length })}
          </AppText>
        )}
      </View>
      {!data ? (
        <View style={styles.center}>
          {error ? <Button title={t('common.retry')} onPress={refresh} /> : <ActivityIndicator color={theme.primary} />}
        </View>
      ) : (
        <FlatList
          data={results}
          keyExtractor={(area) => area.id}
          keyboardShouldPersistTaps="handled"
          contentContainerStyle={styles.list}
          ListEmptyComponent={<AppText muted>{t('select.noResults')}</AppText>}
          renderItem={({ item }) => (
            <ListRow
              title={item.name}
              subtitle={describe(item, t)}
              icon={<KindIcon kind={kind} size={36} />}
              selected={item.id === current}
              onPress={() => answer(item.id)}
            />
          )}
          ListFooterComponent={<Button variant="secondary" title={t('common.skip')} onPress={() => answer(null)} style={styles.skip} />}
        />
      )}
    </View>
  );
}

function describe(area: Area, t: (key: 'select.noDates', options: { note: string }) => string) {
  const meta = [area.district, area.group, area.weekday].filter(Boolean).join(' · ');
  if (!area.dates.length && area.note) return [meta, t('select.noDates', { note: area.note })].filter(Boolean).join('\n');
  return meta;
}

const styles = StyleSheet.create({
  screen: { flex: 1 },
  search: { paddingHorizontal: spacing.lg, paddingBottom: spacing.md, gap: spacing.sm },
  list: { paddingHorizontal: spacing.lg, paddingBottom: spacing.xxl, gap: spacing.sm },
  center: { flex: 1, alignItems: 'center', justifyContent: 'center' },
  skip: { marginTop: spacing.md },
});
