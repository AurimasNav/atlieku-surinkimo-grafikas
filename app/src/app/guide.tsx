import { Ionicons, MaterialCommunityIcons } from '@expo/vector-icons';
import * as WebBrowser from 'expo-web-browser';
import { useDeferredValue, useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { FlatList, ScrollView, StyleSheet, View } from 'react-native';
import Animated, { FadeIn } from 'react-native-reanimated';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { AppText, Button, Card, Chip, KindIcon, PressableScale, ScreenHeader, SearchField } from '@/components/ui';
import { toIsoDate } from '@/lib/dates';
import {
  type Advice,
  advise,
  availableKinds,
  type Destination,
  displayName,
  GUIDE_CATEGORIES,
  type GuideCategory,
  type GuideItem,
  type GuideLanguage,
  guideItem,
  guideLanguage,
  isKind,
  locationsUrl,
  type OffCurb,
  POPULAR,
  type Region,
  regionOf,
  searchGuide,
} from '@/lib/guide';
import { useMotion } from '@/lib/motion';
import { placeLabel, resolvePlace, sourcePageUrl } from '@/lib/resolve';
import { useSchedule } from '@/store/schedule';
import { useSettings } from '@/store/settings';
import { fonts, radius, spacing, useTheme } from '@/theme';

const OFF_CURB_ICONS = {
  deposit: 'recycle',
  shop: 'storefront-outline',
  site: 'warehouse',
  greenSite: 'tree-outline',
  textile: 'tshirt-crew-outline',
  pharmacy: 'pill',
  compost: 'sprout-outline',
  orangeBag: 'sack',
} as const satisfies Record<OffCurb, keyof typeof MaterialCommunityIcons.glyphMap>;

/** The colour of Vilniaus r.'s food waste bags. */
const ORANGE = { solid: '#FF8A1F', onSolid: '#3B1D00' };

/**
 * "Which bin?": search or browse items and see where each goes at the user's place, with the
 * fallback when the place has no such container (see lib/guide.ts). Works offline.
 */
export default function Guide() {
  const { t, i18n } = useTranslation();
  const insets = useSafeAreaInsets();
  const language = guideLanguage(i18n.language);
  const data = useSchedule((s) => s.data);
  const place = useSettings((s) => s.place);
  const [query, setQuery] = useState('');
  const deferred = useDeferredValue(query);
  const [category, setCategory] = useState<GuideCategory>();
  const [open, setOpen] = useState<string>();

  const resolved = useMemo(() => resolvePlace(data, place, toIsoDate(new Date())), [data, place]);
  const region = regionOf(place, resolved);
  // Without the data every official container would look missing.
  const available = data ? availableKinds(place, resolved) : undefined;
  const placeName = placeLabel(place, resolved).name;
  const browsing = !deferred.trim() && !category;
  const results = useMemo(
    () =>
      browsing
        ? POPULAR.map(guideItem).filter((item): item is GuideItem => Boolean(item))
        : searchGuide(deferred, language, category),
    [browsing, deferred, language, category],
  );

  return (
    <FlatList
      data={results}
      keyExtractor={(item) => item.id}
      keyboardShouldPersistTaps="handled"
      keyboardDismissMode="on-drag"
      contentContainerStyle={[styles.list, { paddingBottom: insets.bottom + spacing.xl }]}
      ListHeaderComponent={
        <>
          <ScreenHeader title={t('guide.title')} subtitle={t('guide.subtitle')} />
          <View style={styles.top}>
            <SearchField
              value={query}
              onChangeText={setQuery}
              placeholder={t('guide.searchPlaceholder')}
              accessibilityLabel={t('guide.title')}
              returnKeyType="search"
            />
            <AppText variant="caption" muted>
              {region && placeName ? t('guide.forPlace', { place: placeName }) : t('guide.general')}
            </AppText>
          </View>
          <ScrollView
            horizontal
            showsHorizontalScrollIndicator={false}
            keyboardShouldPersistTaps="handled"
            contentContainerStyle={styles.chips}>
            {GUIDE_CATEGORIES.map((value) => (
              <Chip
                key={value}
                label={t(`guide.categories.${value}`)}
                selected={category === value}
                onPress={() => setCategory(category === value ? undefined : value)}
              />
            ))}
          </ScrollView>
          {browsing && (
            <AppText variant="overline" muted style={styles.sectionTitle}>
              {t('guide.popular')}
            </AppText>
          )}
        </>
      }
      ListEmptyComponent={
        <AppText muted style={styles.empty}>
          {t('guide.noResults')}
        </AppText>
      }
      renderItem={({ item }) => (
        <GuideRow
          item={item}
          advice={advise(item, region, available)}
          language={language}
          region={region}
          open={open === item.id}
          onToggle={() => setOpen(open === item.id ? undefined : item.id)}
        />
      )}
      ListFooterComponent={
        <Card style={styles.disclaimer}>
          <AppText variant="caption" muted>
            {t('guide.disclaimer')}
          </AppText>
          {region && (
            <Button
              variant="ghost"
              icon="open-outline"
              title={t('guide.officialPage')}
              onPress={() => WebBrowser.openBrowserAsync(sourcePageUrl(data, place, resolved))}
              style={styles.official}
            />
          )}
        </Card>
      }
    />
  );
}

function useDestinationText() {
  const { t } = useTranslation();
  return {
    label: (destination: Destination) =>
      isKind(destination) ? t(`kinds.${destination}`) : t(`guide.dest.${destination}`),
    hint: (destination: Destination) =>
      isKind(destination) ? t(`kinds.${destination}Description`) : t(`guide.dest.${destination}Hint`),
  };
}

function GuideRow({
  item,
  advice,
  language,
  region,
  open,
  onToggle,
}: {
  item: GuideItem;
  advice: Advice;
  language: GuideLanguage;
  region: Region | undefined;
  open: boolean;
  onToggle: () => void;
}) {
  const { t } = useTranslation();
  const theme = useTheme();
  const motion = useMotion();
  const text = useDestinationText();

  return (
    <PressableScale
      onPress={onToggle}
      accessibilityRole="button"
      accessibilityState={{ expanded: open }}
      style={[styles.row, { backgroundColor: theme.surface }]}>
      <View style={styles.rowHead}>
        <DestinationIcon destination={advice.to[0]} size={40} />
        <View style={styles.grow}>
          <AppText variant="label">{displayName(item, language)}</AppText>
          <AppText variant="caption" muted numberOfLines={2}>
            {advice.to.map(text.label).join(' · ')}
          </AppText>
        </View>
        <Ionicons name={open ? 'chevron-up' : 'chevron-down'} size={18} color={theme.textMuted} />
      </View>
      {open && (
        <Animated.View entering={motion(FadeIn.duration(220))} style={styles.details}>
          {advice.missing && (
            <AppText variant="caption" style={{ color: theme.warning, fontFamily: fonts.medium }}>
              {t('guide.notCollected', { kind: t(`kinds.${advice.missing}`) })}
            </AppText>
          )}
          {advice.to.map((destination, index) => (
            <View key={destination} style={styles.option}>
              {index > 0 && (
                <AppText variant="overline" muted>
                  {t('guide.or')}
                </AppText>
              )}
              <DestinationLine destination={destination} region={region} />
            </View>
          ))}
          {advice.otherwise && (
            <View style={[styles.otherwise, { borderTopColor: theme.border }]}>
              <AppText variant="caption" muted style={{ fontFamily: fonts.medium }}>
                {t('guide.withoutContainer', { kind: t(`kinds.${advice.otherwise.kind}`) })}
              </AppText>
              {advice.otherwise.to.map((destination) => (
                <DestinationLine key={destination} destination={destination} region={region} />
              ))}
            </View>
          )}
          {advice.tip && (
            <View style={[styles.tip, { backgroundColor: theme.surfaceMuted }]}>
              <Ionicons name="bulb-outline" size={18} color={theme.primary} />
              <AppText variant="caption" style={styles.grow}>
                {advice.tip[language]}
              </AppText>
            </View>
          )}
        </Animated.View>
      )}
    </PressableScale>
  );
}

function DestinationLine({ destination, region }: { destination: Destination; region: Region | undefined }) {
  const { t } = useTranslation();
  const theme = useTheme();
  const text = useDestinationText();
  const url = locationsUrl(destination, region);
  return (
    <View style={styles.destination}>
      <DestinationIcon destination={destination} size={32} />
      <View style={[styles.grow, styles.destinationText]}>
        <AppText variant="label">{text.label(destination)}</AppText>
        <AppText variant="caption" muted>
          {text.hint(destination)}
        </AppText>
        {url && (
          <PressableScale
            haptic="light"
            accessibilityRole="link"
            onPress={() => WebBrowser.openBrowserAsync(url)}
            style={styles.link}>
            <AppText variant="caption" style={{ color: theme.primary, fontFamily: fonts.bold }}>
              {t('guide.locations')}
            </AppText>
            <Ionicons name="open-outline" size={14} color={theme.primary} />
          </PressableScale>
        )}
      </View>
    </View>
  );
}

function DestinationIcon({ destination, size }: { destination: Destination; size: number }) {
  const theme = useTheme();
  if (isKind(destination)) return <KindIcon kind={destination} size={size} />;
  const orange = destination === 'orangeBag';
  return (
    <View
      style={[
        styles.icon,
        { width: size, height: size, borderRadius: size / 2.6 },
        { backgroundColor: orange ? ORANGE.solid : theme.surfaceMuted },
      ]}>
      <MaterialCommunityIcons
        name={OFF_CURB_ICONS[destination]}
        size={size * 0.5}
        color={orange ? ORANGE.onSolid : theme.text}
      />
    </View>
  );
}

const styles = StyleSheet.create({
  list: { gap: spacing.sm },
  top: { paddingHorizontal: spacing.lg, gap: spacing.sm },
  chips: { flexDirection: 'row', gap: spacing.sm, paddingHorizontal: spacing.lg, paddingVertical: spacing.md },
  sectionTitle: { marginHorizontal: spacing.lg + spacing.xs },
  empty: { marginHorizontal: spacing.lg },
  row: { marginHorizontal: spacing.lg, padding: spacing.md, borderRadius: radius.md, gap: spacing.md },
  rowHead: { flexDirection: 'row', alignItems: 'center', gap: spacing.md },
  grow: { flex: 1 },
  details: { gap: spacing.md },
  option: { gap: spacing.sm },
  otherwise: { gap: spacing.sm, paddingTop: spacing.md, borderTopWidth: StyleSheet.hairlineWidth },
  destination: { flexDirection: 'row', alignItems: 'flex-start', gap: spacing.md },
  destinationText: { gap: 2 },
  link: { flexDirection: 'row', alignItems: 'center', gap: 4, paddingVertical: spacing.xs, alignSelf: 'flex-start' },
  tip: { flexDirection: 'row', gap: spacing.sm, padding: spacing.md, borderRadius: radius.sm },
  icon: { alignItems: 'center', justifyContent: 'center' },
  disclaimer: { marginHorizontal: spacing.lg, marginTop: spacing.md },
  official: { alignSelf: 'flex-start', paddingHorizontal: 0 },
});
