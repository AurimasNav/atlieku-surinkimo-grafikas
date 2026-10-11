import { Ionicons } from '@expo/vector-icons';
import * as Haptics from 'expo-haptics';
import { router } from 'expo-router';
import type { ReactNode } from 'react';
import {
  Platform,
  Pressable,
  type PressableProps,
  type StyleProp,
  StyleSheet,
  Text,
  TextInput,
  type TextInputProps,
  type TextProps,
  View,
  type ViewProps,
  type ViewStyle,
} from 'react-native';
import Animated, { useAnimatedStyle, useSharedValue, withSpring } from 'react-native-reanimated';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import type { WasteKind } from '@/lib/schedule';
import { fonts, kindIcons, kindPalette, radius, spacing, useTheme } from '@/theme';

type Variant = 'display' | 'title' | 'heading' | 'body' | 'label' | 'caption' | 'overline';

const variants = StyleSheet.create({
  display: { fontFamily: fonts.heavy, fontSize: 44, lineHeight: 48, letterSpacing: -1.2 },
  title: { fontFamily: fonts.heavy, fontSize: 30, lineHeight: 36, letterSpacing: -0.6 },
  heading: { fontFamily: fonts.bold, fontSize: 19, lineHeight: 25, letterSpacing: -0.2 },
  body: { fontFamily: fonts.regular, fontSize: 16, lineHeight: 23 },
  label: { fontFamily: fonts.bold, fontSize: 15, lineHeight: 20 },
  caption: { fontFamily: fonts.regular, fontSize: 13, lineHeight: 18 },
  overline: { fontFamily: fonts.bold, fontSize: 12, lineHeight: 16, letterSpacing: 1.2, textTransform: 'uppercase' },
});

export function AppText({
  variant = 'body',
  muted,
  style,
  ...rest
}: TextProps & { variant?: Variant; muted?: boolean }) {
  const theme = useTheme();
  return <Text style={[variants[variant], { color: muted ? theme.textMuted : theme.text }, style]} {...rest} />;
}

/** Pressable that springs down slightly when touched. */
export function PressableScale({
  style,
  wrapperStyle,
  haptic,
  onPress,
  ...rest
}: Omit<PressableProps, 'style'> & {
  style?: StyleProp<ViewStyle>;
  /** Layout for the touch area itself, e.g. { flexShrink: 1 } so long text can truncate. */
  wrapperStyle?: StyleProp<ViewStyle>;
  haptic?: 'light' | 'select';
}) {
  const scale = useSharedValue(1);
  const animated = useAnimatedStyle(() => ({ transform: [{ scale: scale.get() }] }));
  return (
    <Pressable
      style={wrapperStyle}
      onPressIn={() => scale.set(withSpring(0.96, { damping: 20, stiffness: 400 }))}
      onPressOut={() => scale.set(withSpring(1, { damping: 15, stiffness: 300 }))}
      onPress={(event) => {
        if (haptic && Platform.OS !== 'web') {
          if (haptic === 'select') Haptics.selectionAsync();
          else Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light);
        }
        onPress?.(event);
      }}
      {...rest}>
      <Animated.View style={[style, animated]}>{rest.children as ReactNode}</Animated.View>
    </Pressable>
  );
}

export function Card({ style, ...rest }: ViewProps) {
  const theme = useTheme();
  return <View style={[styles.card, { backgroundColor: theme.surface }, style]} {...rest} />;
}

export function Button({
  title,
  icon,
  variant = 'primary',
  style,
  ...rest
}: Omit<PressableProps, 'style' | 'children'> & {
  title: string;
  icon?: keyof typeof Ionicons.glyphMap;
  variant?: 'primary' | 'secondary' | 'inverse' | 'ghost';
  style?: StyleProp<ViewStyle>;
}) {
  const theme = useTheme();
  const colors = {
    primary: [theme.primary, theme.onPrimary],
    secondary: [theme.surfaceMuted, theme.text],
    inverse: ['#FFFFFF', '#0A4A31'],
    ghost: ['transparent', theme.primary],
  }[variant];
  return (
    <PressableScale
      accessibilityRole="button"
      haptic="light"
      style={[styles.button, { backgroundColor: colors[0] }, variant === 'ghost' && styles.buttonGhost, style]}
      {...rest}>
      {icon && <Ionicons name={icon} size={20} color={colors[1]} />}
      <Text style={[variants.label, { color: colors[1], fontSize: 16 }]}>{title}</Text>
    </PressableScale>
  );
}

export function KindBadge({ kind, label, size = 'md' }: { kind: WasteKind; label: string; size?: 'sm' | 'md' }) {
  const palette = kindPalette[kind];
  const small = size === 'sm';
  return (
    <View style={[styles.badge, small && styles.badgeSmall, { backgroundColor: palette.solid }]}>
      <Ionicons name={kindIcons[kind]} size={small ? 12 : 14} color={palette.onSolid} />
      <Text style={[variants.label, { color: palette.onSolid, fontSize: small ? 12 : 13 }]}>{label}</Text>
    </View>
  );
}

export function KindIcon({ kind, size = 44 }: { kind: WasteKind; size?: number }) {
  const palette = kindPalette[kind];
  return (
    <View
      style={{
        width: size,
        height: size,
        borderRadius: size / 2.6,
        backgroundColor: palette.solid,
        alignItems: 'center',
        justifyContent: 'center',
      }}>
      <Ionicons name={kindIcons[kind]} size={size * 0.48} color={palette.onSolid} />
    </View>
  );
}

/** Selectable filter pill with an optional colour dot and counter. */
export function Chip({
  label,
  selected,
  color,
  count,
  onPress,
}: {
  label: string;
  selected: boolean;
  color?: string;
  count?: number;
  onPress: () => void;
}) {
  const theme = useTheme();
  return (
    <PressableScale
      haptic="select"
      onPress={onPress}
      accessibilityRole="tab"
      accessibilityState={{ selected }}
      style={[
        styles.chip,
        { backgroundColor: selected ? theme.text : theme.surface, borderColor: selected ? theme.text : theme.border },
      ]}>
      {color && <View style={[styles.dot, { backgroundColor: color }]} />}
      <Text style={[variants.label, { fontSize: 14, color: selected ? theme.background : theme.text }]}>{label}</Text>
      {count !== undefined && (
        <Text style={[variants.caption, { fontFamily: fonts.bold, color: selected ? theme.background : theme.textMuted }]}>
          {count}
        </Text>
      )}
    </PressableScale>
  );
}

export function Notice({ children, action, tone = 'warning' }: { children: ReactNode; action?: ReactNode; tone?: 'warning' | 'info' }) {
  const theme = useTheme();
  const warning = tone === 'warning';
  return (
    <View style={[styles.notice, { backgroundColor: warning ? theme.warningSurface : theme.surfaceMuted }]}>
      <Ionicons
        name={warning ? 'alert-circle' : 'information-circle'}
        size={22}
        color={warning ? theme.warning : theme.textMuted}
      />
      <View style={styles.noticeBody}>
        <AppText variant="caption" style={{ color: warning ? theme.warning : theme.text, fontFamily: fonts.medium }}>
          {children}
        </AppText>
        {action}
      </View>
    </View>
  );
}

export function SearchField(props: TextInputProps) {
  const theme = useTheme();
  return (
    <View style={[styles.search, { backgroundColor: theme.surface, borderColor: theme.border }]}>
      <Ionicons name="search" size={20} color={theme.textMuted} />
      <TextInput
        placeholderTextColor={theme.textMuted}
        autoCorrect={false}
        clearButtonMode="while-editing"
        style={[variants.body, styles.input, { color: theme.text }]}
        {...props}
      />
    </View>
  );
}

export function ListRow({
  title,
  subtitle,
  icon,
  trailing,
  selected,
  onPress,
}: {
  title: string;
  subtitle?: string;
  icon?: ReactNode;
  trailing?: ReactNode;
  selected?: boolean;
  onPress?: () => void;
}) {
  const theme = useTheme();
  return (
    <PressableScale
      onPress={onPress}
      disabled={!onPress}
      haptic={onPress ? 'select' : undefined}
      accessibilityRole={onPress ? 'button' : undefined}
      accessibilityState={{ selected }}
      style={[
        styles.row,
        { backgroundColor: theme.surface, borderColor: selected ? theme.primary : 'transparent' },
      ]}>
      {icon}
      <View style={styles.rowBody}>
        <AppText variant="label">{title}</AppText>
        {subtitle ? (
          <AppText variant="caption" muted numberOfLines={3}>
            {subtitle}
          </AppText>
        ) : null}
      </View>
      {trailing ??
        (selected ? (
          <Ionicons name="checkmark-circle" size={24} color={theme.primary} />
        ) : onPress ? (
          <Ionicons name="chevron-forward" size={18} color={theme.textMuted} />
        ) : null)}
    </PressableScale>
  );
}

/** Large-title screen header with an optional back button and right-hand action. */
export function ScreenHeader({
  title,
  eyebrow,
  subtitle,
  back = true,
  right,
}: {
  title?: string;
  eyebrow?: string;
  subtitle?: string;
  back?: boolean;
  right?: ReactNode;
}) {
  const theme = useTheme();
  const insets = useSafeAreaInsets();
  return (
    <View style={[styles.header, { paddingTop: insets.top + spacing.sm }]}>
      <View style={styles.headerBar}>
        {back && router.canGoBack() ? (
          <PressableScale
            onPress={() => router.back()}
            accessibilityRole="button"
            accessibilityLabel="Back"
            style={[styles.iconButton, { backgroundColor: theme.surface }]}>
            <Ionicons name="chevron-back" size={22} color={theme.text} />
          </PressableScale>
        ) : (
          <View />
        )}
        {right}
      </View>
      {eyebrow ? (
        <AppText variant="overline" style={{ color: theme.primary }}>
          {eyebrow}
        </AppText>
      ) : null}
      {title ? <AppText variant="title">{title}</AppText> : null}
      {subtitle ? <AppText muted>{subtitle}</AppText> : null}
    </View>
  );
}

export function IconButton({
  icon,
  label,
  onPress,
}: {
  icon: keyof typeof Ionicons.glyphMap;
  label: string;
  onPress: () => void;
}) {
  const theme = useTheme();
  return (
    <PressableScale
      onPress={onPress}
      haptic="light"
      accessibilityRole="button"
      accessibilityLabel={label}
      style={[styles.iconButton, { backgroundColor: theme.surface }]}>
      <Ionicons name={icon} size={21} color={theme.text} />
    </PressableScale>
  );
}

const styles = StyleSheet.create({
  card: { borderRadius: radius.lg, padding: spacing.lg, gap: spacing.sm },
  button: {
    minHeight: 56,
    borderRadius: radius.pill,
    alignItems: 'center',
    justifyContent: 'center',
    flexDirection: 'row',
    gap: spacing.sm,
    paddingHorizontal: spacing.lg,
  },
  buttonGhost: { minHeight: 44 },
  badge: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
    borderRadius: radius.pill,
    paddingHorizontal: 12,
    paddingVertical: 6,
    alignSelf: 'flex-start',
  },
  badgeSmall: { paddingHorizontal: 9, paddingVertical: 4, gap: 4 },
  chip: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.sm,
    borderRadius: radius.pill,
    borderWidth: 1,
    paddingHorizontal: 16,
    height: 42,
  },
  dot: { width: 10, height: 10, borderRadius: 5 },
  notice: { flexDirection: 'row', gap: spacing.sm + 2, borderRadius: radius.md, padding: spacing.md },
  noticeBody: { flex: 1, gap: spacing.sm, alignItems: 'flex-start' },
  search: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.sm + 2,
    borderWidth: 1,
    borderRadius: radius.md,
    paddingHorizontal: spacing.md,
    minHeight: 56,
  },
  input: { flex: 1, paddingVertical: 14 },
  row: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.md,
    padding: spacing.md,
    borderRadius: radius.md,
    borderWidth: 2,
  },
  rowBody: { flex: 1, gap: 3 },
  header: { paddingHorizontal: spacing.lg, paddingBottom: spacing.md, gap: spacing.sm },
  headerBar: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', minHeight: 44, marginBottom: spacing.sm },
  iconButton: { width: 44, height: 44, borderRadius: 22, alignItems: 'center', justifyContent: 'center' },
});
