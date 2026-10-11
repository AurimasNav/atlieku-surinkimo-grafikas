// Generates the GitHub issue forms in .github/ISSUE_TEMPLATE, one per form and language, from
// the definitions below. GitHub can't translate a form, so the app opens the one in its
// current language (see src/lib/feedback.ts).
//
//   npm run issue-forms          writes the forms
//   npm run issue-forms:check    fails when the committed forms differ from this file (CI)
//
// Field ids must stay the same in every language: the app prefills fields by id.
import { readdirSync, readFileSync, rmSync, writeFileSync } from 'node:fs';
import { join } from 'node:path';

const outDir = join(import.meta.dirname, '..', '..', '.github', 'ISSUE_TEMPLATE');
// One set of forms per app language (src/i18n/locales/<lang>.json); every form needs them all.
const LANGUAGES = readdirSync(join(import.meta.dirname, '..', 'src', 'i18n', 'locales')).map((file) =>
  file.replace(/\.json$/, ''),
);
const OFFICIAL_SCHEDULE = 'https://www.nemenkom.lt/buitiniu-ir-pakuociu-atlieku-surinkimo-grafikas/';

const appVersion = {
  type: 'input',
  id: 'app-version',
  label: { en: 'App version', lt: 'Programėlės versija', ru: 'Версия приложения', pl: 'Wersja aplikacji' },
};
const device = {
  type: 'input',
  id: 'device',
  label: {
    en: 'Phone and system version',
    lt: 'Telefonas ir sistemos versija',
    ru: 'Телефон и версия системы',
    pl: 'Telefon i wersja systemu',
  },
};
const language = {
  type: 'input',
  id: 'language',
  label: { en: 'App language', lt: 'Programėlės kalba', ru: 'Язык приложения', pl: 'Język aplikacji' },
};
const filledByApp = {
  en: 'Filled in by the app.',
  lt: 'Užpildo programėlė.',
  ru: 'Заполняется приложением.',
  pl: 'Wypełniane przez aplikację.',
};

const FORMS = {
  bug_report: {
    title: '[Bug]: ',
    labels: ['bug'],
    name: { en: 'Report a problem', lt: 'Pranešti apie klaidą', ru: 'Сообщить о проблеме', pl: 'Zgłoś problem' },
    description: {
      en: "Something in the app doesn't work as expected.",
      lt: 'Kažkas programėlėje veikia ne taip, kaip turėtų.',
      ru: 'Что-то в приложении работает не так, как должно.',
      pl: 'Coś w aplikacji nie działa tak, jak powinno.',
    },
    intro: {
      en: 'Thanks for reporting! For wrong pickup dates, please use the **Wrong dates or address** form instead.',
      lt: 'Ačiū, kad pranešate! Jei neteisingos išvežimo datos, naudokite formą **Neteisingos datos ar adresas**.',
      ru: 'Спасибо за сообщение! Если неверны даты вывоза, воспользуйтесь формой **Неверные даты или адрес**.',
      pl: 'Dziękujemy za zgłoszenie! Jeśli daty odbioru są błędne, użyj formularza **Błędne daty lub adres**.',
    },
    fields: [
      {
        type: 'textarea',
        id: 'what-happened',
        required: true,
        label: { en: 'What happened?', lt: 'Kas nutiko?', ru: 'Что произошло?', pl: 'Co się stało?' },
        description: {
          en: 'What did you do, and what went wrong?',
          lt: 'Ką darėte ir kas nepavyko?',
          ru: 'Что вы делали и что пошло не так?',
          pl: 'Co robiłeś(-aś) i co poszło nie tak?',
        },
      },
      {
        type: 'textarea',
        id: 'expected',
        label: {
          en: 'What did you expect?',
          lt: 'Ko tikėjotės?',
          ru: 'Чего вы ожидали?',
          pl: 'Czego się spodziewałeś(-aś)?',
        },
      },
      {
        type: 'textarea',
        id: 'steps',
        label: {
          en: 'Steps to reproduce',
          lt: 'Kaip pakartoti',
          ru: 'Как воспроизвести',
          pl: 'Jak odtworzyć problem',
        },
        placeholder: {
          en: '1. Open Settings\n2. Tap …',
          lt: '1. Atidarykite nustatymus\n2. Paspauskite …',
          ru: '1. Откройте настройки\n2. Нажмите …',
          pl: '1. Otwórz ustawienia\n2. Dotknij …',
        },
      },
      {
        ...appVersion,
        description: {
          en: 'Filled in automatically when you report from the app.',
          lt: 'Užpildoma automatiškai, kai pranešate iš programėlės.',
          ru: 'Заполняется автоматически, если сообщить из приложения.',
          pl: 'Wypełniane automatycznie przy zgłoszeniu z aplikacji.',
        },
      },
      {
        ...device,
        placeholder: {
          en: 'e.g. Samsung Galaxy A54, Android 15',
          lt: 'pvz., Samsung Galaxy A54, Android 15',
          ru: 'например, Samsung Galaxy A54, Android 15',
          pl: 'np. Samsung Galaxy A54, Android 15',
        },
      },
      language,
    ],
  },

  crash_report: {
    title: '[Crash]: ',
    labels: ['bug', 'crash'],
    name: {
      en: 'Crash report',
      lt: 'Programėlės lūžimas',
      ru: 'Сбой приложения',
      pl: 'Awaria aplikacji',
    },
    description: {
      en: 'The app showed an error screen or closed unexpectedly.',
      lt: 'Programėlė parodė klaidos ekraną arba netikėtai užsidarė.',
      ru: 'Приложение показало экран ошибки или неожиданно закрылось.',
      pl: 'Aplikacja pokazała ekran błędu lub nieoczekiwanie się zamknęła.',
    },
    intro: {
      en: 'The app filled in the technical details below. They contain no personal data, but please look them over before submitting.',
      lt: 'Techninę informaciją žemiau užpildė programėlė. Joje nėra asmens duomenų, bet prieš pateikdami ją peržiūrėkite.',
      ru: 'Технические сведения ниже заполнило приложение. Личных данных в них нет, но, пожалуйста, просмотрите их перед отправкой.',
      pl: 'Poniższe dane techniczne wypełniła aplikacja. Nie zawierają danych osobowych, ale przejrzyj je przed wysłaniem.',
    },
    fields: [
      {
        type: 'textarea',
        id: 'what-were-you-doing',
        required: true,
        label: {
          en: 'What were you doing when it happened?',
          lt: 'Ką darėte, kai tai nutiko?',
          ru: 'Что вы делали, когда это произошло?',
          pl: 'Co robiłeś(-aś), gdy to się stało?',
        },
        description: {
          en: 'Any detail helps, e.g. "changed the language" or "opened the app from a reminder".',
          lt: 'Praverčia bet kokia smulkmena, pvz., „pakeičiau kalbą“ arba „atidariau programėlę iš priminimo“.',
          ru: 'Важна любая деталь, например «сменил язык» или «открыл приложение из напоминания».',
          pl: 'Każdy szczegół pomaga, np. „zmieniłem język” albo „otworzyłem aplikację z przypomnienia”.',
        },
      },
      {
        type: 'textarea',
        id: 'error',
        render: 'text',
        label: { en: 'Error details', lt: 'Klaidos informacija', ru: 'Сведения об ошибке', pl: 'Szczegóły błędu' },
        description: filledByApp,
      },
      appVersion,
      device,
      language,
    ],
  },

  schedule_problem: {
    title: '[Schedule]: ',
    labels: ['schedule-data'],
    name: {
      en: 'Wrong dates or address',
      lt: 'Neteisingos datos ar adresas',
      ru: 'Неверные даты или адрес',
      pl: 'Błędne daty lub adres',
    },
    description: {
      en: "Pickup dates are wrong, or your address can't be found or matches the wrong schedule.",
      lt: 'Neteisingos išvežimo datos arba adresas nerandamas ar priskirtas ne tam grafikui.',
      ru: 'Неверные даты вывоза, или адрес не находится либо привязан не к тому графику.',
      pl: 'Błędne daty odbioru albo adresu nie można znaleźć lub przypisano go do złego harmonogramu.',
    },
    intro: {
      en: `The app converts the official schedules of UAB „Nemenčinės komunalininkas“ automatically, so mistakes are possible. Please compare with the official schedule:\n${OFFICIAL_SCHEDULE}`,
      lt: `Programėlė oficialius UAB „Nemenčinės komunalininkas“ grafikus perskaito automatiškai, todėl galimos klaidos. Palyginkite su oficialiu grafiku:\n${OFFICIAL_SCHEDULE}`,
      ru: `Приложение автоматически обрабатывает официальные графики UAB „Nemenčinės komunalininkas“, поэтому возможны ошибки. Сравните с официальным графиком:\n${OFFICIAL_SCHEDULE}`,
      pl: `Aplikacja automatycznie przetwarza oficjalne harmonogramy UAB „Nemenčinės komunalininkas”, więc możliwe są błędy. Porównaj z oficjalnym harmonogramem:\n${OFFICIAL_SCHEDULE}`,
    },
    fields: [
      {
        type: 'dropdown',
        id: 'problem',
        required: true,
        label: { en: "What's wrong?", lt: 'Kas negerai?', ru: 'Что не так?', pl: 'Co jest nie tak?' },
        options: {
          en: [
            'A pickup date is wrong',
            "My village or street can't be found",
            'My place is matched to the wrong schedule row',
            'A waste type is missing for my place',
            'Something else',
          ],
          lt: [
            'Neteisinga išvežimo data',
            'Nerandu savo kaimo ar gatvės',
            'Mano vieta priskirta ne tai grafiko eilutei',
            'Mano vietai trūksta atliekų rūšies',
            'Kita',
          ],
          ru: [
            'Неверная дата вывоза',
            'Не могу найти свою деревню или улицу',
            'Моё место привязано не к той строке графика',
            'Для моего места нет одного из видов отходов',
            'Другое',
          ],
          pl: [
            'Błędna data odbioru',
            'Nie mogę znaleźć swojej miejscowości lub ulicy',
            'Moje miejsce przypisano do złego wiersza harmonogramu',
            'Brakuje rodzaju odpadów dla mojego miejsca',
            'Coś innego',
          ],
        },
      },
      {
        type: 'input',
        id: 'place',
        required: true,
        label: { en: 'Your place', lt: 'Jūsų vieta', ru: 'Ваше место', pl: 'Twoje miejsce' },
        description: {
          en: "Village or town, street and, if relevant, house number. Filled in by the app; remove anything you don't want to share.",
          lt: 'Kaimas ar miestas, gatvė ir, jei svarbu, namo numeris. Užpildo programėlė; ištrinkite tai, kuo nenorite dalintis.',
          ru: 'Деревня или город, улица и при необходимости номер дома. Заполняется приложением; удалите то, чем не хотите делиться.',
          pl: 'Wieś lub miasto, ulica i w razie potrzeby numer domu. Wypełniane przez aplikację; usuń to, czego nie chcesz udostępniać.',
        },
      },
      {
        type: 'textarea',
        id: 'details',
        required: true,
        label: { en: 'Details', lt: 'Išsamiau', ru: 'Подробности', pl: 'Szczegóły' },
        description: {
          en: 'Which waste type and date? What does the official schedule say?',
          lt: 'Kokia atliekų rūšis ir data? Kas nurodyta oficialiame grafike?',
          ru: 'Какой вид отходов и дата? Что указано в официальном графике?',
          pl: 'Jaki rodzaj odpadów i data? Co podaje oficjalny harmonogram?',
        },
      },
      appVersion,
      {
        type: 'input',
        id: 'data-date',
        label: {
          en: 'Schedule data date',
          lt: 'Grafiko duomenų data',
          ru: 'Дата данных графика',
          pl: 'Data danych harmonogramu',
        },
        description: {
          en: 'Shown at the bottom of the home screen. Filled in by the app.',
          lt: 'Rodoma pagrindinio ekrano apačioje. Užpildo programėlė.',
          ru: 'Указана внизу главного экрана. Заполняется приложением.',
          pl: 'Widoczna na dole ekranu głównego. Wypełniane przez aplikację.',
        },
      },
    ],
  },

  feature_request: {
    title: '[Idea]: ',
    labels: ['enhancement'],
    name: { en: 'Suggest an idea', lt: 'Pasiūlyti idėją', ru: 'Предложить идею', pl: 'Zaproponuj pomysł' },
    description: {
      en: 'Suggest a feature or an improvement.',
      lt: 'Pasiūlykite naują funkciją ar patobulinimą.',
      ru: 'Предложите новую функцию или улучшение.',
      pl: 'Zaproponuj nową funkcję lub ulepszenie.',
    },
    intro: {
      en: 'Thanks for helping make the app better!',
      lt: 'Ačiū, kad padedate tobulinti programėlę!',
      ru: 'Спасибо, что помогаете сделать приложение лучше!',
      pl: 'Dziękujemy za pomoc w ulepszaniu aplikacji!',
    },
    fields: [
      {
        type: 'textarea',
        id: 'idea',
        required: true,
        label: { en: 'Your idea', lt: 'Jūsų idėja', ru: 'Ваша идея', pl: 'Twój pomysł' },
      },
      {
        type: 'textarea',
        id: 'why',
        label: {
          en: 'What problem would it solve for you?',
          lt: 'Kokią problemą tai jums išspręstų?',
          ru: 'Какую проблему это бы для вас решило?',
          pl: 'Jaki problem by to dla Ciebie rozwiązało?',
        },
      },
      appVersion,
    ],
  },
};

// YAML double-quoted scalars accept JSON string syntax; multi-line text uses a block scalar.
function scalar(value, indent) {
  if (!value.includes('\n')) return JSON.stringify(value);
  const pad = ' '.repeat(indent);
  return `|\n${value
    .split('\n')
    .map((line) => pad + line)
    .join('\n')}`;
}

function render(id, lang) {
  const form = FORMS[id];
  const lines = [
    '# Generated by app/scripts/issue-forms.mjs. Edit that file, then run `npm run issue-forms` in app/.',
    `name: ${scalar(`${lang.toUpperCase()} · ${form.name[lang]}`)}`,
    `description: ${scalar(form.description[lang])}`,
    `title: ${scalar(form.title)}`,
    `labels: [${[...form.labels, `lang:${lang}`].map((label) => scalar(label)).join(', ')}]`,
    'body:',
    '  - type: markdown',
    '    attributes:',
    `      value: ${scalar(form.intro[lang], 8)}`,
  ];
  for (const field of form.fields) {
    lines.push(`  - type: ${field.type}`, `    id: ${field.id}`, '    attributes:');
    lines.push(`      label: ${scalar(field.label[lang])}`);
    for (const key of ['description', 'placeholder']) {
      if (field[key]) lines.push(`      ${key}: ${scalar(field[key][lang], 8)}`);
    }
    if (field.render) lines.push(`      render: ${field.render}`);
    if (field.options) {
      lines.push('      options:', ...field.options[lang].map((option) => `        - ${scalar(option)}`));
    }
    if (field.required) lines.push('    validations:', '      required: true');
  }
  return `${lines.join('\n')}\n`;
}

for (const [id, form] of Object.entries(FORMS)) {
  const texts = [
    form.name,
    form.description,
    form.intro,
    ...form.fields.flatMap((f) => [f.label, f.description, f.placeholder, f.options]),
  ];
  for (const lang of LANGUAGES) {
    if (texts.some((text) => text && !text[lang])) throw new Error(`${id}: missing "${lang}" text`);
  }
}

const expected = new Map(
  LANGUAGES.flatMap((lang) => Object.keys(FORMS).map((id) => [`${lang}-${id}.yml`, render(id, lang)])),
);
// Every other .yml here except config.yml is a form this script used to generate.
const existing = readdirSync(outDir).filter((file) => file.endsWith('.yml') && file !== 'config.yml');

if (process.argv[2] === 'check') {
  const problems = [
    ...[...expected]
      .filter(([file, text]) => {
        try {
          return readFileSync(join(outDir, file), 'utf8').replace(/\r\n/g, '\n') !== text;
        } catch {
          return true;
        }
      })
      .map(([file]) => `${file} is missing or out of date`),
    ...existing.filter((file) => !expected.has(file)).map((file) => `${file} is not generated by this script`),
  ];
  if (problems.length) {
    console.error(`${problems.join('\n')}\nRun \`npm run issue-forms\` in app/ and commit the result.`);
    process.exit(1);
  }
  console.log(`Issue forms are up to date (${expected.size} files).`);
} else {
  for (const file of existing) if (!expected.has(file)) rmSync(join(outDir, file));
  for (const [file, text] of expected) writeFileSync(join(outDir, file), text);
  console.log(`Wrote ${expected.size} issue forms to ${outDir}`);
}
