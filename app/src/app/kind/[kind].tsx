import { Ionicons } from '@expo/vector-icons';
import { router, useLocalSearchParams } from 'expo-router';
import { useTranslation } from 'react-i18next';
import { ScrollView, StyleSheet, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { AppText, Card, ListRow, ScreenHeader } from '@/components/ui';
import { toIsoDate } from '@/lib/dates';
import { useDateFormat } from '@/lib/format';
import { resolvePlace } from '@/lib/resolve';
import type { WasteKind } from '@/lib/schedule';
import { useSchedule } from '@/store/schedule';
import { useSettings } from '@/store/settings';
import { kindPalette, radius, spacing, useTheme } from '@/theme';

/**
 * Everything about one container type in one place: what applies now, and every way to
 * change it. Opened by tapping a container type anywhere, including greyed-out ones.
 */
export default function ManageKind() {
  const { kind } = useLocalSearchParams<{ kind: WasteKind }>();
  const { t } = useTranslation();
  const theme = useTheme();
  const insets = useSafeAreaInsets();
  const date = useDateFormat();
  const data = useSchedule((s) => s.data);
  const place = useSettings((s) => s.place);
  const today = toIsoDate(new Date());
  const resolved = resolvePlace(data, place, today);
  const status = resolved.kinds[kind];

  // What the official data says for this place if the user's own answers are cleared.
  const official = resolvePlace(
    data,
    place && { ...place, choices: { ...place.choices, [kind]: undefined }, custom: { ...place.custom, [kind]: undefined } },
    today,
  ).kinds[kind];
  const hasOfficial = official.status === 'ok' || official.status === 'choose';
  const isCustom = status.status === 'ok' && status.custom;
  const skipped = status.status === 'none' && status.skipped;
  const usingOfficial = !isCustom && !skipped && place?.choices[kind] === undefined;

  const next = status.status === 'ok' ? status.area.dates.find((d) => d >= today) : undefined;
  const statusText = isCustom
    ? t('manage.statusCustom')
    : status.status === 'ok'
      ? status.area.name
      : status.status === 'choose'
        ? t('manage.statusPending')
        : skipped
          ? t('manage.statusSkipped')
          : t('manage.statusNone');

  const done = () => router.back();

  return (
    <ScrollView contentContainerStyle={{ paddingBottom: insets.bottom + spacing.xl }}>
      <ScreenHeader title={t(`kinds.${kind}`)} subtitle={t(`kinds.${kind}Description`)} />
      <View style={styles.content}>
        <Card style={[styles.status, { borderColor: kindPalette[kind].solid }]}>
          <AppText variant="label" numberOfLines={4}>
            {statusText}
          </AppText>
          {next && (
            <AppText variant="caption" muted>
              {t('setup.nextOn', { date: date.long(next) })}
            </AppText>
          )}
        </Card>

        <View style={styles.actions}>
          {hasOfficial && !usingOfficial && (
            <ListRow
              icon={<Ionicons name="checkmark-done" size={22} color={theme.primary} />}
              title={t('manage.useOfficial')}
              onPress={() => {
                useSettings.getState().resetKind(kind);
                done();
              }}
            />
          )}
          {hasOfficial && (
            <ListRow
              icon={<Ionicons name="list" size={22} color={theme.primary} />}
              title={t('manage.pickRow')}
              onPress={() =>
                official.status === 'choose'
                  ? router.push({ pathname: '/setup/choose/[kind]', params: { kind, from: 'manage' } })
                  : router.push({ pathname: '/select/[kind]', params: { kind } })
              }
            />
          )}
          <ListRow
            icon={<Ionicons name="calendar" size={22} color={theme.primary} />}
            title={isCustom ? t('manage.editCustom') : t('manage.setCustom')}
            onPress={() => router.push({ pathname: '/custom/[kind]', params: { kind } })}
          />
          {!skipped && (
            <ListRow
              icon={<Ionicons name="close-circle" size={22} color={theme.textMuted} />}
              title={t('manage.noContainer')}
              onPress={() => {
                const settings = useSettings.getState();
                settings.setCustom(kind, undefined);
                settings.choose(kind, null);
                done();
              }}
            />
          )}
        </View>

        <AppText variant="caption" muted>
          {t('manage.hint')}
        </AppText>
      </View>
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  content: { paddingHorizontal: spacing.lg, gap: spacing.lg },
  status: { gap: spacing.xs, borderLeftWidth: 6, borderRadius: radius.md },
  actions: { gap: spacing.sm },
});
