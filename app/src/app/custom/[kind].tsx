import { Ionicons } from '@expo/vector-icons';
import { DateTimePicker } from '@expo/ui/community/datetime-picker';
import { router, useLocalSearchParams } from 'expo-router';
import { useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Platform, ScrollView, StyleSheet, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { DateStrip } from '@/components/date-strip';
import { AppText, Button, Card, Chip, IconButton, ScreenHeader } from '@/components/ui';
import { customDates, customPreview, type CustomSchedule, REPEAT_OPTIONS, tidyExceptions } from '@/lib/custom-schedule';
import { parseIsoDate, toIsoDate } from '@/lib/dates';
import { useDateFormat } from '@/lib/format';
import type { WasteKind } from '@/lib/schedule';
import { useSettings } from '@/store/settings';
import { spacing, useTheme } from '@/theme';

const PREVIEW_COUNT = 8;

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

  // Holiday shifts: regular dates that don't happen, and pickups outside the rhythm.
  const [skip, setSkip] = useState<string[]>(existing?.skip ?? []);
  const [extra, setExtra] = useState<string[]>(existing?.extra ?? []);
  const [adding, setAdding] = useState(false);

  const preview = useMemo(
    () => (start ? customPreview({ start, ...repeat, skip, extra }, new Date(), PREVIEW_COUNT) : []),
    [start, repeat, skip, extra],
  );
  const toggleSkip = (iso: string) =>
    setSkip((dates) => (dates.includes(iso) ? dates.filter((d) => d !== iso) : [...dates, iso]));
  const addExtra = (picked?: Date) => {
    if (!picked) return;
    const iso = toIsoDate(picked);
    const regular = start ? customDates({ start, ...repeat }, parseIsoDate(iso)).includes(iso) : false;
    // Adding a skipped regular date is bringing it back; a regular one is already there.
    if (skip.includes(iso)) setSkip((dates) => dates.filter((d) => d !== iso));
    else if (!regular) setExtra((dates) => [...new Set([...dates, iso])]);
  };

  const save = () => {
    if (!start) return;
    useSettings.getState().setCustom(kind, tidyExceptions({ start, ...repeat, skip, extra }, new Date()));
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
              {preview.map(({ date: iso, status }) => (
                <View key={iso} style={styles.previewRow}>
                  <View style={styles.previewText}>
                    <AppText
                      variant="label"
                      muted={status === 'skipped'}
                      style={status === 'skipped' && styles.skipped}>
                      {date.long(iso)}
                    </AppText>
                    <AppText variant="caption" muted>
                      {status === 'skipped'
                        ? t('custom.skipped')
                        : status === 'extra'
                          ? `${date.relative(iso)} · ${t('custom.extra')}`
                          : date.relative(iso)}
                    </AppText>
                  </View>
                  {status === 'extra' ? (
                    <IconButton
                      icon="trash-outline"
                      label={t('custom.removeDate')}
                      onPress={() => setExtra((dates) => dates.filter((d) => d !== iso))}
                    />
                  ) : (
                    <IconButton
                      icon={status === 'skipped' ? 'arrow-undo' : 'close'}
                      label={status === 'skipped' ? t('custom.unskipDate') : t('custom.skipDate')}
                      onPress={() => toggleSkip(iso)}
                    />
                  )}
                </View>
              ))}
              {Platform.OS !== 'web' && (
                <Button variant="ghost" icon="add" title={t('custom.addDate')} onPress={() => setAdding((open) => !open)} />
              )}
              {adding &&
                (Platform.OS === 'android' ? (
                  <DateTimePicker
                    mode="date"
                    value={new Date()}
                    minimumDate={new Date()}
                    onChange={(event, picked) => {
                      setAdding(false);
                      if (event.type === 'set') addExtra(picked);
                    }}
                    onDismiss={() => setAdding(false)}
                  />
                ) : (
                  <View style={styles.inlinePicker}>
                    <DateTimePicker mode="date" display="compact" value={new Date()} minimumDate={new Date()} onValueChange={(_, picked) => addExtra(picked)} />
                    <Ionicons name="checkmark" size={22} color={theme.primary} onPress={() => setAdding(false)} />
                  </View>
                ))}
              <AppText variant="caption" muted>
                {t('custom.exceptionsHint')}
              </AppText>
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
  previewRow: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', gap: spacing.sm },
  previewText: { flex: 1, gap: 2 },
  skipped: { textDecorationLine: 'line-through' },
  inlinePicker: { flexDirection: 'row', alignItems: 'center', gap: spacing.md },
  footer: { paddingHorizontal: spacing.lg, paddingTop: spacing.sm, gap: spacing.xs },
  disabled: { opacity: 0.4 },
});
