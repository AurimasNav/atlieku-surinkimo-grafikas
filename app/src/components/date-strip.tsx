import { useMemo } from 'react';
import { useTranslation } from 'react-i18next';
import { FlatList, StyleSheet, Text, View } from 'react-native';

import { toIsoDate } from '@/lib/dates';
import { fonts, radius, spacing, useTheme } from '@/theme';

import { PressableScale } from './ui';

const DAYS = 42;
const ITEM_WIDTH = 64;
const GAP = spacing.sm;

/** Horizontal day picker for the next six weeks, scrolled to the selected day. */
export function DateStrip({ value, onChange }: { value?: string; onChange: (iso: string) => void }) {
  const theme = useTheme();
  const { i18n } = useTranslation();

  const days = useMemo(() => {
    const today = new Date();
    return Array.from({ length: DAYS }, (_, i) => new Date(today.getFullYear(), today.getMonth(), today.getDate() + i));
  }, []);
  const weekday = new Intl.DateTimeFormat(i18n.language, { weekday: 'short' });
  // Some locales (e.g. Lithuanian) format short months as numbers; use the name's first letters.
  const month = new Intl.DateTimeFormat(i18n.language, { month: 'long' });
  const selectedIndex = Math.max(0, days.findIndex((d) => toIsoDate(d) === value));

  return (
    <FlatList
      horizontal
      data={days}
      keyExtractor={(d) => toIsoDate(d)}
      showsHorizontalScrollIndicator={false}
      contentContainerStyle={styles.list}
      initialScrollIndex={Math.max(0, selectedIndex - 1)}
      getItemLayout={(_, index) => ({ length: ITEM_WIDTH + GAP, offset: (ITEM_WIDTH + GAP) * index, index })}
      renderItem={({ item, index }) => {
        const iso = toIsoDate(item);
        const selected = iso === value;
        const fg = selected ? theme.background : theme.text;
        const showMonth = index === 0 || item.getDate() === 1;
        return (
          <PressableScale
            haptic="select"
            onPress={() => onChange(iso)}
            accessibilityRole="radio"
            accessibilityState={{ selected }}
            accessibilityLabel={item.toLocaleDateString(i18n.language, { weekday: 'long', month: 'long', day: 'numeric' })}
            style={[
              styles.day,
              { backgroundColor: selected ? theme.text : theme.surface, borderColor: selected ? theme.text : theme.border },
            ]}>
            <Text style={[styles.weekday, { color: selected ? theme.background : theme.textMuted }]}>
              {weekday.format(item).replace('.', '')}
            </Text>
            <Text style={[styles.date, { color: fg }]}>{item.getDate()}</Text>
            <View style={styles.monthSlot}>
              {showMonth && (
                <Text style={[styles.month, { color: selected ? theme.background : theme.primary }]}>
                  {month.format(item).slice(0, 3)}
                </Text>
              )}
            </View>
          </PressableScale>
        );
      }}
    />
  );
}

const styles = StyleSheet.create({
  list: { gap: GAP, paddingVertical: spacing.xs },
  day: {
    width: ITEM_WIDTH,
    alignItems: 'center',
    paddingVertical: spacing.sm + 2,
    borderRadius: radius.md,
    borderWidth: 1,
  },
  weekday: { fontFamily: fonts.bold, fontSize: 12, textTransform: 'capitalize' },
  date: { fontFamily: fonts.heavy, fontSize: 22, lineHeight: 28 },
  monthSlot: { height: 16, justifyContent: 'center' },
  month: { fontFamily: fonts.bold, fontSize: 11, textTransform: 'uppercase' },
});
