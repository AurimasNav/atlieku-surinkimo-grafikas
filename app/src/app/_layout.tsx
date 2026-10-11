import {
  Manrope_500Medium,
  Manrope_600SemiBold,
  Manrope_700Bold,
  Manrope_800ExtraBold,
  useFonts,
} from '@expo-google-fonts/manrope';
import { DarkTheme, DefaultTheme, type ErrorBoundaryProps, Stack, ThemeProvider, useSegments } from 'expo-router';
import * as SplashScreen from 'expo-splash-screen';
import { StatusBar } from 'expo-status-bar';
import { useEffect } from 'react';
import { useTranslation } from 'react-i18next';
import { AppState, StyleSheet, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { AppText, Button } from '@/components/ui';
import i18n, { resolveLanguage } from '@/i18n';
// Importing this module also defines the background task, which must happen at startup.
import { registerBackgroundRefresh } from '@/lib/background';
import { installCrashRecorder } from '@/lib/crash';
import { appVersion, formatError, openIssue } from '@/lib/feedback';
import { configureNotifications, syncReminders } from '@/lib/notifications';
import { useSchedule } from '@/store/schedule';
import { useSettings } from '@/store/settings';
import { spacing, useTheme } from '@/theme';

SplashScreen.preventAutoHideAsync();
installCrashRecorder(formatError, appVersion());

/** Shown instead of a screen that crashed while rendering. */
export function ErrorBoundary({ error, retry }: ErrorBoundaryProps) {
  const { t, i18n: translation } = useTranslation();
  const theme = useTheme();
  const insets = useSafeAreaInsets();
  return (
    <View
      style={[
        styles.error,
        { backgroundColor: theme.background, paddingTop: insets.top + spacing.xxl, paddingBottom: insets.bottom + spacing.lg },
      ]}>
      <View style={styles.errorText}>
        <AppText variant="title">{t('crash.title')}</AppText>
        <AppText muted>{t('crash.body')}</AppText>
      </View>
      <View style={styles.errorActions}>
        <Button icon="refresh" title={t('crash.retry')} onPress={retry} />
        <Button
          variant="secondary"
          icon="logo-github"
          title={t('crash.report')}
          onPress={() => openIssue('crash_report', { error: formatError(error), language: translation.language })}
        />
      </View>
    </View>
  );
}

export default function RootLayout() {
  const theme = useTheme();
  const insets = useSafeAreaInsets();
  const segments = useSegments();
  const language = useSettings((s) => s.language);
  const [fontsLoaded, fontError] = useFonts({
    Manrope_500Medium,
    Manrope_600SemiBold,
    Manrope_700Bold,
    Manrope_800ExtraBold,
  });

  useEffect(() => {
    if (fontsLoaded || fontError) SplashScreen.hideAsync();
  }, [fontsLoaded, fontError]);

  useEffect(() => {
    i18n.changeLanguage(resolveLanguage(language));
  }, [language]);

  useEffect(() => {
    const refreshAndSync = () => useSchedule.getState().refresh().finally(() => syncReminders());

    configureNotifications().then(refreshAndSync);
    registerBackgroundRefresh().catch(() => {});

    const appState = AppState.addEventListener('change', (state) => {
      if (state === 'active') refreshAndSync();
    });
    // Re-plan reminders whenever the inputs to the plan change.
    const unsubscribeSettings = useSettings.subscribe((state, prev) => {
      if (state.place !== prev.place || state.reminder !== prev.reminder || state.language !== prev.language) {
        syncReminders();
      }
    });
    const unsubscribeSchedule = useSchedule.subscribe((state, prev) => {
      if (state.data !== prev.data) syncReminders();
    });

    return () => {
      appState.remove();
      unsubscribeSettings();
      unsubscribeSchedule();
    };
  }, []);

  if (!fontsLoaded && !fontError) return null;

  const navigationTheme = theme.dark ? DarkTheme : DefaultTheme;
  return (
    <ThemeProvider
      value={{
        ...navigationTheme,
        colors: { ...navigationTheme.colors, background: theme.background, primary: theme.primary },
      }}>
      <StatusBar style={theme.dark ? 'light' : 'dark'} />
      <Stack
        screenOptions={{
          headerShown: false,
          contentStyle: { backgroundColor: theme.background },
          animation: 'slide_from_right',
        }}>
        <Stack.Screen name="onboarding" options={{ animation: 'fade' }} />
        <Stack.Screen name="setup/done" options={{ animation: 'fade_from_bottom' }} />
      </Stack>
      {/* Keeps scrolled content from showing through the status bar (not on the full-bleed welcome). */}
      {segments[0] !== 'onboarding' && (
        <View pointerEvents="none" style={[styles.statusBar, { height: insets.top, backgroundColor: theme.background }]} />
      )}
    </ThemeProvider>
  );
}

const styles = StyleSheet.create({
  error: { flex: 1, paddingHorizontal: spacing.lg, justifyContent: 'space-between' },
  errorText: { gap: spacing.md },
  errorActions: { gap: spacing.sm },
  statusBar: { position: 'absolute', top: 0, left: 0, right: 0 },
});
