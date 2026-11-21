import { Ionicons, MaterialCommunityIcons } from '@expo/vector-icons';
import { LinearGradient } from 'expo-linear-gradient';
import { router, useIsFocused } from 'expo-router';
import { StatusBar } from 'expo-status-bar';
import { useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Pressable, ScrollView, type ScrollViewInstance, StyleSheet, Text, View } from 'react-native';
import Animated, { FadeIn, FadeInDown, FadeOut } from 'react-native-reanimated';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { AppText, Button } from '@/components/ui';
import { LANGUAGE_NAMES, LANGUAGES, type Language, resolveLanguage } from '@/i18n';
import { useMotion } from '@/lib/motion';
import { WASTE_KINDS } from '@/lib/schedule';
import { useSettings } from '@/store/settings';
import { fonts, kindIcons, kindPalette, radius, spacing } from '@/theme';

const FEATURES = [
  ['location', 'onboarding.featurePlace'],
  ['notifications', 'onboarding.featureReminder'],
  ['lock-closed', 'onboarding.featurePrivate'],
] as const;

/** The screen's background: a gradient from the top left corner towards the bottom. */
const BACKGROUND = ['#0F6B47', '#0A4A31', '#06301F'] as const;
const BACKGROUND_END = { x: 0.6, y: 1 };

/**
 * The background's colour at a point of a screen of that size, as the gradient draws it: the
 * point projected on the line from the top left corner to BACKGROUND_END, between its colours.
 */
function backgroundAt(x: number, y: number, width: number, height: number): string {
  const [dx, dy] = [BACKGROUND_END.x * width, BACKGROUND_END.y * height];
  const t = Math.min(1, Math.max(0, (x * dx + y * dy) / (dx * dx + dy * dy || 1)));
  const scaled = t * (BACKGROUND.length - 1);
  const i = Math.min(BACKGROUND.length - 2, Math.floor(scaled));
  const [from, to] = [BACKGROUND[i], BACKGROUND[i + 1]].map((hex) => [1, 3, 5].map((k) => parseInt(hex.slice(k, k + 2), 16)));
  return `rgb(${from.map((c, k) => Math.round(c + (to[k] - c) * (scaled - i))).join(',')})`;
}

/**
 * The text fades out over the bottom of the scrolling part: strips of the background's own
 * colours, more opaque towards the bottom, so the fade has no visible edges.
 */
const FADE_STRIPS = 12;
const FADE_STRIP = 3;

export default function Welcome() {
  const motion = useMotion();
  const { t } = useTranslation();
  const insets = useSafeAreaInsets();
  const language = useSettings((s) => s.language);
  const setLanguage = useSettings((s) => s.setLanguage);
  const [languagesOpen, setLanguagesOpen] = useState(false);
  const options: (Language | 'system')[] = ['system', ...LANGUAGES];
  // This screen stays mounted under the setup screens, where white status bar icons would be
  // invisible on the light background; unmounting the StatusBar restores the app's default.
  const focused = useIsFocused();

  // Whether the scrolling part has more below what is shown.
  const scroll = useRef<ScrollViewInstance>(null);
  const size = useRef({ viewport: 0, content: 0, offset: 0 });
  const [more, setMore] = useState(false);
  const measure = (change: Partial<typeof size.current>) => {
    Object.assign(size.current, change);
    const { viewport, content, offset } = size.current;
    setMore(viewport > 0 && content - viewport - offset > spacing.md);
  };
  // Where the scrolling part ends on the screen, for the colours of the fade.
  const [screen, setScreen] = useState({ width: 0, height: 0 });
  const [bodyBottom, setBodyBottom] = useState(0);

  return (
    <LinearGradient
      colors={BACKGROUND}
      start={{ x: 0, y: 0 }}
      end={BACKGROUND_END}
      onLayout={(e) => setScreen({ width: e.nativeEvent.layout.width, height: e.nativeEvent.layout.height })}
      style={[styles.screen, { paddingTop: insets.top + spacing.xl, paddingBottom: insets.bottom + spacing.lg }]}>
      {focused && <StatusBar style="light" />}

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
          <Animated.View entering={motion(FadeInDown.duration(200))} style={styles.languageList}>
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
      <Animated.View entering={motion(FadeInDown.duration(500))} style={styles.tiles}>
        {WASTE_KINDS.map((kind, i) => (
          <View
            key={kind}
            style={[
              styles.tile,
              { backgroundColor: kindPalette[kind].solid, transform: [{ rotate: `${(i - 1) * 8}deg` }, { translateY: i === 1 ? -10 : 0 }] },
            ]}>
            <MaterialCommunityIcons name={kindIcons[kind]} size={30} color={kindPalette[kind].onSolid} />
          </View>
        ))}
      </Animated.View>

      {/* Scrolls on short screens: otherwise the features ran under the button. The features come
          before the list of areas, which grows with every district, so they stay in view; a fade
          and an arrow show that there is more below. */}
      <View style={styles.body} onLayout={(e) => setBodyBottom(e.nativeEvent.layout.y + e.nativeEvent.layout.height)}>
        <ScrollView
          ref={scroll}
          contentContainerStyle={styles.bodyContent}
          showsVerticalScrollIndicator={false}
          onLayout={(e) => measure({ viewport: e.nativeEvent.layout.height })}
          onContentSizeChange={(_, height) => measure({ content: height })}
          onScroll={(e) => measure({ offset: e.nativeEvent.contentOffset.y })}
          scrollEventThrottle={32}>
          <Animated.View entering={motion(FadeInDown.delay(120).duration(500))}>
            <AppText variant="display" style={styles.title}>
              {t('onboarding.title')}
            </AppText>
            <AppText style={styles.subtitle}>{t('onboarding.body')}</AppText>
          </Animated.View>

          <View style={styles.features}>
            {FEATURES.map(([icon, key], i) => (
              <Animated.View key={key} entering={motion(FadeInDown.delay(240 + i * 80).duration(450))} style={styles.feature}>
                <View style={styles.featureIcon}>
                  <Ionicons name={icon} size={18} color="#C8F169" />
                </View>
                <AppText variant="label" style={styles.featureText}>
                  {t(key)}
                </AppText>
              </Animated.View>
            ))}
          </View>

          <Animated.View entering={motion(FadeInDown.delay(480).duration(450))}>
            <AppText variant="caption" style={styles.areas}>
              {t('onboarding.areas', { areas: t('coverage.areas') })}
            </AppText>
          </Animated.View>
        </ScrollView>
        {more && (
          <Animated.View
            entering={motion(FadeIn.duration(200))}
            exiting={motion(FadeOut.duration(200))}
            pointerEvents="box-none"
            style={styles.more}>
            <View style={styles.fade} pointerEvents="none">
              {Array.from({ length: FADE_STRIPS }, (_, i) => {
                const y = bodyBottom - (FADE_STRIPS - i - 0.5) * FADE_STRIP;
                const color = (x: number) => backgroundAt(x, y, screen.width, screen.height);
                return (
                  <LinearGradient
                    key={i}
                    colors={[color(0), color(screen.width)]}
                    start={{ x: 0, y: 0 }}
                    end={{ x: 1, y: 0 }}
                    style={{ height: FADE_STRIP, opacity: (i + 1) / FADE_STRIPS }}
                  />
                );
              })}
            </View>
            <Pressable
              onPress={() => scroll.current?.scrollToEnd()}
              accessibilityRole="button"
              accessibilityLabel={t('onboarding.more')}
              hitSlop={spacing.sm}
              style={styles.moreButton}>
              <Ionicons name="chevron-down" size={18} color="#FFFFFF" />
            </Pressable>
          </Animated.View>
        )}
      </View>

      <Animated.View entering={motion(FadeInDown.delay(520).duration(450))} style={styles.footer}>
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
  body: { flex: 1 },
  bodyContent: { gap: spacing.md, paddingBottom: spacing.lg },
  title: { color: '#FFFFFF', fontSize: 52, lineHeight: 56 },
  subtitle: { color: 'rgba(255,255,255,0.78)', fontSize: 18, lineHeight: 26, marginTop: spacing.md },
  areas: { color: 'rgba(255,255,255,0.66)' },
  // Across the whole screen, so the fade has no side edges; the arrow at the text's right edge,
  // where the feature texts don't reach.
  more: {
    position: 'absolute',
    left: -spacing.lg,
    right: -spacing.lg,
    bottom: 0,
    height: FADE_STRIPS * FADE_STRIP,
    alignItems: 'flex-end',
    justifyContent: 'flex-end',
    paddingRight: spacing.lg,
  },
  fade: { ...StyleSheet.absoluteFill, justifyContent: 'flex-end' },
  moreButton: {
    width: 32,
    height: 32,
    borderRadius: 16,
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: 'rgba(255,255,255,0.18)',
  },
  features: { gap: spacing.md - 4 },
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
  footer: { gap: spacing.md, paddingTop: spacing.sm },
  disclaimer: { color: 'rgba(255,255,255,0.55)', textAlign: 'center' },
});
