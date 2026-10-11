import { Ionicons } from '@expo/vector-icons';
import { useTranslation } from 'react-i18next';
import { StyleSheet, Text, View } from 'react-native';

import type { WasteKind } from '@/lib/schedule';
import { fonts, kindIcons, kindPalette, radius, spacing, useTheme } from '@/theme';

import { PressableScale } from './ui';

export type KindFilterValue = 'all' | WasteKind;

/**
 * Full-width segmented control: every option is always visible, so no type hides off-screen
 * the way it would in a horizontally scrolling chip row.
 */
export function KindFilter({
  kinds,
  counts,
  value,
  onChange,
}: {
  kinds: WasteKind[];
  counts: Partial<Record<WasteKind, number>>;
  value: KindFilterValue;
  onChange: (value: KindFilterValue) => void;
}) {
  const { t } = useTranslation();
  const theme = useTheme();
  const options: KindFilterValue[] = ['all', ...kinds];

  return (
    <View accessibilityRole="tablist" style={[styles.bar, { backgroundColor: theme.surface }]}>
      {options.map((option) => {
        const selected = option === value;
        const fg = selected ? theme.background : theme.text;
        return (
          <PressableScale
            key={option}
            haptic="select"
            accessibilityRole="tab"
            accessibilityState={{ selected }}
            accessibilityLabel={option === 'all' ? t('home.filterAll') : t(`kinds.${option}`)}
            onPress={() => onChange(selected && option !== 'all' ? 'all' : option)}
            wrapperStyle={styles.segmentWrapper}
            style={[styles.segment, selected && { backgroundColor: theme.text }]}>
            {option === 'all' ? (
              <View style={[styles.icon, { backgroundColor: selected ? theme.background : theme.surfaceMuted }]}>
                <Ionicons name="apps" size={15} color={selected ? theme.text : theme.textMuted} />
              </View>
            ) : (
              <View style={[styles.icon, { backgroundColor: kindPalette[option].solid }]}>
                <Ionicons name={kindIcons[option]} size={15} color={kindPalette[option].onSolid} />
              </View>
            )}
            <Text
              numberOfLines={1}
              adjustsFontSizeToFit
              minimumFontScale={0.75}
              style={[styles.label, { color: fg }]}>
              {option === 'all' ? t('home.filterAll') : t(`kinds.${option}Short`)}
            </Text>
            {option !== 'all' && (
              <Text style={[styles.count, { color: selected ? theme.background : theme.textMuted }]}>
                {counts[option] ?? 0}
              </Text>
            )}
          </PressableScale>
        );
      })}
    </View>
  );
}

const styles = StyleSheet.create({
  bar: { flexDirection: 'row', borderRadius: radius.lg, padding: 5, gap: 4 },
  segmentWrapper: { flex: 1 },
  segment: {
    alignItems: 'center',
    justifyContent: 'center',
    gap: 4,
    paddingVertical: spacing.sm + 2,
    paddingHorizontal: 4,
    borderRadius: radius.md + 2,
    minHeight: 84,
  },
  icon: { width: 28, height: 28, borderRadius: 10, alignItems: 'center', justifyContent: 'center' },
  label: { fontFamily: fonts.bold, fontSize: 13, lineHeight: 17 },
  count: { fontFamily: fonts.bold, fontSize: 12, lineHeight: 14 },
});
