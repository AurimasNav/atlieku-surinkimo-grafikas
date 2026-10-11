import { Ionicons } from '@expo/vector-icons';
import { router } from 'expo-router';
import { useTranslation } from 'react-i18next';
import { ScrollView, StyleSheet, View } from 'react-native';
import Animated, { FadeInDown } from 'react-native-reanimated';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { ReminderPicker } from '@/components/reminder-picker';
import { AppText, Button, Card, KindIcon, PressableScale, ScreenHeader } from '@/components/ui';
import { toIsoDate } from '@/lib/dates';
import { useDateFormat } from '@/lib/format';
import { requestNotificationPermission } from '@/lib/notifications';
import { type KindStatus, resolvePlace } from '@/lib/resolve';
import { WASTE_KINDS } from '@/lib/schedule';
import { useSchedule } from '@/store/schedule';
import { useSettings } from '@/store/settings';
import { spacing, useTheme } from '@/theme';

export default function SetupDone() {
  const { t } = useTranslation();
  const theme = useTheme();
  const insets = useSafeAreaInsets();
  const date = useDateFormat();
  const data = useSchedule((s) => s.data);
  const place = useSettings((s) => s.place);
  const today = toIsoDate(new Date());
  const resolved = resolvePlace(data, place, today);
  const street = resolved.location?.streets?.find(([key]) => key === place?.street)?.[1];
  const placeName = [resolved.location?.name, street].filter(Boolean).join(', ') || t('custom.title');

  const describe = (status: KindStatus) => {
    if (status.status !== 'ok')
      return status.status === 'none' && status.skipped ? t('setup.skipped') : t('setup.notCollected');
    const next = status.area.dates.find((d) => d >= today);
    return next ? t('setup.nextOn', { date: date.long(next) }) : t('setup.noDates');
  };

  const finish = async () => {
    await requestNotificationPermission();
    useSettings.getState().setOnboarded();
    // Home becomes the only screen, so it has no back arrow into setup.
    router.dismissAll();
    router.replace('/');
  };

  return (
    <View style={styles.screen}>
      <ScrollView contentContainerStyle={{ paddingBottom: spacing.xl }}>
        <ScreenHeader eyebrow={placeName} title={t('setup.doneTitle')} subtitle={t('setup.doneHint')} />
        <View style={styles.content}>
          <Card style={styles.summary}>
            {WASTE_KINDS.map((kind, i) => {
              const status = resolved.kinds[kind];
              const active = status.status === 'ok';
              return (
                <Animated.View key={kind} entering={FadeInDown.delay(i * 90).duration(400)}>
                  <PressableScale
                    haptic="select"
                    accessibilityRole="button"
                    onPress={() => router.push({ pathname: '/kind/[kind]', params: { kind } })}
                    style={[styles.kindRow, { opacity: active ? 1 : 0.55 }]}>
                    <KindIcon kind={kind} />
                    <View style={styles.kindText}>
                      <AppText variant="label">{t(`kinds.${kind}`)}</AppText>
                      <AppText variant="caption" muted>
                        {describe(status)}
                      </AppText>
                    </View>
                    {active ? (
                      <Ionicons name="checkmark-circle" size={24} color={theme.primary} />
                    ) : (
                      <Ionicons name="add-circle-outline" size={24} color={theme.textMuted} />
                    )}
                  </PressableScale>
                </Animated.View>
              );
            })}
          </Card>

          <View style={styles.section}>
            <AppText variant="heading">{t('setup.remindWhen')}</AppText>
            <ReminderPicker />
          </View>
        </View>
      </ScrollView>
      <View
        style={[
          styles.footer,
          {
            paddingBottom: insets.bottom + spacing.md,
            backgroundColor: theme.background,
          },
        ]}>
        <Button title={t('setup.enable')} icon="notifications" onPress={finish} />
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  screen: { flex: 1 },
  content: { paddingHorizontal: spacing.lg, gap: spacing.xl },
  summary: { gap: spacing.lg },
  kindRow: { flexDirection: 'row', alignItems: 'center', gap: spacing.md },
  kindText: { flex: 1, gap: 2 },
  section: { gap: spacing.md },
  footer: { paddingHorizontal: spacing.lg, paddingTop: spacing.sm },
});
