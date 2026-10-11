import { Ionicons } from '@expo/vector-icons';
import { LinearGradient } from 'expo-linear-gradient';
import { router } from 'expo-router';
import { StatusBar } from 'expo-status-bar';
import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Pressable, StyleSheet, Text, View } from 'react-native';
import Animated, { FadeInDown } from 'react-native-reanimated';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { AppText, Button } from '@/components/ui';
import { LANGUAGE_NAMES, LANGUAGES, type Language, resolveLanguage } from '@/i18n';
import { WASTE_KINDS } from '@/lib/schedule';
import { useSettings } from '@/store/settings';
import { fonts, kindIcons, kindPalette, radius, spacing } from '@/theme';

const FEATURES = [
  ['location', 'onboarding.featurePlace'],
  ['notifications', 'onboarding.featureReminder'],
  ['lock-closed', 'onboarding.featurePrivate'],
] as const;

export default function Welcome() {
  const { t } = useTranslation();
  const insets = useSafeAreaInsets();
  const language = useSettings((s) => s.language);
  const setLanguage = useSettings((s) => s.setLanguage);
  const [languagesOpen, setLanguagesOpen] = useState(false);
  const options: (Language | 'system')[] = ['system', ...LANGUAGES];

  return (
    <LinearGradient
      colors={['#0F6B47', '#0A4A31', '#06301F']}
      start={{ x: 0, y: 0 }}
      end={{ x: 0.6, y: 1 }}
      style={[styles.screen, { paddingTop: insets.top + spacing.xl, paddingBottom: insets.bottom + spacing.lg }]}>
      <StatusBar style="light" />

      {/* Language before anything else: the phone may be in a language the user doesn't prefer. */}
      <View style={[styles.languageBar, { top: insets.top + spacing.sm }]}>
        <Pressable
          onPress={() => setLanguagesOpen((open) => !open)}
          accessibilityRole="button"
          accessibilityLabel={t('settings.language')}
          style={styles.languageButton}>
          <Ionicons name="globe-outline" size={16} color="#FFFFFF" />
          <Text style={styles.languageText}>{LANGUAGE_NAMES[resolveLanguage(language)]}</Text>
          <Ionicons name={languagesOpen ? 'chevron-up' : 'chevron-down'} size={14} color="#FFFFFF" />
        </Pressable>
        {languagesOpen && (
          <Animated.View entering={FadeInDown.duration(200)} style={styles.languageList}>
            {options.map((code) => {
              const selected = code === language;
              return (
                <Pressable
                  key={code}
                  onPress={() => {
                    setLanguage(code);
                    setLanguagesOpen(false);
                  }}
                  accessibilityRole="radio"
                  accessibilityState={{ selected }}
                  style={[styles.languageOption, selected && styles.languageOptionSelected]}>
                  <Text style={[styles.languageText, selected && styles.languageTextSelected]}>
                    {code === 'system' ? t('settings.systemLanguage') : LANGUAGE_NAMES[code]}
                  </Text>
                </Pressable>
              );
            })}
          </Animated.View>
        )}
      </View>

      {/* Three container tiles: a playful nod to the three bins the app tracks. */}
      <Animated.View entering={FadeInDown.duration(500)} style={styles.tiles}>
        {WASTE_KINDS.map((kind, i) => (
          <View
            key={kind}
            style={[
              styles.tile,
              { backgroundColor: kindPalette[kind].solid, transform: [{ rotate: `${(i - 1) * 8}deg` }, { translateY: i === 1 ? -10 : 0 }] },
            ]}>
            <Ionicons name={kindIcons[kind]} size={30} color={kindPalette[kind].onSolid} />
          </View>
        ))}
      </Animated.View>

      <View style={styles.body}>
        <Animated.View entering={FadeInDown.delay(120).duration(500)}>
          <AppText variant="display" style={styles.title}>
            {t('onboarding.title')}
          </AppText>
          <AppText style={styles.subtitle}>{t('onboarding.body')}</AppText>
        </Animated.View>

        <View style={styles.features}>
          {FEATURES.map(([icon, key], i) => (
            <Animated.View key={key} entering={FadeInDown.delay(240 + i * 80).duration(450)} style={styles.feature}>
              <View style={styles.featureIcon}>
                <Ionicons name={icon} size={18} color="#C8F169" />
              </View>
              <AppText variant="label" style={styles.featureText}>
                {t(key)}
              </AppText>
            </Animated.View>
          ))}
        </View>
      </View>

      <Animated.View entering={FadeInDown.delay(520).duration(450)} style={styles.footer}>
        <Button variant="inverse" title={t('onboarding.start')} icon="arrow-forward" onPress={() => router.push('/setup/location')} />
        <AppText variant="caption" style={styles.disclaimer}>
          {t('onboarding.disclaimer')}
        </AppText>
      </Animated.View>
    </LinearGradient>
  );
}

const styles = StyleSheet.create({
  screen: { flex: 1, paddingHorizontal: spacing.lg },
  languageBar: { position: 'absolute', right: spacing.lg, alignItems: 'flex-end', zIndex: 1, gap: spacing.sm },
  languageButton: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
    height: 36,
    paddingHorizontal: 14,
    borderRadius: radius.pill,
    backgroundColor: 'rgba(255,255,255,0.14)',
  },
  languageList: { backgroundColor: 'rgba(6,48,31,0.96)', borderRadius: radius.md, padding: 6, gap: 2 },
  languageOption: { paddingHorizontal: 14, paddingVertical: 10, borderRadius: radius.sm },
  languageOptionSelected: { backgroundColor: '#FFFFFF' },
  languageText: { color: '#FFFFFF', fontFamily: fonts.bold, fontSize: 14 },
  languageTextSelected: { color: '#0A4A31' },
  tiles: { flexDirection: 'row', gap: spacing.sm + 4, marginTop: spacing.lg, marginBottom: spacing.xl },
  tile: {
    width: 68,
    height: 68,
    borderRadius: radius.md + 4,
    alignItems: 'center',
    justifyContent: 'center',
  },
  body: { flex: 1, gap: spacing.xl },
  title: { color: '#FFFFFF', fontSize: 52, lineHeight: 56 },
  subtitle: { color: 'rgba(255,255,255,0.78)', fontSize: 18, lineHeight: 26, marginTop: spacing.md },
  features: { gap: spacing.md },
  feature: { flexDirection: 'row', alignItems: 'center', gap: spacing.md },
  featureIcon: {
    width: 36,
    height: 36,
    borderRadius: 12,
    backgroundColor: 'rgba(200,241,105,0.14)',
    alignItems: 'center',
    justifyContent: 'center',
  },
  featureText: { color: '#FFFFFF', flex: 1 },
  footer: { gap: spacing.md },
  disclaimer: { color: 'rgba(255,255,255,0.55)', textAlign: 'center' },
});
