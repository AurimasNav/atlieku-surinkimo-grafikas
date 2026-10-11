import { Ionicons } from '@expo/vector-icons';
import type { ReactNode } from 'react';
import {
  Pressable,
  type PressableProps,
  type StyleProp,
  StyleSheet,
  Text,
  type TextProps,
  View,
  type ViewProps,
  type ViewStyle,
} from 'react-native';

import type { WasteKind } from '@/lib/schedule';
import { kindColors, kindIcons, radius, spacing, useTheme } from '@/theme';

type Variant = 'title' | 'heading' | 'body' | 'caption' | 'label';

export function AppText({ variant = 'body', muted, style, ...rest }: TextProps & { variant?: Variant; muted?: boolean }) {
  const theme = useTheme();
  return <Text style={[styles[variant], { color: muted ? theme.textMuted : theme.text }, style]} {...rest} />;
}

export function Card({ style, ...rest }: ViewProps) {
  const theme = useTheme();
  return <View style={[styles.card, { backgroundColor: theme.surface, borderColor: theme.border }, style]} {...rest} />;
}

export function Button({
  title,
  variant = 'primary',
  style,
  ...rest
}: Omit<PressableProps, 'style'> & {
  title: string;
  variant?: 'primary' | 'secondary';
  style?: StyleProp<ViewStyle>;
}) {
  const theme = useTheme();
  const primary = variant === 'primary';
  return (
    <Pressable
      accessibilityRole="button"
      style={({ pressed }) => [
        styles.button,
        { backgroundColor: primary ? theme.primary : theme.surfaceMuted, opacity: pressed ? 0.8 : 1 },
        style,
      ]}
      {...rest}>
      <Text style={[styles.label, { color: primary ? theme.onPrimary : theme.text }]}>{title}</Text>
    </Pressable>
  );
}

export function KindBadge({ kind, label }: { kind: WasteKind; label: string }) {
  return (
    <View style={[styles.badge, { backgroundColor: kindColors[kind] }]}>
      <Ionicons name={kindIcons[kind]} size={14} color="#FFFFFF" />
      <Text style={styles.badgeText}>{label}</Text>
    </View>
  );
}

export function Banner({ children, action }: { children: ReactNode; action?: ReactNode }) {
  const theme = useTheme();
  return (
    <View style={[styles.banner, { backgroundColor: theme.warningSurface }]}>
      <Ionicons name="alert-circle-outline" size={20} color={theme.warning} />
      <View style={styles.bannerBody}>
        <AppText variant="caption" style={{ color: theme.warning }}>
          {children}
        </AppText>
        {action}
      </View>
    </View>
  );
}

export function ListRow({
  title,
  subtitle,
  icon,
  onPress,
}: {
  title: string;
  subtitle?: string;
  icon?: keyof typeof Ionicons.glyphMap;
  onPress?: () => void;
}) {
  const theme = useTheme();
  return (
    <Pressable
      onPress={onPress}
      disabled={!onPress}
      accessibilityRole={onPress ? 'button' : undefined}
      style={({ pressed }) => [styles.row, { opacity: pressed ? 0.6 : 1 }]}>
      {icon && <Ionicons name={icon} size={22} color={theme.primary} />}
      <View style={styles.rowBody}>
        <AppText>{title}</AppText>
        {subtitle ? (
          <AppText variant="caption" muted numberOfLines={2}>
            {subtitle}
          </AppText>
        ) : null}
      </View>
      {onPress && <Ionicons name="chevron-forward" size={18} color={theme.textMuted} />}
    </Pressable>
  );
}

const styles = StyleSheet.create({
  title: { fontSize: 30, lineHeight: 36, fontWeight: '700', letterSpacing: -0.5 },
  heading: { fontSize: 18, lineHeight: 24, fontWeight: '600' },
  body: { fontSize: 16, lineHeight: 22 },
  caption: { fontSize: 13, lineHeight: 18 },
  label: { fontSize: 16, fontWeight: '600' },
  card: {
    borderRadius: radius.lg,
    borderWidth: StyleSheet.hairlineWidth,
    padding: spacing.md,
    gap: spacing.sm,
  },
  button: {
    minHeight: 52,
    borderRadius: radius.pill,
    alignItems: 'center',
    justifyContent: 'center',
    paddingHorizontal: spacing.lg,
  },
  badge: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.xs,
    borderRadius: radius.pill,
    paddingHorizontal: 10,
    paddingVertical: 4,
    alignSelf: 'flex-start',
  },
  badgeText: { color: '#FFFFFF', fontSize: 13, fontWeight: '600' },
  banner: {
    flexDirection: 'row',
    gap: spacing.sm,
    borderRadius: radius.md,
    padding: spacing.md,
  },
  bannerBody: { flex: 1, gap: spacing.sm, alignItems: 'flex-start' },
  row: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.md,
    paddingVertical: spacing.sm + 4,
  },
  rowBody: { flex: 1, gap: 2 },
});
