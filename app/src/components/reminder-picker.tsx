import { Ionicons } from '@expo/vector-icons';
import { DateTimePicker } from '@expo/ui/community/datetime-picker';
import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Platform, StyleSheet, View } from 'react-native';

import { formatTime, REMINDER_TIMES } from '@/lib/format';
import { MAX_REMINDER_TIMES, type ReminderTime, sortTimes } from '@/lib/reminders';
import { useSettings } from '@/store/settings';
import { radius, spacing, useTheme } from '@/theme';

import { Button, Chip, IconButton } from './ui';

/** The reminders for every waste type without its own, saved immediately. */
export function ReminderPicker() {
  const reminder = useSettings((s) => s.reminder);
  const setReminder = useSettings((s) => s.setReminder);
  return <ReminderTimesEditor value={reminder.times} onChange={(times) => setReminder({ ...reminder, times })} />;
}

/** One or more reminders: "Evening before / That morning" plus the time of each. */
export function ReminderTimesEditor({ value, onChange }: { value: ReminderTime[]; onChange: (times: ReminderTime[]) => void }) {
  const { t } = useTranslation();
  const add = () => {
    const next: ReminderTime = !value.some((time) => time.daysBefore === 0)
      ? { daysBefore: 0, hour: 6, minute: 0 }
      : { daysBefore: 1, hour: 19, minute: 0 };
    onChange(sortTimes([...value, next]));
  };

  return (
    <View style={styles.list}>
      {value.map((time, index) => (
        <ReminderTimeRow
          key={index}
          value={time}
          onChange={(changed) => onChange(value.map((old, i) => (i === index ? changed : old)))}
          onRemove={value.length > 1 ? () => onChange(value.filter((_, i) => i !== index)) : undefined}
        />
      ))}
      {value.length < MAX_REMINDER_TIMES && (
        <Button variant="ghost" icon="add" title={t('settings.addReminder')} onPress={add} style={styles.add} />
      )}
    </View>
  );
}

function ReminderTimeRow({
  value,
  onChange,
  onRemove,
}: {
  value: ReminderTime;
  onChange: (time: ReminderTime) => void;
  onRemove?: () => void;
}) {
  const { t } = useTranslation();
  const theme = useTheme();
  const [picking, setPicking] = useState(false);
  const presets = REMINDER_TIMES[value.daysBefore];
  const isPreset = presets.some(([hour, minute]) => hour === value.hour && minute === value.minute);

  const setDaysBefore = (daysBefore: ReminderTime['daysBefore']) => {
    if (daysBefore === value.daysBefore) return;
    const [hour, minute] = REMINDER_TIMES[daysBefore][daysBefore === 1 ? 2 : 1];
    onChange({ daysBefore, hour, minute });
  };
  const pickerValue = new Date(2000, 0, 1, value.hour, value.minute);
  const pick = (date?: Date) => date && onChange({ ...value, hour: date.getHours(), minute: date.getMinutes() });

  return (
    <View style={[styles.row, { backgroundColor: theme.surface }]}>
      <View style={styles.line}>
        <Chip label={t('settings.eveningBefore')} selected={value.daysBefore === 1} onPress={() => setDaysBefore(1)} />
        <Chip label={t('settings.morningOf')} selected={value.daysBefore === 0} onPress={() => setDaysBefore(0)} />
        {onRemove && (
          <View style={styles.remove}>
            <IconButton icon="trash-outline" label={t('settings.removeReminder')} onPress={onRemove} />
          </View>
        )}
      </View>
      <View style={styles.line}>
        {presets.map(([hour, minute]) => (
          <Chip
            key={formatTime(hour, minute)}
            label={formatTime(hour, minute)}
            selected={value.hour === hour && value.minute === minute}
            onPress={() => onChange({ ...value, hour, minute })}
          />
        ))}
        {Platform.OS !== 'web' && (
          <Chip
            label={isPreset ? t('settings.otherTime') : formatTime(value.hour, value.minute)}
            selected={!isPreset}
            onPress={() => setPicking((open) => !open)}
          />
        )}
      </View>
      {picking &&
        (Platform.OS === 'android' ? (
          <DateTimePicker
            mode="time"
            is24Hour
            positiveButton={{ label: t('common.done') }}
            negativeButton={{ label: t('common.cancel') }}
            value={pickerValue}
            onChange={(event, date) => {
              setPicking(false);
              if (event.type === 'set') pick(date);
            }}
            onDismiss={() => setPicking(false)}
          />
        ) : (
          <View style={styles.inlinePicker}>
            <DateTimePicker mode="time" display="compact" value={pickerValue} onValueChange={(_, date) => pick(date)} />
            <Ionicons name="checkmark" size={22} color={theme.primary} onPress={() => setPicking(false)} />
          </View>
        ))}
    </View>
  );
}

const styles = StyleSheet.create({
  list: { gap: spacing.sm + 2 },
  row: { gap: spacing.sm + 2, borderRadius: radius.lg, padding: spacing.md },
  line: { flexDirection: 'row', flexWrap: 'wrap', alignItems: 'center', gap: spacing.sm },
  remove: { marginLeft: 'auto' },
  add: { alignSelf: 'flex-start' },
  inlinePicker: { flexDirection: 'row', alignItems: 'center', gap: spacing.md },
});
