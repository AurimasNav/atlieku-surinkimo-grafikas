import { useTranslation } from 'react-i18next';
import { StyleSheet, View } from 'react-native';

import { formatTime, REMINDER_TIMES } from '@/lib/format';
import type { ReminderSettings } from '@/lib/reminders';
import { useSettings } from '@/store/settings';
import { spacing } from '@/theme';

import { Chip } from './ui';

/** "Evening before / That morning" plus the time, saved immediately. */
export function ReminderPicker() {
  const { t } = useTranslation();
  const reminder = useSettings((s) => s.reminder);
  const setReminder = useSettings((s) => s.setReminder);

  const setDaysBefore = (daysBefore: ReminderSettings['daysBefore']) => {
    if (daysBefore === reminder.daysBefore) return;
    const [hour, minute] = REMINDER_TIMES[daysBefore][daysBefore === 1 ? 2 : 1];
    setReminder({ daysBefore, hour, minute });
  };

  return (
    <View style={styles.wrap}>
      <View style={styles.row}>
        <Chip label={t('settings.eveningBefore')} selected={reminder.daysBefore === 1} onPress={() => setDaysBefore(1)} />
        <Chip label={t('settings.morningOf')} selected={reminder.daysBefore === 0} onPress={() => setDaysBefore(0)} />
      </View>
      <View style={styles.row}>
        {REMINDER_TIMES[reminder.daysBefore].map(([hour, minute]) => (
          <Chip
            key={formatTime(hour, minute)}
            label={formatTime(hour, minute)}
            selected={reminder.hour === hour && reminder.minute === minute}
            onPress={() => setReminder({ ...reminder, hour, minute })}
          />
        ))}
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: { gap: spacing.sm + 2 },
  row: { flexDirection: 'row', flexWrap: 'wrap', gap: spacing.sm },
});
