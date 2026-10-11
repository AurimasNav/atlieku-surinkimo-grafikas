import { router } from 'expo-router';
import { useDeferredValue, useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { FlatList, StyleSheet, View } from 'react-native';

import { Button, ListRow, ScreenHeader, SearchField } from '@/components/ui';
import { normalizeForSearch } from '@/lib/schedule';
import { nextSetupStep } from '@/lib/setup-flow';
import { useSchedule } from '@/store/schedule';
import { useSettings } from '@/store/settings';
import { spacing } from '@/theme';

export default function ChooseStreet() {
  const { t } = useTranslation();
  const data = useSchedule((s) => s.data);
  const place = useSettings((s) => s.place);
  const location = data?.locations?.find((loc) => loc.id === place?.locationId);
  const [query, setQuery] = useState('');
  const deferred = useDeferredValue(query);

  const streets = useMemo(() => {
    const words = normalizeForSearch(deferred).split(/\s+/).filter(Boolean);
    return (location?.streets ?? []).filter(([, label]) =>
      words.every((word) => normalizeForSearch(label).includes(word)),
    );
  }, [location, deferred]);

  const pick = (street: string) => {
    if (!place?.locationId) return;
    useSettings.getState().setLocation(place.locationId, street);
    router.push(nextSetupStep(data, useSettings.getState().place));
  };

  return (
    <View style={styles.screen}>
      <ScreenHeader
        eyebrow={location?.name}
        title={t('setup.streetTitle')}
        subtitle={t('setup.streetHint', { place: location?.name })}
      />
      <View style={styles.search}>
        <SearchField value={query} onChangeText={setQuery} placeholder={t('setup.streetPlaceholder')} />
      </View>
      <FlatList
        data={streets}
        keyExtractor={([key]) => key}
        keyboardShouldPersistTaps="handled"
        contentContainerStyle={styles.list}
        renderItem={({ item: [key, label] }) => (
          <ListRow title={label} selected={place?.street === key} onPress={() => pick(key)} />
        )}
        ListFooterComponent={
          <Button variant="secondary" title={t('setup.streetNotListed')} onPress={() => pick('')} style={styles.notListed} />
        }
      />
    </View>
  );
}

const styles = StyleSheet.create({
  screen: { flex: 1 },
  search: { paddingHorizontal: spacing.lg, paddingBottom: spacing.md },
  list: { paddingHorizontal: spacing.lg, paddingBottom: spacing.xxl, gap: spacing.sm },
  notListed: { marginTop: spacing.md },
});
