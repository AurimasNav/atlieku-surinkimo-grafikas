import { Ionicons } from '@expo/vector-icons';
import { router } from 'expo-router';
import { useTranslation } from 'react-i18next';
import { ScrollView, StyleSheet, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';

import { AppText, Button, Card } from '@/components/ui';
import { radius, spacing, useTheme } from '@/theme';

export default function Onboarding() {
  const { t } = useTranslation();
  const theme = useTheme();

  return (
    <SafeAreaView style={[styles.screen, { backgroundColor: theme.background }]}>
      <ScrollView contentContainerStyle={styles.content}>
        <View style={[styles.icon, { backgroundColor: theme.primary }]}>
          <Ionicons name="notifications-outline" size={40} color={theme.onPrimary} />
        </View>
        <AppText variant="title">{t('onboarding.title')}</AppText>
        <AppText muted>{t('onboarding.body')}</AppText>
        <Card>
          <AppText variant="caption" muted>
            {t('onboarding.disclaimer')}
          </AppText>
        </Card>
      </ScrollView>
      <View style={styles.footer}>
        <Button
          title={t('onboarding.start')}
          onPress={() => router.push({ pathname: '/select/[kind]', params: { kind: 'household', flow: 'onboarding' } })}
        />
      </View>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  screen: { flex: 1 },
  content: { padding: spacing.lg, gap: spacing.md, paddingTop: spacing.xl * 2 },
  icon: {
    width: 80,
    height: 80,
    borderRadius: radius.lg,
    alignItems: 'center',
    justifyContent: 'center',
    marginBottom: spacing.md,
  },
  footer: { padding: spacing.lg },
});
