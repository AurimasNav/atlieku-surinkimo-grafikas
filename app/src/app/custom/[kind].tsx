import { router, useLocalSearchParams } from 'expo-router';
import { useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { ScrollView, StyleSheet, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { DateStrip } from '@/components/date-strip';
import { AppText, Button, Card, Chip, ScreenHeader } from '@/components/ui';
import { customDates, type CustomSchedule, REPEAT_OPTIONS } from '@/lib/custom-schedule';
import { toIsoDate } from '@/lib/dates';
import { useDateFormat } from '@/lib/format';
import type { WasteKind } from '@/lib/schedule';
import { useSettings } from '@/store/settings';
import { spacing, useTheme } from '@/theme';

const PREVIEW_COUNT = 4;

/** Set up or edit the user's own schedule for one waste type. */
export default function CustomScheduleEditor() {
  const { kind } = useLocalSearchParams<{ kind: WasteKind }>();
  const { t } = useTranslation();
  const theme = useTheme();
  const insets = useSafeAreaInsets();
  const date = useDateFormat();
  const existing = useSettings((s) => s.place?.custom?.[kind]);
  const today = toIsoDate(new Date());

  // An existing schedule may have started in the past; show its next date in the picker.
  const initialStart = existing ? (customDates(existing, new Date())[0] ?? today) : undefined;
  const [start, setStart] = useState<string | undefined>(initialStart);
  const [repeat, setRepeat] = useState<Pick<CustomSchedule, 'every' | 'unit'>>(
    existing ? { every: existing.every, unit: existing.unit } : { every: 2, unit: 'week' },
  );

  const preview = useMemo(
    () => (start ? customDates({ start, ...repeat }, new Date()).slice(0, PREVIEW_COUNT) : []),
    [start, repeat],
  );

  const save = () => {
    if (!start) return;
    useSettings.getState().setCustom(kind, { start, ...repeat });
    router.back();
  };
  const remove = () => {
    useSettings.getState().setCustom(kind, undefined);
    router.back();
  };

  return (
    <View style={styles.screen}>
      <ScrollView contentContainerStyle={{ paddingBottom: spacing.xl }}>
        <ScreenHeader eyebrow={t('custom.title')} title={t(`kinds.${kind}`)} />
        <View style={styles.content}>
          <View style={styles.section}>
            <AppText variant="overline" muted>
              {t('custom.nextPickup')}
            </AppText>
            <DateStrip value={start} onChange={setStart} />
          </View>

          <View style={styles.section}>
            <AppText variant="overline" muted>
              {t('custom.repeats')}
            </AppText>
            <View style={styles.chips}>
              {REPEAT_OPTIONS.map((option) => (
                <Chip
                  key={`${option.unit}${option.every}`}
                  label={t(`custom.${option.unit}${option.every}` as 'custom.week1')}
                  selected={option.unit === repeat.unit && option.every === repeat.every}
                  onPress={() => setRepeat(option)}
                />
              ))}
            </View>
            {repeat.unit === 'month' && (
              <AppText variant="caption" muted>
                {t('custom.monthlyNote')}
              </AppText>
            )}
          </View>

          {preview.length > 0 && (
            <Card style={styles.preview}>
              <AppText variant="overline" style={{ color: theme.primary }}>
                {t('custom.preview')}
              </AppText>
              {preview.map((iso) => (
                <View key={iso} style={styles.previewRow}>
                  <AppText variant="label">{date.long(iso)}</AppText>
                  <AppText variant="caption" muted>
                    {date.relative(iso)}
                  </AppText>
                </View>
              ))}
            </Card>
          )}
        </View>
      </ScrollView>

      <View style={[styles.footer, { paddingBottom: insets.bottom + spacing.md, backgroundColor: theme.background }]}>
        <Button icon="checkmark" title={t('custom.save')} onPress={save} disabled={!start} style={!start && styles.disabled} />
        {existing && <Button variant="ghost" title={t('custom.remove')} onPress={remove} />}
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  screen: { flex: 1 },
  content: { paddingHorizontal: spacing.lg, gap: spacing.xl },
  section: { gap: spacing.sm + 2 },
  chips: { flexDirection: 'row', flexWrap: 'wrap', gap: spacing.sm },
  preview: { gap: spacing.sm },
  previewRow: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'baseline', gap: spacing.sm },
  footer: { paddingHorizontal: spacing.lg, paddingTop: spacing.sm, gap: spacing.xs },
  disabled: { opacity: 0.4 },
});
