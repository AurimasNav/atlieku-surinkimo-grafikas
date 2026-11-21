import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { StyleSheet, View } from 'react-native';

import { parseIsoDate, toIsoDate } from '@/lib/dates';
import { capitalize, useDateFormat } from '@/lib/format';
import type { Pickup } from '@/lib/reminders';
import { fonts, kindPalette, radius, spacing, useTheme } from '@/theme';

import { AppText, IconButton, KindIcon, PressableScale } from './ui';

const monthKey = (date: Date) => date.getFullYear() * 12 + date.getMonth();

/** The weeks of a month, Monday first, as dates or null for the days of other months. */
export function monthGrid(year: number, month: number): (string | null)[][] {
  const first = new Date(year, month, 1);
  const days = new Date(year, month + 1, 0).getDate();
  const lead = (first.getDay() + 6) % 7;
  const cells: (string | null)[] = [
    ...Array<null>(lead).fill(null),
    ...Array.from({ length: days }, (_, i) => toIsoDate(new Date(year, month, i + 1))),
  ];
  while (cells.length % 7) cells.push(null);
  return Array.from({ length: cells.length / 7 }, (_, i) => cells.slice(i * 7, i * 7 + 7));
}

/** Pickups as a month grid with a dot per waste type; tap a day to see what's collected. */
export function MonthCalendar({ pickups }: { pickups: Pickup[] }) {
  const { t, i18n } = useTranslation();
  const theme = useTheme();
  const date = useDateFormat();
  const today = toIsoDate(new Date());
  const byDate = new Map(pickups.map((pickup) => [pickup.date, pickup]));
  const firstMonth = monthKey(new Date());
  const lastMonth = Math.max(firstMonth, pickups.length ? monthKey(parseIsoDate(pickups.at(-1)!.date)) : firstMonth);
  const [shown, setShown] = useState(firstMonth);
  const [selected, setSelected] = useState<string | undefined>(pickups[0]?.date);
  const current = Math.min(Math.max(shown, firstMonth), lastMonth);
  const year = Math.floor(current / 12);
  const month = current % 12;
  const weekdays = Array.from({ length: 7 }, (_, i) =>
    capitalize(new Intl.DateTimeFormat(i18n.language, { weekday: 'narrow' }).format(new Date(2024, 0, 1 + i))),
  );
  const title = capitalize(new Intl.DateTimeFormat(i18n.language, { month: 'long', year: 'numeric' }).format(new Date(year, month, 1)));
  const chosen = selected && byDate.get(selected);
  const go = (step: number) => {
    const next = current + step;
    setShown(next);
    // Show the first pickup of that month, so a tap on the arrow already answers "when".
    const prefix = toIsoDate(new Date(Math.floor(next / 12), next % 12, 1)).slice(0, 7);
    setSelected(pickups.find((pickup) => pickup.date.startsWith(prefix))?.date);
  };

  return (
    <View style={[styles.card, { backgroundColor: theme.surface }]}>
      <View style={styles.header}>
        <IconButton icon="chevron-back" label={t('calendar.previous')} onPress={() => current > firstMonth && go(-1)} />
        <AppText variant="heading" accessibilityRole="header">
          {title}
        </AppText>
        <IconButton icon="chevron-forward" label={t('calendar.next')} onPress={() => current < lastMonth && go(1)} />
      </View>
      <View style={styles.week}>
        {weekdays.map((day, i) => (
          <AppText key={i} variant="caption" muted style={styles.weekday}>
            {day}
          </AppText>
        ))}
      </View>
      {monthGrid(year, month).map((week, w) => (
        <View key={w} style={styles.week}>
          {week.map((day, d) => {
            if (!day) return <View key={d} style={styles.cell} />;
            const pickup = byDate.get(day);
            const isSelected = day === selected;
            const past = day < today;
            return (
              <PressableScale
                key={d}
                wrapperStyle={styles.cell}
                disabled={!pickup}
                onPress={() => setSelected(day)}
                accessibilityRole={pickup ? 'button' : undefined}
                accessibilityState={{ selected: isSelected }}
                accessibilityLabel={
                  pickup ? `${date.long(day)}: ${pickup.kinds.map((kind) => t(`kinds.${kind}`)).join(', ')}` : undefined
                }
                style={[
                  styles.day,
                  isSelected && { backgroundColor: theme.text },
                  day === today && !isSelected && { borderColor: theme.primary, borderWidth: 2 },
                ]}>
                <AppText
                  style={[
                    styles.dayNumber,
                    { color: isSelected ? theme.background : past ? theme.textMuted : theme.text },
                    pickup && { fontFamily: fonts.heavy },
                  ]}>
                  {Number(day.slice(8))}
                </AppText>
                <View style={styles.dots}>
                  {pickup?.kinds.map((kind) => (
                    <View key={kind} style={[styles.dot, { backgroundColor: kindPalette[kind].solid }]} />
                  ))}
                </View>
              </PressableScale>
            );
          })}
        </View>
      ))}
      <View style={[styles.detail, { borderTopColor: theme.border }]}>
        {chosen ? (
          <>
            <AppText variant="label">{date.long(chosen.date)}</AppText>
            {chosen.kinds.map((kind) => (
              <View key={kind} style={styles.kind}>
                <KindIcon kind={kind} size={26} />
                <AppText>{t(`kinds.${kind}`)}</AppText>
              </View>
            ))}
          </>
        ) : (
          <AppText variant="caption" muted>
            {t('calendar.noPickupsMonth')}
          </AppText>
        )}
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  card: { borderRadius: radius.lg, padding: spacing.md, gap: spacing.xs },
  header: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginBottom: spacing.sm },
  week: { flexDirection: 'row' },
  weekday: { flex: 1, textAlign: 'center', fontFamily: fonts.bold },
  cell: { flex: 1, aspectRatio: 1, padding: 2 },
  day: { flex: 1, borderRadius: radius.sm, alignItems: 'center', justifyContent: 'center', gap: 3 },
  dayNumber: { fontSize: 15, lineHeight: 19 },
  dots: { flexDirection: 'row', gap: 3, height: 6 },
  dot: { width: 6, height: 6, borderRadius: 3 },
  detail: { borderTopWidth: StyleSheet.hairlineWidth, marginTop: spacing.sm, paddingTop: spacing.md, gap: spacing.sm },
  kind: { flexDirection: 'row', alignItems: 'center', gap: spacing.sm },
});
