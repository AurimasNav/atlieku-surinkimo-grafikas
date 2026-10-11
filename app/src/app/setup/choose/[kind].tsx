import { Ionicons } from '@expo/vector-icons';
import { router, useLocalSearchParams } from 'expo-router';
import { useTranslation } from 'react-i18next';
import { ScrollView, StyleSheet, View } from 'react-native';

import { AppText, Button, KindIcon, ListRow, PressableScale, ScreenHeader } from '@/components/ui';
import { toIsoDate } from '@/lib/dates';
import { isHousingChoice, resolvePlace } from '@/lib/resolve';
import type { Area, WasteKind } from '@/lib/schedule';
import { nextSetupStep } from '@/lib/setup-flow';
import { useSchedule } from '@/store/schedule';
import { useSettings } from '@/store/settings';
import { radius, spacing, useTheme } from '@/theme';

/** Asks which row applies when a location matches several: house vs apartment, or a list. */
export default function ChooseRow() {
  const { kind, from } = useLocalSearchParams<{ kind: WasteKind; from?: 'manage' }>();
  const { t } = useTranslation();
  const data = useSchedule((s) => s.data);
  const place = useSettings((s) => s.place);
  // Ignore an earlier answer for this kind, so the choice can be made again from Settings.
  const resolved = resolvePlace(
    data,
    place && { ...place, choices: { ...place.choices, [kind]: undefined } },
    toIsoDate(new Date()),
  );
  const status = resolved.kinds[kind];
  const candidates = status?.status === 'choose' ? status.candidates : [];
  const placeName = resolved.location?.name ?? '';

  const answer = (areaId: string | null) => {
    useSettings.getState().choose(kind, areaId);
    if (from === 'manage') router.back();
    else router.push(nextSetupStep(data, useSettings.getState().place));
  };

  if (isHousingChoice(candidates)) {
    const house = candidates.find((a) => a.group === 'Individualūs namai')!;
    const apartment = candidates.find((a) => a.group === 'Daugiabučiai namai')!;
    return (
      <View style={styles.screen}>
        <ScreenHeader eyebrow={placeName} title={t('setup.housingTitle')} subtitle={t('setup.housingHint', { place: placeName })} />
        <View style={styles.cards}>
          <HousingCard icon="home" title={t('setup.house')} hint={t('setup.houseHint')} onPress={() => answer(house.id)} />
          <HousingCard
            icon="business"
            title={t('setup.apartment')}
            hint={t('setup.apartmentHint')}
            onPress={() => answer(apartment.id)}
          />
        </View>
      </View>
    );
  }

  return (
    <View style={styles.screen}>
      <ScreenHeader
        eyebrow={placeName}
        title={t('setup.chooseTitle', { kind: t(`kinds.${kind}`).toLowerCase() })}
        subtitle={t('setup.chooseHint', { place: placeName })}
      />
      <ScrollView contentContainerStyle={styles.list}>
        {candidates.map((area: Area) => (
          <ListRow
            key={area.id}
            title={area.name}
            subtitle={[area.group, area.weekday].filter(Boolean).join(' · ')}
            icon={<KindIcon kind={kind} size={40} />}
            onPress={() => answer(area.id)}
          />
        ))}
        <Button variant="secondary" title={t('common.skip')} onPress={() => answer(null)} style={styles.skip} />
      </ScrollView>
    </View>
  );
}

function HousingCard({
  icon,
  title,
  hint,
  onPress,
}: {
  icon: keyof typeof Ionicons.glyphMap;
  title: string;
  hint: string;
  onPress: () => void;
}) {
  const theme = useTheme();
  return (
    <PressableScale haptic="select" onPress={onPress} accessibilityRole="button" style={[styles.card, { backgroundColor: theme.surface }]}>
      <View style={[styles.cardIcon, { backgroundColor: theme.primary }]}>
        <Ionicons name={icon} size={30} color={theme.onPrimary} />
      </View>
      <View style={styles.cardText}>
        <AppText variant="heading">{title}</AppText>
        <AppText variant="caption" muted>
          {hint}
        </AppText>
      </View>
      <Ionicons name="chevron-forward" size={20} color={theme.textMuted} />
    </PressableScale>
  );
}

const styles = StyleSheet.create({
  screen: { flex: 1 },
  cards: { paddingHorizontal: spacing.lg, gap: spacing.md },
  card: { flexDirection: 'row', alignItems: 'center', gap: spacing.md, padding: spacing.lg, borderRadius: radius.lg },
  cardIcon: { width: 60, height: 60, borderRadius: radius.md, alignItems: 'center', justifyContent: 'center' },
  cardText: { flex: 1, gap: 4 },
  list: { paddingHorizontal: spacing.lg, paddingBottom: spacing.xxl, gap: spacing.sm },
  skip: { marginTop: spacing.md },
});
