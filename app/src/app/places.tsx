import { Ionicons } from '@expo/vector-icons';
import { router } from 'expo-router';
import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { ScrollView, StyleSheet, TextInput, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { Button, IconButton, ListRow, ScreenHeader } from '@/components/ui';
import { toIsoDate } from '@/lib/dates';
import { placeLabel, resolvePlace } from '@/lib/resolve';
import { useSchedule } from '@/store/schedule';
import { allPlaces, type SavedPlace, useSettings } from '@/store/settings';
import { fonts, radius, spacing, useTheme } from '@/theme';

/** Every saved place: switch between them, name them, add or remove one. */
export default function Places() {
  const { t } = useTranslation();
  const theme = useTheme();
  const insets = useSafeAreaInsets();
  const data = useSchedule((s) => s.data);
  const settings = useSettings();
  const places = allPlaces(settings);
  const [editing, setEditing] = useState<string | undefined>();
  const [draft, setDraft] = useState('');
  const today = toIsoDate(new Date());

  const describe = (saved: SavedPlace) => {
    const label = placeLabel(saved.place, resolvePlace(data, saved.place, today));
    const own = saved.place?.custom && Object.keys(saved.place.custom).length ? t('custom.title') : undefined;
    const official = label.name ?? own;
    return {
      title: saved.name ?? official ?? t('places.new'),
      subtitle: [saved.name && official, label.detail].filter(Boolean).join(' · ') || undefined,
    };
  };
  const startEditing = (saved: SavedPlace) => {
    setEditing(saved.id);
    setDraft(saved.name ?? '');
  };

  return (
    <ScrollView
      contentContainerStyle={{ paddingBottom: insets.bottom + spacing.xl }}
      keyboardShouldPersistTaps="handled">
      <ScreenHeader title={t('places.title')} subtitle={t('places.hint')} />
      <View style={styles.content}>
        {places.map((saved) => {
          const current = saved.id === settings.placeId;
          const { title, subtitle } = describe(saved);
          return (
            <View key={saved.id} style={styles.place}>
              <ListRow
                title={title}
                subtitle={subtitle}
                selected={current}
                icon={<Ionicons name={current ? 'location' : 'location-outline'} size={22} color={theme.primary} />}
                onPress={() => {
                  if (!current) settings.switchPlace(saved.id);
                  router.back();
                }}
                trailing={
                  <IconButton icon="create-outline" label={t('places.rename')} onPress={() => startEditing(saved)} />
                }
              />
              {editing === saved.id && (
                <View style={[styles.editor, { backgroundColor: theme.surface }]}>
                  <TextInput
                    value={draft}
                    onChangeText={setDraft}
                    placeholder={t('places.namePlaceholder')}
                    placeholderTextColor={theme.textMuted}
                    autoFocus
                    maxLength={40}
                    returnKeyType="done"
                    onSubmitEditing={() => {
                      settings.renamePlace(saved.id, draft);
                      setEditing(undefined);
                    }}
                    style={[styles.input, { color: theme.text, borderColor: theme.border }]}
                  />
                  <View style={styles.editorActions}>
                    <Button
                      title={t('places.save')}
                      onPress={() => {
                        settings.renamePlace(saved.id, draft);
                        setEditing(undefined);
                      }}
                    />
                    {current && (
                      <Button
                        variant="secondary"
                        icon="swap-horizontal"
                        title={t('places.change')}
                        onPress={() => router.push('/setup/location')}
                      />
                    )}
                    {places.length > 1 && (
                      <Button
                        variant="ghost"
                        icon="trash-outline"
                        title={t('places.remove')}
                        onPress={() => {
                          settings.removePlace(saved.id);
                          setEditing(undefined);
                        }}
                      />
                    )}
                  </View>
                </View>
              )}
            </View>
          );
        })}
        <Button
          variant="secondary"
          icon="add"
          title={t('places.add')}
          onPress={() => {
            settings.addPlace();
            router.push('/setup/location');
          }}
        />
      </View>
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  content: { paddingHorizontal: spacing.lg, gap: spacing.md },
  place: { gap: spacing.sm },
  editor: { borderRadius: radius.md, padding: spacing.md, gap: spacing.md },
  input: {
    borderWidth: 1,
    borderRadius: radius.sm,
    paddingHorizontal: spacing.md,
    minHeight: 48,
    fontFamily: fonts.regular,
    fontSize: 16,
  },
  editorActions: { gap: spacing.sm },
});
