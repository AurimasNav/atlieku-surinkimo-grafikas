import { Ionicons } from '@expo/vector-icons';
import * as WebBrowser from 'expo-web-browser';
import { useTranslation } from 'react-i18next';
import { StyleSheet, View } from 'react-native';

import { EKONOVUS_SCHEDULES_URL } from '@/lib/config';
import { spacing, useTheme } from '@/theme';

import { AppText, KindIcon, PressableScale } from './ui';

/**
 * Kauno r.: glass and packaging containers are emptied by UAB „Ekonovus“, not Kauno švara, and
 * its schedules are only published on its website. A row like the waste types next to it that
 * opens them. `size` is the size of the waste type icons around it.
 */
export function EkonovusLink({ size = 44, variant = 'row' }: { size?: number; variant?: 'row' | 'compact' }) {
  const { t } = useTranslation();
  const theme = useTheme();
  const small = Math.round(size * 0.68);
  const compact = variant === 'compact';
  return (
    <PressableScale
      haptic="select"
      accessibilityRole="link"
      accessibilityLabel={`${t('kauno.glassPackaging')}. ${t('kauno.ekonovus')}`}
      onPress={() => WebBrowser.openBrowserAsync(EKONOVUS_SCHEDULES_URL)}
      style={[styles.row, { gap: compact ? spacing.sm : spacing.md }]}>
      <View style={{ width: size, height: size }}>
        <View style={styles.back}>
          <KindIcon kind="packaging" size={small} />
        </View>
        <View style={[styles.front, { borderColor: theme.surface, borderRadius: small / 2.6 + 2 }]}>
          <KindIcon kind="glass" size={small} />
        </View>
      </View>
      {compact ? (
        <AppText variant="caption" numberOfLines={2} style={styles.text}>
          {`${t('kauno.glassPackaging')}: ${t('kauno.ekonovus')}`}
        </AppText>
      ) : (
        <View style={[styles.text, styles.lines]}>
          <AppText variant="label">{t('kauno.glassPackaging')}</AppText>
          <AppText variant="caption" muted>
            {t('kauno.ekonovus')}
          </AppText>
        </View>
      )}
      <Ionicons name="open-outline" size={compact ? 16 : 22} color={compact ? theme.textMuted : theme.primary} />
    </PressableScale>
  );
}

const styles = StyleSheet.create({
  row: { flexDirection: 'row', alignItems: 'center' },
  back: { position: 'absolute', top: 0, left: 0 },
  front: { position: 'absolute', right: -2, bottom: -2, borderWidth: 2 },
  text: { flex: 1 },
  lines: { gap: 2 },
});
