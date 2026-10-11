import { Ionicons } from '@expo/vector-icons';
import { router, Stack, useLocalSearchParams } from 'expo-router';
import { useDeferredValue, useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { ActivityIndicator, FlatList, Pressable, StyleSheet, TextInput, View } from 'react-native';

import { AppText, Button } from '@/components/ui';
import { requestNotificationPermission } from '@/lib/notifications';
import { type Area, searchAreas, WASTE_KINDS, type WasteKind } from '@/lib/schedule';
import { useSchedule } from '@/store/schedule';
import { useSettings } from '@/store/settings';
import { radius, spacing, useTheme } from '@/theme';

export default function SelectArea() {
  const { kind, flow } = useLocalSearchParams<{ kind: WasteKind; flow?: 'onboarding' }>();
  const { t } = useTranslation();
  const theme = useTheme();
  const { data, error, refresh } = useSchedule();
  const current = useSettings((s) => s.selections[kind]);
  const select = useSettings((s) => s.select);
  const [query, setQuery] = useState('');
  const deferredQuery = useDeferredValue(query);

  const results = useMemo(
    () => (data ? searchAreas(data.areas, kind, deferredQuery) : []),
    [data, kind, deferredQuery],
  );

  const finish = async (areaId: string | null) => {
    select(kind, areaId);
    if (flow !== 'onboarding') {
      router.back();
      return;
    }
    const nextKind = WASTE_KINDS[WASTE_KINDS.indexOf(kind) + 1];
    if (nextKind) {
      router.push({ pathname: '/select/[kind]', params: { kind: nextKind, flow } });
      return;
    }
    await requestNotificationPermission();
    useSettings.getState().setOnboarded();
    router.dismissTo('/');
  };

  return (
    <View style={styles.screen}>
      <Stack.Screen options={{ title: t('select.title', { kind: t(`kinds.${kind}`) }) }} />
      <View style={styles.header}>
        <AppText variant="caption" muted>
          {t('select.hint')}
        </AppText>
        <View style={[styles.search, { backgroundColor: theme.surface, borderColor: theme.border }]}>
          <Ionicons name="search" size={18} color={theme.textMuted} />
          <TextInput
            value={query}
            onChangeText={setQuery}
            placeholder={t('select.searchPlaceholder')}
            placeholderTextColor={theme.textMuted}
            style={[styles.input, { color: theme.text }]}
            autoCorrect={false}
            clearButtonMode="while-editing"
          />
        </View>
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
            <AreaRow area={item} selected={item.id === current} onPress={() => finish(item.id)} />
          )}
          ListFooterComponent={
            <Button variant="secondary" title={t('common.skip')} onPress={() => finish(null)} style={styles.skip} />
          }
        />
      )}
    </View>
  );
}

function AreaRow({ area, selected, onPress }: { area: Area; selected: boolean; onPress: () => void }) {
  const { t } = useTranslation();
  const theme = useTheme();
  const meta = [area.district, area.group, area.weekday].filter(Boolean).join(' · ');
  return (
    <Pressable
      onPress={onPress}
      accessibilityRole="button"
      accessibilityState={{ selected }}
      style={({ pressed }) => [
        styles.row,
        {
          backgroundColor: theme.surface,
          borderColor: selected ? theme.primary : theme.border,
          opacity: pressed ? 0.7 : 1,
        },
      ]}>
      <View style={styles.rowBody}>
        <AppText>{area.name}</AppText>
        {meta ? (
          <AppText variant="caption" muted>
            {meta}
          </AppText>
        ) : null}
        {!area.dates.length && area.note ? (
          <AppText variant="caption" style={{ color: theme.warning }}>
            {t('select.noDates', { note: area.note })}
          </AppText>
        ) : null}
      </View>
      {selected && <Ionicons name="checkmark-circle" size={22} color={theme.primary} />}
    </Pressable>
  );
}

const styles = StyleSheet.create({
  screen: { flex: 1 },
  header: { padding: spacing.md, gap: spacing.sm },
  search: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.sm,
    borderWidth: 1,
    borderRadius: radius.md,
    paddingHorizontal: spacing.md,
  },
  input: { flex: 1, fontSize: 16, paddingVertical: 12 },
  list: { paddingHorizontal: spacing.md, paddingBottom: spacing.xl, gap: spacing.sm },
  row: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.sm,
    borderWidth: 1,
    borderRadius: radius.md,
    padding: spacing.md,
  },
  rowBody: { flex: 1, gap: 4 },
  center: { flex: 1, alignItems: 'center', justifyContent: 'center' },
  skip: { marginTop: spacing.md },
});
