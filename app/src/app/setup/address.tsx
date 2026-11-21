import { router, useLocalSearchParams } from 'expo-router';
import { useDeferredValue, useEffect, useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { ActivityIndicator, FlatList, StyleSheet, View } from 'react-native';

import { AppText, Button, ListRow, ScreenHeader, SearchField } from '@/components/ui';
import {
  fetchKaunoAddresses,
  fetchKaunoIndex,
  type KaunoAddress,
  type KaunoAddresses,
  type KaunoIndex,
  kaunoAreas,
  kaunoKey,
} from '@/lib/kauno';
import { normalizeForSearch } from '@/lib/schedule';
import { useSchedule } from '@/store/schedule';
import { useSettings } from '@/store/settings';
import { spacing, useTheme } from '@/theme';

/**
 * Kauno r.: schedules are per address, so after the town the user picks the street and then the
 * house number, from the address file of the town's eldership.
 */
export default function ChooseAddress() {
  const { t } = useTranslation();
  const theme = useTheme();
  const params = useLocalSearchParams<{ eldership: string; eldershipName: string; town: string }>();
  const [files, setFiles] = useState<{ index: KaunoIndex; addresses: KaunoAddresses } | null>(null);
  const [failed, setFailed] = useState(false);
  const [street, setStreet] = useState<string | null>(null);
  const [query, setQuery] = useState('');
  const deferred = useDeferredValue(query);

  const [attempt, setAttempt] = useState(0);
  useEffect(() => {
    let cancelled = false;
    Promise.all([fetchKaunoIndex(), fetchKaunoAddresses(params.eldership)])
      .then(([index, addresses]) => !cancelled && setFiles({ index, addresses }))
      .catch(() => !cancelled && setFailed(true));
    return () => {
      cancelled = true;
    };
  }, [params.eldership, attempt]);
  const retry = () => {
    setFailed(false);
    setAttempt((n) => n + 1);
  };

  const streets = files?.addresses.towns[params.town];
  // A town with a single (often unnamed) street goes straight to the house numbers.
  const onlyStreet = streets && Object.keys(streets).length === 1 ? Object.keys(streets)[0] : null;
  const chosenStreet = street ?? onlyStreet;

  const options = useMemo(() => {
    const all = chosenStreet === null ? Object.keys(streets ?? {}) : Object.keys(streets?.[chosenStreet] ?? {});
    const words = normalizeForSearch(deferred).split(/\s+/).filter(Boolean);
    return all.filter((option) => words.every((word) => normalizeForSearch(option).includes(word)));
  }, [streets, chosenStreet, deferred]);

  const pickHouse = (house: string) => {
    if (!files || chosenStreet === null) return;
    const address: KaunoAddress = {
      eldership: params.eldership,
      eldershipName: params.eldershipName,
      town: params.town,
      street: chosenStreet,
      house,
    };
    useSettings.getState().setKaunoAddress(address);
    useSchedule.getState().setPersonal({
      key: kaunoKey(address),
      areas: kaunoAreas(files.index, files.addresses, address) ?? [],
      generatedAt: files.index.generatedAt,
    });
    router.push('/setup/done');
  };

  const pick = (option: string) => {
    if (chosenStreet === null) {
      setStreet(option);
      setQuery('');
    } else pickHouse(option);
  };

  const asksHouse = chosenStreet !== null;
  return (
    <View style={styles.screen}>
      <ScreenHeader
        eyebrow={asksHouse && chosenStreet ? `${params.town}, ${chosenStreet}` : params.town}
        title={asksHouse ? t('setup.houseTitle') : t('setup.streetTitle')}
        subtitle={t('setup.addressHint', { place: params.town })}
      />
      {!files ? (
        <View style={styles.center}>
          {failed ? (
            <>
              <AppText muted style={styles.failed}>
                {t('setup.addressesFailed')}
              </AppText>
              <Button title={t('common.retry')} onPress={retry} />
            </>
          ) : (
            <ActivityIndicator color={theme.primary} />
          )}
        </View>
      ) : (
        <>
          <View style={styles.search}>
            <SearchField
              value={query}
              onChangeText={setQuery}
              placeholder={asksHouse ? t('setup.housePlaceholder') : t('setup.streetPlaceholder')}
            />
          </View>
          <FlatList
            data={options}
            keyExtractor={(option) => option}
            keyboardShouldPersistTaps="handled"
            contentContainerStyle={styles.list}
            renderItem={({ item }) => (
              <ListRow title={item || (asksHouse ? t('setup.noHouse') : t('setup.noStreet'))} onPress={() => pick(item)} />
            )}
          />
        </>
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  screen: { flex: 1 },
  search: { paddingHorizontal: spacing.lg, paddingBottom: spacing.md },
  list: { paddingHorizontal: spacing.lg, paddingBottom: spacing.xxl, gap: spacing.sm },
  center: { flex: 1, alignItems: 'center', justifyContent: 'center', gap: spacing.md, padding: spacing.lg },
  failed: { textAlign: 'center' },
});
