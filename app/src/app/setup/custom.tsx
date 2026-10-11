import { Ionicons } from '@expo/vector-icons';
import { router } from 'expo-router';
import { useTranslation } from 'react-i18next';
import { ScrollView, StyleSheet, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { AppText, Button, KindIcon, ListRow, ScreenHeader } from '@/components/ui';
import { customDates } from '@/lib/custom-schedule';
import { useDateFormat } from '@/lib/format';
import { WASTE_KINDS } from '@/lib/schedule';
import { useSettings } from '@/store/settings';
import { spacing, useTheme } from '@/theme';

/** Setup for places the official data doesn't cover: the user enters each schedule. */
export default function CustomSetup() {
  const { t } = useTranslation();
  const theme = useTheme();
  const insets = useSafeAreaInsets();
  const date = useDateFormat();
  const custom = useSettings((s) => s.place?.custom ?? {});
  const anySet = WASTE_KINDS.some((kind) => custom[kind]);

  return (
    <View style={styles.screen}>
      <ScrollView contentContainerStyle={{ paddingBottom: spacing.xl }}>
        <ScreenHeader title={t('custom.setupTitle')} subtitle={t('custom.setupHint')} />
        <View style={styles.list}>
          {WASTE_KINDS.map((kind) => {
            const schedule = custom[kind];
            const next = schedule ? customDates(schedule, new Date())[0] : undefined;
            return (
              <ListRow
                key={kind}
                icon={<KindIcon kind={kind} size={44} />}
                title={t(`kinds.${kind}`)}
                subtitle={next ? t('setup.nextOn', { date: date.long(next) }) : t('custom.notSet')}
                trailing={
                  schedule ? (
                    <Ionicons name="checkmark-circle" size={24} color={theme.primary} />
                  ) : (
                    <AppText variant="label" style={{ color: theme.primary }}>
                      {t('custom.set')}
                    </AppText>
                  )
                }
                onPress={() => router.push({ pathname: '/custom/[kind]', params: { kind } })}
              />
            );
          })}
        </View>
      </ScrollView>
      <View style={[styles.footer, { paddingBottom: insets.bottom + spacing.md }]}>
        {!anySet && (
          <AppText variant="caption" muted style={styles.center}>
            {t('custom.needOne')}
          </AppText>
        )}
        <Button
          title={t('common.continue')}
          icon="arrow-forward"
          disabled={!anySet}
          style={!anySet && styles.disabled}
          onPress={() => {
            // Containers without a schedule count as "not collected" rather than unanswered.
            const settings = useSettings.getState();
            for (const kind of WASTE_KINDS) if (!settings.place?.custom?.[kind]) settings.choose(kind, null);
            router.push('/setup/done');
          }}
        />
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  screen: { flex: 1 },
  list: { paddingHorizontal: spacing.lg, gap: spacing.sm },
  footer: { paddingHorizontal: spacing.lg, paddingTop: spacing.sm, gap: spacing.sm },
  center: { textAlign: 'center' },
  disabled: { opacity: 0.4 },
});
