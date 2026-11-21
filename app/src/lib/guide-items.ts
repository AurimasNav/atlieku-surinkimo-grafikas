import type { GuideItem, GuideRule, Localized } from './guide';

/*
 * Items of the "Which bin?" guide. The first name in each language is the one shown; the others
 * are words people search for. Keep a rule general unless a source says otherwise for a company,
 * and then put it under `regions` with the source.
 *
 * Sources (checked November 2026):
 * - Vilniaus r.: nemenkom.lt (atlieku-rusiavimas, konteineriai: one 240 l bin for paper, plastic
 *   and metal at private houses; dideliu-gabaritu-ir-pavojingu-atlieku-surinkimas), nkom.lt
 *   (kita.html, rusiavimo-taisykles.html), vaatc.lt (atlieku-enciklopedija, bulky waste sites),
 *   vrsa.lt (orange bags for food waste).
 * - Kauno r.: kaunoratc.lt (atlieku-rusiavimo-abc, dgasa, zaka), svara.lt (rusiavimo-gidas,
 *   maisto-atlieku-tvarkymas), rkpc.lt (atlieku-tvarkymas-informacija: Ekonovus empties the bins
 *   for all packaging except glass, and glass; food waste in a paper or plastic bag).
 * - Mažeikių r., Telšių r., Plungės r., Rietavo sav. (region `mazeikiai`): tratc.lt
 *   (atlieku-rusiavimas-2/*, tratc-atlieku-surinkimo-aiksteles).
 * - National: grazintiverta.lt (deposit, 10 ct), eei.lt (electronics and batteries go back to
 *   shops that sell them), aplinka.vilnius.lt (receipts are mixed waste).
 */

/** The same rule for both companies in Vilniaus r. */
const vilnius = (rule: Partial<GuideRule>) => ({ nemencine: rule, nemezio: rule });

/** Two tips one after the other. */
const join = (a: Localized, b: Localized): Localized => ({
  en: `${a.en} ${b.en}`,
  lt: `${a.lt} ${b.lt}`,
  ru: `${a.ru} ${b.ru}`,
  pl: `${a.pl} ${b.pl}`,
});

// rkpc.lt: "Maisto ir virtuvės atliekas reikia rinkti į popierinį ar plastikinį maišelį".
const kaunoBag: Localized = {
  en: 'In Kaunas district, collect food waste in a paper or plastic bag and tie it before putting it in the bin.',
  lt: 'Kauno rajone maisto atliekas rinkite į popierinį ar plastikinį maišelį ir prieš išmesdami jį užriškite.',
  ru: 'В Каунасском районе собирайте пищевые отходы в бумажный или пластиковый пакет и завязывайте его, прежде чем выбросить.',
  pl: 'W rejonie kowieńskim zbieraj odpady spożywcze do papierowej lub plastikowej torebki i zawiąż ją przed wyrzuceniem.',
};
/**
 * A tip about the food waste bin of Kauno švara's addresses: not shown where an address has none,
 * as in Kaišiadorių r., where it collects mixed waste only.
 */
const kaunoFoodBin = (tip: Localized): Partial<GuideRule> => ({ tip, tipFor: 'food' });

const leftoversTip: Localized = {
  en: 'Without packaging. Pour off liquids such as soup or milk first.',
  lt: 'Be pakuočių. Skysčius, pavyzdžiui, sriubą ar pieną, pirmiausia nupilkite.',
  ru: 'Без упаковки. Жидкости, например суп или молоко, сначала слейте.',
  pl: 'Bez opakowania. Płyny, np. zupę czy mleko, najpierw odlej.',
};

const paperTip: Localized = {
  en: "Dry and clean. At a private house paper goes in the packaging bin with plastic and metal; where there's a separate paper container (often blue), use that.",
  lt: 'Popierius turi būti sausas ir švarus. Prie individualaus namo jis metamas į pakuočių konteinerį kartu su plastiku ir metalu; jei yra atskiras popieriaus konteineris (dažnai mėlynas), meskite į jį.',
  ru: 'Бумага должна быть сухой и чистой. У частного дома её кладут в контейнер для упаковки вместе с пластиком и металлом; если есть отдельный контейнер для бумаги (часто синий), используйте его.',
  pl: 'Papier musi być suchy i czysty. Przy domu jednorodzinnym wrzuca się go do pojemnika na opakowania razem z plastikiem i metalem; jeśli jest osobny pojemnik na papier (często niebieski), użyj go.',
};

const depositTip = (rest: Localized): Localized => ({
  en: `With the deposit mark, return it empty and uncrushed to a shop for 10 ct. ${rest.en}`,
  lt: `Jei yra užstato ženklas, tuščią ir nesuspaustą grąžinkite parduotuvėje ir atgausite 10 ct. ${rest.lt}`,
  ru: `Если есть знак залога, сдайте её пустой и несмятой в магазине и получите 10 ct. ${rest.ru}`,
  pl: `Jeśli ma znak kaucji, oddaj ją pustą i niezgniecioną w sklepie i odzyskaj 10 ct. ${rest.pl}`,
});

const electronicsTip: Localized = {
  en: 'Anything with a plug or a battery is electronics: never put it in mixed waste.',
  lt: 'Viskas, kas turi kištuką ar bateriją, yra elektronika: niekada nemeskite į mišrias atliekas.',
  ru: 'Всё, что с вилкой или батарейкой, — это электроника: никогда не выбрасывайте её в смешанные отходы.',
  pl: 'Wszystko z wtyczką lub baterią to elektronika: nigdy nie wyrzucaj tego do odpadów zmieszanych.',
};

const hazardousTip: Localized = {
  en: 'Hazardous waste: keep it in its closed original packaging and never pour it down the drain.',
  lt: 'Pavojingos atliekos: laikykite uždarytoje originalioje pakuotėje ir niekada nepilkite į kanalizaciją.',
  ru: 'Опасные отходы: храните в закрытой оригинальной упаковке и никогда не сливайте в канализацию.',
  pl: 'Odpady niebezpieczne: trzymaj je w zamkniętym oryginalnym opakowaniu i nigdy nie wylewaj do kanalizacji.',
};

const notGlassTip: Localized = {
  en: 'Only bottles and jars go in the glass container. Wrap sharp pieces.',
  lt: 'Į stiklo konteinerį metami tik buteliai ir stiklainiai. Aštrias šukes suvyniokite.',
  ru: 'В контейнер для стекла кладут только бутылки и банки. Острые осколки заверните.',
  pl: 'Do pojemnika na szkło wrzuca się tylko butelki i słoiki. Ostre kawałki zawiń.',
};

const textileTip: Localized = {
  en: "Clean and dry, in a tied bag. Don't leave bags next to a full container.",
  lt: 'Švarius ir sausus, užrištame maišelyje. Nepalikite maišų prie pilno konteinerio.',
  ru: 'Чистые и сухие, в завязанном пакете. Не оставляйте пакеты у переполненного контейнера.',
  pl: 'Czyste i suche, w zawiązanym worku. Nie zostawiaj worków przy pełnym pojemniku.',
};

const giveAwayTip: Localized = {
  en: 'If it still works or can be used, give it away first.',
  lt: 'Jei daiktas dar tinkamas naudoti, pirmiausia pabandykite jį atiduoti.',
  ru: 'Если вещь ещё годится, сначала попробуйте её отдать.',
  pl: 'Jeśli rzecz nadaje się jeszcze do użytku, najpierw spróbuj ją oddać.',
};

// vaatc.lt, bulky waste sites: "Baldai privalo būti išardyti".
const dismantleTip: Localized = {
  en: 'Usable furniture: give it away. Vilnius region sites only take furniture taken apart.',
  lt: 'Tinkamus baldus atiduokite kitiems. Vilniaus regiono aikštelėse baldai priimami tik išardyti.',
  ru: 'Годную мебель отдайте. На площадках Вильнюсского региона мебель принимают только в разобранном виде.',
  pl: 'Meble w dobrym stanie oddaj. Punkty w regionie wileńskim przyjmują meble tylko rozebrane.',
};

export const GUIDE_ITEMS: GuideItem[] = [
  // --- Food and kitchen ------------------------------------------------------------------------
  {
    id: 'peels',
    category: 'food',
    to: ['food'],
    compost: true,
    names: {
      en: ['Fruit and vegetable peels', 'peel', 'peelings', 'vegetable scraps', 'fruit', 'vegetables', 'banana peel', 'apple core', 'potato peel'],
      lt: ['Vaisių ir daržovių lupenos', 'lupenos', 'žievės', 'vaisiai', 'daržovės', 'bananų žievės', 'obuolių graužtukai', 'bulvių lupenos'],
      ru: ['Очистки фруктов и овощей', 'очистки', 'кожура', 'фрукты', 'овощи', 'банановая кожура', 'огрызок', 'картофельные очистки'],
      pl: ['Obierki owoców i warzyw', 'obierki', 'skórki', 'owoce', 'warzywa', 'skórka od banana', 'ogryzek', 'obierki z ziemniaków'],
    },
    regions: { kauno: kaunoFoodBin(kaunoBag) },
  },
  {
    id: 'leftovers',
    category: 'food',
    to: ['food'],
    names: {
      en: ['Food leftovers', 'leftovers', 'cooked food', 'plate scrapings', 'rice', 'pasta', 'spoiled food', 'mouldy food'],
      lt: ['Maisto likučiai', 'likučiai', 'virtas maistas', 'gaminto maisto likučiai', 'ryžiai', 'makaronai', 'sugedęs maistas', 'supelijęs maistas'],
      ru: ['Остатки еды', 'объедки', 'готовая еда', 'рис', 'макароны', 'испорченная еда', 'заплесневелая еда'],
      pl: ['Resztki jedzenia', 'resztki', 'gotowane jedzenie', 'ryż', 'makaron', 'zepsute jedzenie', 'spleśniałe jedzenie'],
    },
    tip: leftoversTip,
    regions: { kauno: kaunoFoodBin(join(leftoversTip, kaunoBag)) },
  },
  {
    id: 'meat-fish',
    category: 'food',
    to: ['food'],
    names: {
      en: ['Meat and fish', 'meat', 'fish', 'raw meat', 'chicken', 'fish skin', 'seafood', 'shrimp shells'],
      lt: ['Mėsa ir žuvis', 'mėsa', 'žuvis', 'žalia mėsa', 'vištiena', 'žuvies oda', 'jūros gėrybės', 'krevečių kiautai'],
      ru: ['Мясо и рыба', 'мясо', 'рыба', 'сырое мясо', 'курица', 'рыбья кожа', 'морепродукты', 'панцири креветок'],
      pl: ['Mięso i ryby', 'mięso', 'ryba', 'surowe mięso', 'kurczak', 'skóra rybia', 'owoce morza', 'skorupki krewetek'],
    },
    regions: {
      kauno: kaunoFoodBin(kaunoBag),
      // tratc.lt/atlieku-rusiavimas-2/zaliosios-atliekos: raw meat, fish and eggs are not accepted.
      mazeikiai: {
        to: ['household'],
        tip: {
          en: 'Telšiai region (TRATC): the food waste bin takes cooked meat and fish only, not raw meat, fish or eggs.',
          lt: 'Telšių regione (TRATC) į maisto atliekų konteinerį galima mesti tik termiškai apdorotą mėsą ir žuvį, ne žalią mėsą, žuvį ar kiaušinius.',
          ru: 'В Тельшяйском регионе (TRATC) в контейнер для пищевых отходов можно класть только приготовленные мясо и рыбу, но не сырые мясо, рыбу или яйца.',
          pl: 'W regionie telszańskim (TRATC) do pojemnika na odpady spożywcze trafia tylko gotowane mięso i ryby, nie surowe mięso, ryby ani jajka.',
        },
      },
    },
  },
  {
    id: 'bones',
    category: 'food',
    to: ['food'],
    names: {
      en: ['Bones', 'chicken bones', 'meat bones', 'fish bones'],
      lt: ['Kaulai', 'vištienos kaulai', 'mėsos kaulai', 'žuvies kaulai', 'ašakos'],
      ru: ['Кости', 'куриные кости', 'мясные кости', 'рыбьи кости'],
      pl: ['Kości', 'kości z kurczaka', 'kości mięsne', 'ości'],
    },
  },
  {
    id: 'eggshells',
    category: 'food',
    to: ['food'],
    compost: true,
    names: {
      en: ['Eggshells', 'egg shells', 'eggs'],
      lt: ['Kiaušinių lukštai', 'kiaušiniai', 'lukštai'],
      ru: ['Яичная скорлупа', 'скорлупа', 'яйца'],
      pl: ['Skorupki jajek', 'skorupki', 'jajka'],
    },
  },
  {
    id: 'coffee',
    category: 'food',
    to: ['food'],
    compost: true,
    names: {
      en: ['Coffee grounds', 'coffee', 'coffee filter', 'paper coffee filter'],
      lt: ['Kavos tirščiai', 'kava', 'kavos filtras', 'popierinis kavos filtras'],
      ru: ['Кофейная гуща', 'кофе', 'кофейный фильтр', 'бумажный фильтр для кофе'],
      pl: ['Fusy z kawy', 'kawa', 'filtr do kawy', 'fusy'],
    },
  },
  {
    id: 'tea',
    category: 'food',
    to: ['food'],
    compost: true,
    names: {
      en: ['Tea bags', 'tea', 'tea leaves'],
      lt: ['Arbatos pakeliai', 'arbata', 'arbatžolės'],
      ru: ['Чайные пакетики', 'чай', 'заварка'],
      pl: ['Torebki herbaty', 'herbata', 'fusy z herbaty'],
    },
  },
  {
    id: 'bread',
    category: 'food',
    to: ['food'],
    names: {
      en: ['Bread and pastries', 'bread', 'pastry', 'cake', 'stale bread', 'baked goods'],
      lt: ['Duona ir pyragai', 'duona', 'pyragas', 'bandelė', 'sudžiūvusi duona', 'kepiniai'],
      ru: ['Хлеб и выпечка', 'хлеб', 'булка', 'пирог', 'чёрствый хлеб', 'торт'],
      pl: ['Pieczywo i ciasta', 'chleb', 'bułka', 'ciasto', 'czerstwy chleb', 'wypieki'],
    },
  },
  {
    id: 'dairy',
    category: 'food',
    to: ['food'],
    names: {
      en: ['Cheese and dairy leftovers', 'cheese', 'cottage cheese', 'yogurt leftovers', 'sour cream', 'dairy'],
      lt: ['Sūris ir pieno produktų likučiai', 'sūris', 'varškė', 'jogurto likučiai', 'grietinė', 'pieno produktai'],
      ru: ['Сыр и остатки молочных продуктов', 'сыр', 'творог', 'остатки йогурта', 'сметана', 'молочные продукты'],
      pl: ['Ser i resztki nabiału', 'ser', 'twaróg', 'resztki jogurtu', 'śmietana', 'nabiał'],
    },
    tip: {
      en: "Solid leftovers only, without the packaging; liquids such as milk don't belong in the bin.",
      lt: 'Tik kieti likučiai, be pakuotės; skysčiai, pavyzdžiui, pienas, į konteinerį nemetami.',
      ru: 'Только твёрдые остатки, без упаковки; жидкости, например молоко, в контейнер не выливают.',
      pl: 'Tylko stałe resztki, bez opakowania; płyny, np. mleko, nie trafiają do pojemnika.',
    },
  },
  {
    id: 'nutshells',
    category: 'food',
    to: ['food'],
    compost: true,
    names: {
      en: ['Nutshells', 'nut shells', 'nuts', 'sunflower seed husks', 'seeds'],
      lt: ['Riešutų kevalai', 'riešutai', 'kevalai', 'saulėgrąžų lukštai', 'sėklos'],
      ru: ['Скорлупа орехов', 'орехи', 'шелуха семечек', 'семечки'],
      pl: ['Łupiny orzechów', 'orzechy', 'łupiny', 'łuski słonecznika', 'pestki'],
    },
  },
  {
    id: 'expired-packaged',
    category: 'food',
    to: ['food'],
    names: {
      en: ['Expired food in its packaging', 'expired food', 'out-of-date food', 'spoiled yogurt', 'old jam'],
      lt: ['Pasibaigusio galiojimo maistas pakuotėje', 'pasibaigęs galiojimas', 'nebetinkamas maistas', 'sugedęs jogurtas', 'sena uogienė'],
      ru: ['Просроченные продукты в упаковке', 'просрочка', 'просроченные продукты', 'испорченный йогурт', 'старое варенье'],
      pl: ['Przeterminowana żywność w opakowaniu', 'przeterminowane jedzenie', 'zepsuty jogurt', 'stary dżem'],
    },
    tip: {
      en: 'Empty the food out and sort the packaging separately: a jar goes to glass, a cup or tray to packaging.',
      lt: 'Maistą išimkite iš pakuotės, o pakuotę rūšiuokite atskirai: stiklainį – į stiklo, indelį ar padėklą – į pakuočių konteinerį.',
      ru: 'Выньте еду из упаковки, а упаковку сортируйте отдельно: банку — в стекло, стаканчик или лоток — в упаковку.',
      pl: 'Wyjmij jedzenie z opakowania, a opakowanie posegreguj osobno: słoik do szkła, kubek lub tackę do opakowań.',
    },
  },
  {
    id: 'flowers',
    category: 'food',
    to: ['food'],
    compost: true,
    names: {
      en: ['Cut flowers and houseplants', 'flowers', 'bouquet', 'houseplant', 'dead plant', 'potted plant'],
      lt: ['Skintos gėlės ir kambariniai augalai', 'gėlės', 'puokštė', 'kambarinis augalas', 'nuvytęs augalas', 'vazoninis augalas'],
      ru: ['Срезанные цветы и комнатные растения', 'цветы', 'букет', 'комнатное растение', 'завядшее растение'],
      pl: ['Cięte kwiaty i rośliny doniczkowe', 'kwiaty', 'bukiet', 'roślina doniczkowa', 'zwiędła roślina'],
    },
    tip: {
      en: 'Without the pot, soil, ribbons or wrapping.',
      lt: 'Be vazono, žemių, kaspinų ir įvyniojimo.',
      ru: 'Без горшка, земли, лент и обёртки.',
      pl: 'Bez doniczki, ziemi, wstążek i opakowania.',
    },
  },
  {
    id: 'napkins',
    category: 'food',
    to: ['food'],
    fallback: ['household'],
    names: {
      en: ['Paper napkins and paper towels', 'napkin', 'serviette', 'paper towel', 'kitchen roll'],
      lt: ['Popierinės servetėlės ir rankšluosčiai', 'servetėlė', 'popierinis rankšluostis', 'virtuvinis popierius'],
      ru: ['Бумажные салфетки и полотенца', 'салфетка', 'бумажное полотенце', 'кухонные полотенца'],
      pl: ['Serwetki i ręczniki papierowe', 'serwetka', 'ręcznik papierowy', 'ręcznik kuchenny'],
    },
    tip: {
      en: "Food-soiled paper isn't recycled with paper. Wet wipes go in mixed waste.",
      lt: 'Maistu suteptas popierius neperdirbamas kartu su popieriumi. Drėgnosios servetėlės metamos į mišrias atliekas.',
      ru: 'Испачканная едой бумага не перерабатывается вместе с бумагой. Влажные салфетки — в смешанные отходы.',
      pl: 'Papier zabrudzony jedzeniem nie jest przetwarzany razem z papierem. Chusteczki nawilżane – do odpadów zmieszanych.',
    },
  },
  {
    id: 'cooking-oil',
    category: 'food',
    to: ['site'],
    names: {
      en: ['Cooking oil and fat', 'oil', 'frying oil', 'used oil', 'grease', 'lard'],
      lt: ['Kepimo aliejus ir riebalai', 'aliejus', 'panaudotas aliejus', 'riebalai', 'taukai'],
      ru: ['Растительное масло и жир', 'масло', 'отработанное масло', 'жир', 'сало'],
      pl: ['Olej i tłuszcz po smażeniu', 'olej', 'zużyty olej', 'tłuszcz', 'smalec'],
    },
    tip: {
      en: 'Pour it into a closed plastic bottle and take it to a bulky waste site. Wipe up a little oil with a paper towel and put it in the food waste. Never pour oil down the sink.',
      lt: 'Supilkite į uždaromą plastikinį butelį ir nuvežkite į didelių gabaritų atliekų aikštelę. Nedidelį kiekį sugerkite popieriniu rankšluosčiu ir išmeskite su maisto atliekomis. Niekada nepilkite aliejaus į kriauklę.',
      ru: 'Слейте в закрытую пластиковую бутылку и отвезите на площадку крупногабаритных отходов. Немного масла промокните бумажным полотенцем и выбросьте с пищевыми отходами. Никогда не сливайте масло в раковину.',
      pl: 'Przelej do zakręcanej plastikowej butelki i zawieź do punktu odpadów wielkogabarytowych. Odrobinę oleju zbierz ręcznikiem papierowym i wyrzuć z odpadami spożywczymi. Nigdy nie wylewaj oleju do zlewu.',
    },
  },

  // --- Paper and cardboard ---------------------------------------------------------------------
  {
    id: 'cardboard',
    category: 'paper',
    to: ['packaging'],
    names: {
      en: ['Cardboard box', 'cardboard', 'box', 'parcel box', 'moving box', 'corrugated cardboard'],
      lt: ['Kartoninė dėžė', 'kartonas', 'dėžė', 'dėžutė', 'siuntinio dėžė', 'gofruotas kartonas'],
      ru: ['Картонная коробка', 'картон', 'коробка', 'коробка от посылки', 'гофрокартон'],
      pl: ['Karton', 'kartonowe pudło', 'pudełko', 'pudło', 'karton po przesyłce', 'tektura'],
    },
    tip: {
      en: 'Flatten it. Paper goes in the packaging bin, or in a separate paper container (often blue) where there is one. Too many or too big boxes: bulky waste site.',
      lt: 'Suplokite. Popierius metamas į pakuočių konteinerį arba, jei yra, į atskirą popieriaus konteinerį (dažnai mėlyną). Per daug ar per didelės dėžės – į didelių gabaritų atliekų aikštelę.',
      ru: 'Сложите плоско. Бумагу кладут в контейнер для упаковки или, если есть, в отдельный контейнер для бумаги (часто синий). Слишком много или слишком большие коробки — на площадку крупногабаритных отходов.',
      pl: 'Złóż na płasko. Papier wrzuca się do pojemnika na opakowania albo, jeśli jest, do osobnego pojemnika na papier (często niebieskiego). Za dużo lub za duże kartony – do punktu odpadów wielkogabarytowych.',
    },
  },
  {
    id: 'newspapers',
    category: 'paper',
    to: ['packaging'],
    names: {
      en: ['Newspapers and magazines', 'newspaper', 'magazine', 'leaflets', 'flyers', 'brochure', 'catalogue'],
      lt: ['Laikraščiai ir žurnalai', 'laikraštis', 'žurnalas', 'skrajutės', 'lankstinukai', 'reklaminiai leidiniai', 'katalogas'],
      ru: ['Газеты и журналы', 'газета', 'журнал', 'листовки', 'рекламные буклеты', 'каталог'],
      pl: ['Gazety i czasopisma', 'gazeta', 'czasopismo', 'ulotki', 'broszura', 'katalog'],
    },
    tip: paperTip,
  },
  {
    id: 'office-paper',
    category: 'paper',
    to: ['packaging'],
    names: {
      en: ['Office paper and notebooks', 'paper', 'printer paper', 'notebook', 'exercise book', 'documents', 'letters'],
      lt: ['Biuro popierius ir sąsiuviniai', 'popierius', 'spausdintuvo popierius', 'sąsiuvinis', 'dokumentai', 'laiškai'],
      ru: ['Офисная бумага и тетради', 'бумага', 'бумага для принтера', 'тетрадь', 'документы', 'письма'],
      pl: ['Papier biurowy i zeszyty', 'papier', 'papier do drukarki', 'zeszyt', 'dokumenty', 'listy', 'kartki'],
    },
    tip: {
      en: 'Staples and sticky tape can stay on. Take the spiral out of notebooks.',
      lt: 'Sąsagėlių ir lipnios juostos nuimti nereikia. Iš sąsiuvinių išimkite spirales.',
      ru: 'Скрепки и скотч можно не снимать. Из тетрадей выньте пружину.',
      pl: 'Zszywek i taśmy klejącej nie trzeba usuwać. Z zeszytów wyjmij spiralę.',
    },
  },
  {
    id: 'books',
    category: 'paper',
    to: ['packaging'],
    names: {
      en: ['Books', 'book', 'paperback', 'old books', 'textbook'],
      lt: ['Knygos', 'knyga', 'senos knygos', 'vadovėlis'],
      ru: ['Книги', 'книга', 'старые книги', 'учебник'],
      pl: ['Książki', 'książka', 'stare książki', 'podręcznik'],
    },
    tip: {
      en: 'Books in good condition: give them to a library or a book swap shelf. Hard covers are best torn off.',
      lt: 'Geros būklės knygas atiduokite bibliotekai ar į knygų mainų lentyną. Kietus viršelius geriau nuplėškite.',
      ru: 'Книги в хорошем состоянии отдайте в библиотеку или на полку буккроссинга. Твёрдые обложки лучше оторвать.',
      pl: 'Książki w dobrym stanie oddaj do biblioteki lub na półkę wymiany książek. Twarde okładki lepiej oderwać.',
    },
  },
  {
    id: 'envelopes',
    category: 'paper',
    to: ['packaging'],
    names: {
      en: ['Envelopes', 'envelope', 'window envelope', 'post', 'mail'],
      lt: ['Vokai', 'vokas', 'vokas su langeliu', 'paštas'],
      ru: ['Конверты', 'конверт', 'конверт с окошком', 'почта'],
      pl: ['Koperty', 'koperta', 'koperta z okienkiem', 'poczta'],
    },
    tip: paperTip,
  },
  {
    id: 'paper-bags',
    category: 'paper',
    to: ['packaging'],
    names: {
      en: ['Paper bags', 'paper bag', 'flour bag', 'sugar bag', 'gift bag'],
      lt: ['Popieriniai maišeliai', 'popierinis maišelis', 'miltų maišelis', 'cukraus pakuotė', 'dovanų maišelis'],
      ru: ['Бумажные пакеты', 'бумажный пакет', 'пакет от муки', 'пакет от сахара', 'подарочный пакет'],
      pl: ['Torby papierowe', 'torba papierowa', 'torebka po mące', 'torebka po cukrze', 'torebka prezentowa'],
    },
    tip: {
      en: 'Shake them empty first.',
      lt: 'Pirmiausia išpurtykite.',
      ru: 'Сначала вытряхните содержимое.',
      pl: 'Najpierw wytrzep zawartość.',
    },
  },
  {
    id: 'egg-cartons',
    category: 'paper',
    to: ['packaging'],
    names: {
      en: ['Egg cartons', 'egg box', 'egg tray'],
      lt: ['Kiaušinių dėklai', 'kiaušinių dėžutė', 'kiaušinių padėklas'],
      ru: ['Лотки для яиц', 'коробка из-под яиц', 'упаковка от яиц'],
      pl: ['Wytłaczanki na jajka', 'opakowanie po jajkach', 'pudełko na jajka'],
    },
    tip: {
      en: 'Plastic egg boxes go in the packaging bin too.',
      lt: 'Plastikiniai kiaušinių dėklai taip pat metami į pakuočių konteinerį.',
      ru: 'Пластиковые упаковки от яиц тоже кладут в контейнер для упаковки.',
      pl: 'Plastikowe opakowania po jajkach też wrzuca się do pojemnika na opakowania.',
    },
  },
  {
    id: 'pizza-box',
    category: 'paper',
    // svara.lt, kaunoratc.lt, tratc.lt: greasy cardboard goes with food waste; nemenkom.lt and
    // nkom.lt (no food waste bins): greasy paper is mixed waste.
    to: ['food'],
    fallback: ['household'],
    names: {
      en: ['Pizza box', 'pizza', 'greasy cardboard', 'greasy paper'],
      lt: ['Picos dėžutė', 'pica', 'picos dėžė', 'riebaluotas kartonas', 'riebaluotas popierius'],
      ru: ['Коробка от пиццы', 'пицца', 'жирный картон', 'жирная бумага'],
      pl: ['Pudełko po pizzy', 'pizza', 'tłusty karton', 'zatłuszczony papier'],
    },
    tip: {
      en: "Greasy cardboard isn't recycled with paper. Tear off the clean, dry parts for the packaging bin.",
      lt: 'Riebaluotas kartonas neperdirbamas kartu su popieriumi. Švarias ir sausas dalis nuplėškite ir meskite į pakuočių konteinerį.',
      ru: 'Жирный картон не перерабатывается вместе с бумагой. Чистые и сухие части оторвите и положите в контейнер для упаковки.',
      pl: 'Tłusty karton nie jest przetwarzany razem z papierem. Czyste i suche części oderwij i wrzuć do pojemnika na opakowania.',
    },
  },
  {
    id: 'receipts',
    category: 'paper',
    to: ['household'],
    names: {
      en: ['Receipts', 'receipt', 'till receipt', 'thermal paper'],
      lt: ['Kasos čekiai', 'čekis', 'kvitas', 'terminis popierius'],
      ru: ['Чеки', 'чек', 'кассовый чек', 'термобумага'],
      pl: ['Paragony', 'paragon', 'papier termiczny'],
    },
    tip: {
      en: "Most till receipts are thermal paper, which isn't recycled.",
      lt: 'Dauguma kasos čekių spausdinami ant terminio popieriaus, kuris neperdirbamas.',
      ru: 'Большинство чеков печатают на термобумаге, которая не перерабатывается.',
      pl: 'Większość paragonów drukuje się na papierze termicznym, który nie jest przetwarzany.',
    },
  },
  {
    id: 'wallpaper',
    category: 'paper',
    to: ['site'],
    names: {
      en: ['Wallpaper', 'old wallpaper'],
      lt: ['Tapetai', 'tapetas', 'seni tapetai'],
      ru: ['Обои', 'старые обои'],
      pl: ['Tapeta', 'tapety', 'stare tapety'],
    },
    tip: {
      en: 'It counts as renovation waste, not paper.',
      lt: 'Tai remonto, o ne popieriaus atliekos.',
      ru: 'Это ремонтные отходы, а не бумага.',
      pl: 'To odpady remontowe, a nie papier.',
    },
  },
  {
    id: 'baking-paper',
    category: 'paper',
    to: ['household'],
    names: {
      en: ['Baking paper', 'parchment paper', 'greaseproof paper', 'muffin cases'],
      lt: ['Kepimo popierius', 'pergamentas', 'kepimo formelės'],
      ru: ['Бумага для выпечки', 'пергамент', 'бумажные формочки'],
      pl: ['Papier do pieczenia', 'pergamin', 'papilotki'],
    },
    tip: {
      en: "It's coated, so it isn't recycled with paper.",
      lt: 'Jis padengtas, todėl neperdirbamas kartu su popieriumi.',
      ru: 'Она с покрытием, поэтому не перерабатывается вместе с бумагой.',
      pl: 'Jest powlekany, więc nie jest przetwarzany razem z papierem.',
    },
  },
  {
    id: 'paper-cups',
    category: 'paper',
    // nemenkom.lt, nkom.lt: paper coated with plastic is mixed waste.
    to: ['household'],
    names: {
      en: ['Paper cups and plates', 'coffee cup', 'takeaway cup', 'disposable cup', 'paper plate'],
      lt: ['Popieriniai puodeliai ir lėkštės', 'kavos puodelis', 'išsinešimo puodelis', 'vienkartinis puodelis', 'popierinė lėkštė'],
      ru: ['Бумажные стаканы и тарелки', 'стаканчик для кофе', 'кофе с собой', 'одноразовый стакан', 'бумажная тарелка'],
      pl: ['Kubki i talerzyki papierowe', 'kubek na kawę', 'kubek na wynos', 'kubek jednorazowy', 'talerzyk papierowy'],
    },
    tip: {
      en: "They're lined with plastic, so they don't go with paper. The plastic lid goes in the packaging bin.",
      lt: 'Jie padengti plastiku, todėl nemetami kartu su popieriumi. Plastikinį dangtelį meskite į pakuočių konteinerį.',
      ru: 'Они покрыты пластиком, поэтому не идут вместе с бумагой. Пластиковую крышку положите в контейнер для упаковки.',
      pl: 'Są pokryte plastikiem, więc nie trafiają do papieru. Plastikowe wieczko wrzuć do pojemnika na opakowania.',
    },
  },
  {
    id: 'folders',
    category: 'paper',
    to: ['household'],
    names: {
      en: ['Document folders and binders', 'folder', 'ring binder', 'file folder', 'plastic sleeve'],
      lt: ['Dokumentų segtuvai ir aplankai', 'segtuvas', 'aplankas', 'įmautė'],
      ru: ['Папки и скоросшиватели', 'папка', 'скоросшиватель', 'файл'],
      pl: ['Segregatory i teczki', 'segregator', 'teczka', 'koszulka'],
    },
    tip: {
      en: 'Take the paper out for recycling. Folders with metal parts go in mixed waste.',
      lt: 'Popierių išimkite ir rūšiuokite. Aplankai su metalinėmis dalimis metami į mišrias atliekas.',
      ru: 'Бумагу выньте и сдайте отдельно. Папки с металлическими деталями — в смешанные отходы.',
      pl: 'Papier wyjmij i posegreguj. Teczki z metalowymi elementami – do odpadów zmieszanych.',
    },
  },
  {
    id: 'toilet-rolls',
    category: 'paper',
    to: ['packaging'],
    names: {
      en: ['Toilet roll tubes', 'cardboard tube', 'kitchen roll tube'],
      lt: ['Tualetinio popieriaus ritinėliai', 'kartoninė tūtelė', 'ritinėlis'],
      ru: ['Втулки от туалетной бумаги', 'картонная втулка', 'втулка'],
      pl: ['Rolki po papierze toaletowym', 'tuleja kartonowa', 'rolka'],
    },
  },
  {
    id: 'gift-wrap',
    category: 'paper',
    to: ['packaging'],
    names: {
      en: ['Wrapping paper', 'gift wrap', 'wrapping', 'tissue paper'],
      lt: ['Vyniojamasis popierius', 'dovanų popierius', 'pakavimo popierius'],
      ru: ['Упаковочная бумага', 'подарочная бумага', 'обёрточная бумага'],
      pl: ['Papier do pakowania', 'papier prezentowy', 'papier pakowy'],
    },
    tip: {
      en: "Plastic-coated wrapping (shiny, doesn't tear) goes in mixed waste.",
      lt: 'Plastiku padengtas vyniojamasis popierius (blizgus, neplyšta) metamas į mišrias atliekas.',
      ru: 'Бумага с пластиковым покрытием (блестящая, не рвётся) — в смешанные отходы.',
      pl: 'Papier powlekany plastikiem (błyszczący, nie drze się) – do odpadów zmieszanych.',
    },
  },

  // --- Plastic and metal packaging -------------------------------------------------------------
  {
    id: 'plastic-bottle',
    category: 'packaging',
    to: ['deposit', 'packaging'],
    names: {
      en: ['Plastic drink bottle', 'PET bottle', 'water bottle', 'soda bottle', 'bottle'],
      lt: ['Plastikinis gėrimų butelis', 'PET butelis', 'vandens butelis', 'butelis', 'buteliukas'],
      ru: ['Пластиковая бутылка', 'ПЭТ-бутылка', 'бутылка из-под воды', 'бутылка'],
      pl: ['Plastikowa butelka', 'butelka PET', 'butelka po wodzie', 'butelka'],
    },
    tip: depositTip({
      en: 'Otherwise empty it, screw the cap back on and squash it into the packaging bin.',
      lt: 'Kitu atveju ištuštinkite, užsukite kamštelį, suspauskite ir meskite į pakuočių konteinerį.',
      ru: 'Иначе опорожните, закрутите крышку, сомните и положите в контейнер для упаковки.',
      pl: 'W przeciwnym razie opróżnij ją, zakręć, zgnieć i wrzuć do pojemnika na opakowania.',
    }),
  },
  {
    id: 'cans',
    category: 'packaging',
    to: ['deposit', 'packaging'],
    names: {
      en: ['Drink can', 'can', 'beer can', 'soda can', 'aluminium can'],
      lt: ['Gėrimų skardinė', 'skardinė', 'alaus skardinė', 'aliuminio skardinė'],
      ru: ['Банка от напитка', 'банка', 'пивная банка', 'алюминиевая банка'],
      pl: ['Puszka po napoju', 'puszka', 'puszka po piwie', 'puszka aluminiowa'],
    },
    tip: depositTip({
      en: 'Otherwise: packaging bin.',
      lt: 'Kitu atveju – į pakuočių konteinerį.',
      ru: 'Иначе — в контейнер для упаковки.',
      pl: 'W przeciwnym razie – do pojemnika na opakowania.',
    }),
  },
  {
    id: 'yogurt-cup',
    category: 'packaging',
    to: ['packaging'],
    names: {
      en: ['Yogurt cup', 'yoghurt pot', 'cream pot', 'plastic cup', 'dessert cup', 'ice cream tub'],
      lt: ['Jogurto indelis', 'jogurtas', 'grietinės indelis', 'plastikinis indelis', 'deserto indelis', 'ledų dėžutė'],
      ru: ['Стаканчик от йогурта', 'йогурт', 'стаканчик от сметаны', 'пластиковый стаканчик', 'ведёрко от мороженого'],
      pl: ['Kubek po jogurcie', 'jogurt', 'kubek po śmietanie', 'plastikowy kubeczek', 'pudełko po lodach'],
    },
    tip: {
      en: "Scrape it empty; there's no need to wash it. The foil lid goes in too.",
      lt: 'Gerai ištuštinkite; plauti nereikia. Folijos dangtelį meskite kartu.',
      ru: 'Хорошо опустошите; мыть не нужно. Крышку из фольги кладите туда же.',
      pl: 'Dokładnie opróżnij; myć nie trzeba. Wieczko z folii wrzuć razem z nim.',
    },
  },
  {
    id: 'plastic-bags',
    category: 'packaging',
    to: ['packaging'],
    names: {
      en: ['Plastic bags and film', 'plastic bag', 'carrier bag', 'shopping bag', 'cling film', 'stretch film', 'bubble wrap'],
      lt: ['Plastikiniai maišeliai ir plėvelė', 'maišelis', 'pirkinių maišelis', 'plėvelė', 'maistinė plėvelė', 'burbulinė plėvelė'],
      ru: ['Пластиковые пакеты и плёнка', 'пакет', 'полиэтиленовый пакет', 'плёнка', 'пищевая плёнка', 'пупырчатая плёнка'],
      pl: ['Torebki foliowe i folia', 'reklamówka', 'torba foliowa', 'folia', 'folia spożywcza', 'folia bąbelkowa'],
    },
    tip: {
      en: 'Empty and without food leftovers.',
      lt: 'Tušti ir be maisto likučių.',
      ru: 'Пустые и без остатков еды.',
      pl: 'Puste i bez resztek jedzenia.',
    },
  },
  {
    id: 'food-trays',
    category: 'packaging',
    to: ['packaging'],
    names: {
      en: ['Plastic food trays and boxes', 'meat tray', 'salad box', 'takeaway box', 'berry punnet', 'plastic container'],
      lt: ['Plastikiniai maisto padėklai ir dėžutės', 'padėklas', 'mėsos padėklas', 'salotų dėžutė', 'išsinešimo dėžutė', 'uogų dėžutė', 'plastikinė dėžutė'],
      ru: ['Пластиковые лотки и контейнеры для еды', 'лоток', 'лоток от мяса', 'контейнер для салата', 'контейнер навынос', 'пластиковый контейнер'],
      pl: ['Plastikowe tacki i pojemniki na żywność', 'tacka', 'tacka po mięsie', 'pojemnik na sałatkę', 'pudełko na wynos', 'plastikowy pojemnik'],
    },
    tip: {
      en: 'Empty them; rinse greasy ones if you can.',
      lt: 'Ištuštinkite; riebaluotus, jei galite, praskalaukite.',
      ru: 'Опустошите; жирные по возможности ополосните.',
      pl: 'Opróżnij; tłuste w miarę możliwości opłucz.',
    },
  },
  {
    id: 'detergent-bottles',
    category: 'packaging',
    to: ['packaging'],
    names: {
      en: ['Shampoo and detergent bottles', 'shampoo', 'shower gel', 'washing-up liquid', 'detergent', 'cosmetics bottle'],
      lt: ['Šampūno ir ploviklių buteliai', 'šampūnas', 'dušo želė', 'indų ploviklis', 'skalbiklis', 'kosmetikos pakuotė'],
      ru: ['Флаконы от шампуня и моющих средств', 'шампунь', 'гель для душа', 'средство для посуды', 'моющее средство', 'флакон от косметики'],
      pl: ['Butelki po szamponie i detergentach', 'szampon', 'żel pod prysznic', 'płyn do naczyń', 'detergent', 'butelka po kosmetyku'],
    },
    tip: {
      en: 'Empty. Packaging of hazardous products (with warning symbols, e.g. drain cleaner or antifreeze) goes to a bulky waste site.',
      lt: 'Tuščius. Pavojingų produktų pakuotės (su įspėjamaisiais ženklais, pvz., kanalizacijos valiklio ar antifrizo) vežamos į didelių gabaritų atliekų aikštelę.',
      ru: 'Пустыми. Упаковку опасных средств (со знаками опасности, например средства для труб или антифриза) везите на площадку крупногабаритных отходов.',
      pl: 'Puste. Opakowania po produktach niebezpiecznych (z symbolami ostrzegawczymi, np. udrażniacz do rur, płyn do chłodnic) – do punktu odpadów wielkogabarytowych.',
    },
  },
  {
    id: 'caps',
    category: 'packaging',
    to: ['packaging'],
    names: {
      en: ['Bottle caps and lids', 'cap', 'plastic lid', 'metal lid', 'jar lid', 'bottle top'],
      lt: ['Kamšteliai ir dangteliai', 'kamštelis', 'dangtelis', 'plastikinis dangtelis', 'metalinis dangtelis', 'stiklainio dangtelis'],
      ru: ['Крышки', 'крышка', 'крышечка', 'пробка', 'крышка от банки'],
      pl: ['Nakrętki i wieczka', 'nakrętka', 'zakrętka', 'wieczko', 'kapsel', 'pokrywka słoika'],
    },
    tip: {
      en: 'Screw plastic caps back onto bottles. Take lids off glass jars: the lid goes here, the jar to glass.',
      lt: 'Plastikinius kamštelius užsukite ant butelių. Stiklainių dangtelius nuimkite: dangtelis – čia, stiklainis – į stiklo konteinerį.',
      ru: 'Пластиковые крышки закрутите обратно на бутылки. С банок крышки снимите: крышку — сюда, банку — в стекло.',
      pl: 'Plastikowe nakrętki zakręć z powrotem na butelkach. Ze słoików zdejmij pokrywki: pokrywka tutaj, słoik do szkła.',
    },
  },
  {
    id: 'tetra-pak',
    category: 'packaging',
    to: ['packaging'],
    names: {
      en: ['Milk and juice cartons', 'Tetra Pak', 'drink carton', 'milk carton', 'juice carton', 'Elopak'],
      lt: ['Pieno ir sulčių pakeliai', 'Tetra Pak', 'pieno pakelis', 'sulčių pakelis', 'kombinuota pakuotė', 'Elopak'],
      ru: ['Пакеты от молока и сока', 'Tetra Pak', 'тетрапак', 'пакет от молока', 'пакет от сока', 'комбинированная упаковка'],
      pl: ['Kartony po mleku i soku', 'Tetra Pak', 'karton po mleku', 'karton po soku', 'opakowanie wielomateriałowe'],
    },
    tip: {
      en: "Empty and flattened, with the cap on. Cartons go with plastic, not with paper.",
      lt: 'Tuščius ir suplotus, su kamšteliu. Pakeliai rūšiuojami su plastiku, ne su popieriumi.',
      ru: 'Пустыми и сплющенными, с крышкой. Пакеты сортируют вместе с пластиком, а не с бумагой.',
      pl: 'Puste i spłaszczone, z nakrętką. Kartony segreguje się z plastikiem, nie z papierem.',
    },
  },
  {
    id: 'snack-wrappers',
    category: 'packaging',
    to: ['packaging'],
    names: {
      en: ['Crisp bags and sweet wrappers', 'chips bag', 'crisps', 'candy wrapper', 'chocolate wrapper', 'snack wrapper'],
      lt: ['Traškučių pakeliai ir saldainių popierėliai', 'traškučiai', 'saldainių popierėliai', 'šokolado pakuotė', 'užkandžių pakuotė'],
      ru: ['Пакеты от чипсов и фантики', 'чипсы', 'фантик', 'обёртка от шоколада', 'обёртка'],
      pl: ['Torebki po chipsach i papierki po cukierkach', 'chipsy', 'papierek po cukierku', 'opakowanie po czekoladzie', 'opakowanie po przekąskach'],
    },
  },
  {
    id: 'tins',
    category: 'packaging',
    to: ['packaging'],
    names: {
      en: ['Food tins', 'tin can', 'canned food', 'pet food tin', 'fish tin'],
      lt: ['Konservų skardinės', 'konservai', 'skardinė dėžutė', 'gyvūnų ėdalo skardinė'],
      ru: ['Консервные банки', 'консервы', 'жестяная банка', 'банка от корма'],
      pl: ['Puszki po konserwach', 'konserwy', 'puszka po karmie', 'puszka po rybach'],
    },
    tip: {
      en: 'Scrape them empty. The lid goes in too.',
      lt: 'Gerai ištuštinkite. Dangtelį meskite kartu.',
      ru: 'Хорошо опустошите. Крышку кладите туда же.',
      pl: 'Dokładnie opróżnij. Wieczko wrzuć razem z puszką.',
    },
  },
  {
    id: 'foil',
    category: 'packaging',
    to: ['packaging'],
    names: {
      en: ['Aluminium foil and trays', 'foil', 'tin foil', 'foil tray', 'baking tin', 'disposable grill tray'],
      lt: ['Aliuminio folija ir indeliai', 'folija', 'aliuminio indelis', 'kepimo skardelė', 'vienkartinė grilio skardelė'],
      ru: ['Алюминиевая фольга и формы', 'фольга', 'форма из фольги', 'форма для выпечки', 'одноразовый поддон для гриля'],
      pl: ['Folia aluminiowa i tacki', 'folia aluminiowa', 'sreberko', 'tacka aluminiowa', 'foremka do pieczenia'],
    },
    tip: {
      en: 'Scrape off food and scrunch foil into a ball.',
      lt: 'Nuvalykite maisto likučius, o foliją suglamžykite į kamuoliuką.',
      ru: 'Очистите от остатков еды, а фольгу сомните в комок.',
      pl: 'Usuń resztki jedzenia, a folię zgnieć w kulkę.',
    },
  },
  {
    id: 'styrofoam',
    category: 'packaging',
    // tratc.lt: "polistireninio putplasčio pakuotės" go in the packaging bin; kaunoratc.lt: PS
    // packaging is accepted. nkom.lt/kita.html bans "putplastį" from the packaging bin.
    to: ['packaging'],
    names: {
      en: ['Polystyrene foam packaging', 'styrofoam', 'polystyrene', 'foam', 'foam tray', 'packing foam'],
      lt: ['Putplasčio pakuotės', 'putplastis', 'polistirenas', 'putplasčio padėklas', 'pakavimo putplastis'],
      ru: ['Упаковка из пенопласта', 'пенопласт', 'полистирол', 'лоток из пенопласта', 'упаковочный пенопласт'],
      pl: ['Opakowania ze styropianu', 'styropian', 'polistyren', 'tacka styropianowa', 'styropian z opakowania'],
    },
    tip: {
      en: 'Clean foam packaging goes in the packaging bin. Big blocks and building insulation: bulky waste site.',
      lt: 'Švarios putplasčio pakuotės metamos į pakuočių konteinerį. Dideli gabalai ir statybinis putplastis – į didelių gabaritų atliekų aikštelę.',
      ru: 'Чистую упаковку из пенопласта кладут в контейнер для упаковки. Крупные куски и строительный пенопласт — на площадку крупногабаритных отходов.',
      pl: 'Czyste opakowania ze styropianu wrzuca się do pojemnika na opakowania. Duże bloki i styropian budowlany – do punktu odpadów wielkogabarytowych.',
    },
    regions: {
      nemezio: {
        to: ['site'],
        tip: {
          en: '„Nemėžio komunalininkas“ doesn\'t take foam in the packaging bin: take it to a bulky waste site.',
          lt: '„Nemėžio komunalininkas“ putplasčio į pakuočių konteinerį neleidžia mesti: vežkite jį į didelių gabaritų atliekų aikštelę.',
          ru: '„Nemėžio komunalininkas“ не принимает пенопласт в контейнер для упаковки: отвезите его на площадку крупногабаритных отходов.',
          pl: '„Nemėžio komunalininkas“ nie przyjmuje styropianu w pojemniku na opakowania: zawieź go do punktu odpadów wielkogabarytowych.',
        },
      },
    },
  },
  {
    id: 'coffee-capsules',
    category: 'packaging',
    to: ['household'],
    names: {
      en: ['Coffee capsules', 'coffee pods', 'Nespresso', 'aluminium capsule'],
      lt: ['Kavos kapsulės', 'kapsulės', 'Nespresso', 'aliumininė kapsulė'],
      ru: ['Кофейные капсулы', 'капсулы', 'Nespresso', 'алюминиевая капсула'],
      pl: ['Kapsułki do kawy', 'kapsułki', 'Nespresso', 'kapsułka aluminiowa'],
    },
    tip: {
      en: 'Capsules with coffee inside go in mixed waste.',
      lt: 'Kapsulės su kavos likučiais metamos į mišrias atliekas.',
      ru: 'Капсулы с кофе внутри — в смешанные отходы.',
      pl: 'Kapsułki z kawą w środku – do odpadów zmieszanych.',
    },
    regions: {
      // tratc.lt/atlieku-rusiavimas-2/popieriaus-plastiko-ir-metalo-pakuociu-atliekos.
      mazeikiai: {
        to: ['packaging'],
        tip: {
          en: 'Telšiai region (TRATC): aluminium capsules emptied of coffee go in the packaging bin; compostable ones in food waste.',
          lt: 'Telšių regione (TRATC) aliumininės kapsulės be kavos likučių metamos į pakuočių konteinerį, biologiškai suyrančios – į maisto atliekas.',
          ru: 'В Тельшяйском регионе (TRATC) алюминиевые капсулы без кофе кладут в контейнер для упаковки, биоразлагаемые — в пищевые отходы.',
          pl: 'W regionie telszańskim (TRATC) aluminiowe kapsułki bez kawy wrzuca się do pojemnika na opakowania, biodegradowalne – do odpadów spożywczych.',
        },
      },
    },
  },
  {
    id: 'pots-pans',
    category: 'packaging',
    to: ['site'],
    names: {
      en: ['Pots and pans', 'pot', 'pan', 'frying pan', 'saucepan', 'metal cookware'],
      lt: ['Puodai ir keptuvės', 'puodas', 'keptuvė', 'prikaistuvis', 'metaliniai indai'],
      ru: ['Кастрюли и сковородки', 'кастрюля', 'сковорода', 'сковородка', 'металлическая посуда'],
      pl: ['Garnki i patelnie', 'garnek', 'patelnia', 'rondel', 'metalowe naczynia'],
    },
    tip: {
      en: "Metal things that aren't packaging go to a bulky waste site as scrap metal. Usable ones: give them away.",
      lt: 'Metaliniai daiktai, kurie nėra pakuotės, vežami į didelių gabaritų atliekų aikštelę kaip metalo laužas. Tinkamus naudoti atiduokite kitiems.',
      ru: 'Металлические вещи, которые не являются упаковкой, везут на площадку крупногабаритных отходов как металлолом. Годные отдайте.',
      pl: 'Metalowe rzeczy, które nie są opakowaniem, zawieź do punktu odpadów wielkogabarytowych jako złom. Te w dobrym stanie oddaj.',
    },
    regions: {
      // tratc.lt/atlieku-rusiavimas-2/popieriaus-plastiko-ir-metalo-pakuociu-atliekos lists pots.
      mazeikiai: {
        to: ['packaging'],
        tip: {
          en: 'Telšiai region (TRATC): metal pots and baking trays go in the packaging bin.',
          lt: 'Telšių regione (TRATC) metaliniai puodai ir kepimo skardos metami į pakuočių konteinerį.',
          ru: 'В Тельшяйском регионе (TRATC) металлические кастрюли и противни кладут в контейнер для упаковки.',
          pl: 'W regionie telszańskim (TRATC) metalowe garnki i blachy do pieczenia wrzuca się do pojemnika na opakowania.',
        },
      },
    },
  },

  // --- Glass ------------------------------------------------------------------------------------
  {
    id: 'glass-bottle',
    category: 'glass',
    to: ['deposit', 'glass'],
    names: {
      en: ['Glass bottle', 'wine bottle', 'beer bottle', 'spirits bottle', 'oil bottle'],
      lt: ['Stiklinis butelis', 'vyno butelis', 'alaus butelis', 'degtinės butelis', 'aliejaus butelis'],
      ru: ['Стеклянная бутылка', 'винная бутылка', 'пивная бутылка', 'бутылка из-под водки', 'бутылка из-под масла'],
      pl: ['Szklana butelka', 'butelka po winie', 'butelka po piwie', 'butelka po wódce', 'butelka po oleju'],
    },
    tip: depositTip({
      en: "Otherwise: glass container, empty and without the cap or cork. There's no need to wash it or remove the label.",
      lt: 'Kitu atveju – į stiklo konteinerį, tuščią ir be kamštelio. Plauti ir nuplėšti etiketės nereikia.',
      ru: 'Иначе — в контейнер для стекла, пустой и без пробки. Мыть и снимать этикетку не нужно.',
      pl: 'W przeciwnym razie – do pojemnika na szkło, pustą i bez nakrętki czy korka. Nie trzeba jej myć ani zdejmować etykiety.',
    }),
  },
  {
    id: 'jars',
    category: 'glass',
    to: ['glass'],
    names: {
      en: ['Glass jars', 'jar', 'jam jar', 'pickle jar', 'baby food jar'],
      lt: ['Stiklainiai', 'stiklainis', 'uogienės stiklainis', 'marinatų stiklainis', 'kūdikių maisto stiklainėlis'],
      ru: ['Стеклянные банки', 'банка', 'банка из-под варенья', 'банка из-под солений', 'баночка детского питания'],
      pl: ['Słoiki', 'słoik', 'słoik po dżemie', 'słoik po ogórkach', 'słoiczek po jedzeniu dla dzieci'],
    },
    tip: {
      en: "Empty and without the lid (the lid goes in the packaging bin). There's no need to wash them.",
      lt: 'Tuščius ir be dangtelių (dangteliai metami į pakuočių konteinerį). Plauti nereikia.',
      ru: 'Пустыми и без крышек (крышки — в контейнер для упаковки). Мыть не нужно.',
      pl: 'Puste i bez pokrywek (pokrywki – do pojemnika na opakowania). Nie trzeba ich myć.',
    },
  },
  {
    id: 'cosmetic-glass',
    category: 'glass',
    to: ['glass'],
    names: {
      en: ['Perfume and cosmetics glass bottles', 'perfume bottle', 'perfume', 'cream jar'],
      lt: ['Kvepalų ir kosmetikos buteliukai', 'kvepalai', 'kvepalų buteliukas', 'kremo stiklainėlis'],
      ru: ['Флаконы от духов и косметики', 'духи', 'флакон духов', 'баночка от крема'],
      pl: ['Flakony po perfumach i kosmetykach', 'perfumy', 'flakon', 'słoiczek po kremie'],
    },
    tip: {
      en: 'Empty, without the pump or cap.',
      lt: 'Tuščius, be purkštuko ar dangtelio.',
      ru: 'Пустыми, без распылителя и крышки.',
      pl: 'Puste, bez pompki i nakrętki.',
    },
  },
  {
    id: 'drinking-glass',
    category: 'glass',
    to: ['household'],
    names: {
      en: ['Drinking glasses and glass cookware', 'drinking glass', 'wine glass', 'tumbler', 'ovenproof glass', 'glass bowl', 'crystal'],
      lt: ['Stiklinės ir stikliniai indai', 'stiklinė', 'taurė', 'vyno taurė', 'karščiui atsparus stiklas', 'stiklinis dubuo', 'krištolas'],
      ru: ['Стаканы и стеклянная посуда', 'стакан', 'бокал', 'рюмка', 'жаропрочное стекло', 'стеклянная миска', 'хрусталь'],
      pl: ['Szklanki i naczynia szklane', 'szklanka', 'kieliszek', 'naczynie żaroodporne', 'szklana miska', 'kryształ'],
    },
    tip: notGlassTip,
  },
  {
    id: 'mirror',
    category: 'glass',
    to: ['household'],
    names: {
      en: ['Mirror', 'mirrors', 'broken mirror'],
      lt: ['Veidrodis', 'veidrodžiai', 'sudužęs veidrodis'],
      ru: ['Зеркало', 'зеркала', 'разбитое зеркало'],
      pl: ['Lustro', 'lustra', 'stłuczone lustro'],
    },
    tip: {
      en: 'Not in the glass container. Big mirrors: bulky waste site.',
      lt: 'Ne į stiklo konteinerį. Didelius veidrodžius vežkite į didelių gabaritų atliekų aikštelę.',
      ru: 'Не в контейнер для стекла. Большие зеркала — на площадку крупногабаритных отходов.',
      pl: 'Nie do pojemnika na szkło. Duże lustra – do punktu odpadów wielkogabarytowych.',
    },
  },
  {
    id: 'window-glass',
    category: 'glass',
    to: ['site'],
    names: {
      en: ['Window glass', 'window', 'glass pane', 'double glazing', 'car glass', 'windscreen'],
      lt: ['Langų stiklas', 'langas', 'stiklo lakštas', 'stiklo paketas', 'automobilio stiklas'],
      ru: ['Оконное стекло', 'окно', 'стеклопакет', 'автомобильное стекло', 'лобовое стекло'],
      pl: ['Szyba okienna', 'szyba', 'okno', 'szyba zespolona', 'szyba samochodowa'],
    },
    tip: {
      en: 'Not in the glass container: it is a different kind of glass.',
      lt: 'Ne į stiklo konteinerį: tai kitokios rūšies stiklas.',
      ru: 'Не в контейнер для стекла: это другой вид стекла.',
      pl: 'Nie do pojemnika na szkło: to inny rodzaj szkła.',
    },
  },
  {
    id: 'grave-candles',
    category: 'glass',
    // tratc.lt/atlieku-rusiavimas-2/stiklas-2: empty, clean glass candle covers.
    to: ['glass'],
    names: {
      en: ['Grave candles', 'candle holder', 'cemetery candle', 'candle glass'],
      lt: ['Kapų žvakės', 'žvakė', 'kapų žvakidė', 'žvakių stiklas', 'lampelė'],
      ru: ['Кладбищенские свечи', 'лампадка', 'свеча', 'стеклянный подсвечник'],
      pl: ['Znicze', 'znicz', 'świeczka', 'szklany znicz'],
    },
    tip: {
      en: 'The glass cover goes in the glass container once empty and clean. Wax leftovers go in mixed waste.',
      lt: 'Stiklinį gaubtą, kai jis tuščias ir švarus, meskite į stiklo konteinerį. Vaško likučiai metami į mišrias atliekas.',
      ru: 'Стеклянный колпак, пустой и чистый, — в контейнер для стекла. Остатки воска — в смешанные отходы.',
      pl: 'Szklany klosz, pusty i czysty, wrzuć do pojemnika na szkło. Resztki wosku – do odpadów zmieszanych.',
    },
  },

  // --- Garden -----------------------------------------------------------------------------------
  {
    id: 'grass',
    category: 'garden',
    to: ['green'],
    compost: true,
    names: {
      en: ['Grass clippings', 'grass', 'lawn cuttings', 'mown grass'],
      lt: ['Nupjauta žolė', 'žolė', 'vejos žolė', 'šienas'],
      ru: ['Скошенная трава', 'трава', 'газон', 'сено'],
      pl: ['Skoszona trawa', 'trawa', 'trawnik', 'siano'],
    },
    tip: {
      en: 'Loose, without plastic bags, soil or stones.',
      lt: 'Be plastikinių maišų, žemių ir akmenų.',
      ru: 'Без пластиковых мешков, земли и камней.',
      pl: 'Bez plastikowych worków, ziemi i kamieni.',
    },
  },
  {
    id: 'leaves',
    category: 'garden',
    to: ['green'],
    compost: true,
    names: {
      en: ['Leaves', 'fallen leaves', 'autumn leaves'],
      lt: ['Lapai', 'nukritę lapai', 'rudens lapai'],
      ru: ['Листья', 'опавшие листья', 'осенние листья'],
      pl: ['Liście', 'opadłe liście', 'jesienne liście'],
    },
  },
  {
    id: 'branches',
    category: 'garden',
    to: ['green'],
    compost: true,
    names: {
      en: ['Branches and hedge trimmings', 'branches', 'twigs', 'hedge cuttings', 'pruning', 'bushes'],
      lt: ['Šakos ir gyvatvorės genėjimo atliekos', 'šakos', 'šakelės', 'gyvatvorė', 'genėjimas', 'krūmai'],
      ru: ['Ветки и обрезки живой изгороди', 'ветки', 'сучья', 'обрезка', 'кусты'],
      pl: ['Gałęzie i ścinki żywopłotu', 'gałęzie', 'gałązki', 'żywopłot', 'przycinanie', 'krzewy'],
    },
    tip: {
      en: 'Lots of them, or thick branches: green waste site.',
      lt: 'Didelį kiekį ar storas šakas vežkite į žaliųjų atliekų aikštelę.',
      ru: 'Много веток или толстые ветки — на площадку для зелёных отходов.',
      pl: 'Dużo gałęzi lub grube gałęzie – do punktu odpadów zielonych.',
    },
  },
  {
    id: 'weeds',
    category: 'garden',
    to: ['green'],
    compost: true,
    names: {
      en: ['Weeds and vegetable garden waste', 'weeds', 'garden plants', 'potato tops', 'dead plants'],
      lt: ['Piktžolės ir daržo atliekos', 'piktžolės', 'daržo atliekos', 'bulvienojai', 'nuvytę augalai'],
      ru: ['Сорняки и огородные отходы', 'сорняки', 'ботва', 'огородные отходы', 'завядшие растения'],
      pl: ['Chwasty i odpady z warzywnika', 'chwasty', 'nać', 'łęty ziemniaków', 'zwiędłe rośliny'],
    },
    tip: {
      en: 'Shake off the soil first.',
      lt: 'Pirmiausia nukratykite žemes.',
      ru: 'Сначала стряхните землю.',
      pl: 'Najpierw otrząśnij ziemię.',
    },
  },
  {
    id: 'fallen-fruit',
    category: 'garden',
    to: ['green'],
    compost: true,
    names: {
      en: ['Fallen fruit', 'windfall apples', 'rotten apples', 'garden fruit'],
      lt: ['Nukritę vaisiai', 'nukritę obuoliai', 'supuvę obuoliai', 'sodo vaisiai'],
      ru: ['Падалица', 'опавшие яблоки', 'гнилые яблоки', 'садовые фрукты'],
      pl: ['Spady owoców', 'spady', 'zgniłe jabłka', 'owoce z ogrodu'],
    },
  },
  {
    id: 'christmas-tree',
    category: 'garden',
    to: ['green'],
    compost: true,
    names: {
      en: ['Christmas tree', 'xmas tree', 'fir tree', 'spruce'],
      lt: ['Kalėdų eglutė', 'eglutė', 'eglė', 'kalėdinė eglė'],
      ru: ['Новогодняя ёлка', 'ёлка', 'ель', 'рождественская ёлка'],
      pl: ['Choinka', 'choinka świąteczna', 'świerk', 'jodła'],
    },
    tip: {
      en: 'Take off all decorations, tinsel and the stand.',
      lt: 'Nuimkite visus žaisliukus, blizgučius ir stovą.',
      ru: 'Снимите все игрушки, мишуру и подставку.',
      pl: 'Zdejmij wszystkie ozdoby, łańcuchy i stojak.',
    },
  },
  {
    id: 'stumps',
    category: 'garden',
    // kaunoratc.lt/zaka: stumps up to 500 kg a year free.
    to: ['greenSite'],
    names: {
      en: ['Tree stumps and roots', 'stump', 'roots'],
      lt: ['Kelmai ir šaknys', 'kelmas', 'šaknys'],
      ru: ['Пни и корни', 'пень', 'корни', 'корчи'],
      pl: ['Pniaki i korzenie', 'pniak', 'korzenie', 'karpy'],
    },
    tip: {
      en: 'Composting sites take them within yearly limits.',
      lt: 'Kompostavimo aikštelės juos priima neviršijant metinių limitų.',
      ru: 'Площадки компостирования принимают их в пределах годовых лимитов.',
      pl: 'Kompostownie przyjmują je w ramach rocznych limitów.',
    },
  },
  {
    id: 'sawdust',
    category: 'garden',
    to: ['green'],
    compost: true,
    names: {
      en: ['Sawdust and wood chips', 'sawdust', 'wood chips', 'bark'],
      lt: ['Pjuvenos ir medžio drožlės', 'pjuvenos', 'drožlės', 'žievė'],
      ru: ['Опилки и щепа', 'опилки', 'щепа', 'кора'],
      pl: ['Trociny i zrębki', 'trociny', 'zrębki', 'kora'],
    },
    tip: {
      en: 'Only from untreated wood.',
      lt: 'Tik iš neapdorotos medienos.',
      ru: 'Только от необработанной древесины.',
      pl: 'Tylko z nieobrobionego chemicznie drewna.',
    },
  },

  // --- Hazardous and electronics ----------------------------------------------------------------
  {
    id: 'batteries',
    category: 'hazardous',
    to: ['shop', 'site'],
    names: {
      en: ['Batteries', 'battery', 'AA battery', 'button cell', 'rechargeable battery', 'power bank'],
      lt: ['Baterijos', 'baterija', 'pirštukinė baterija', 'sagos tipo baterija', 'pakraunama baterija', 'išorinė baterija'],
      ru: ['Батарейки', 'батарейка', 'пальчиковая батарейка', 'батарейка-таблетка', 'аккумулятор', 'повербанк'],
      pl: ['Baterie', 'bateria', 'paluszki', 'bateria guzikowa', 'akumulatorek', 'powerbank'],
    },
    tip: {
      en: 'Hazardous waste: never in mixed waste or packaging. Shops that sell batteries have collection boxes.',
      lt: 'Pavojingos atliekos: niekada nemeskite į mišrias atliekas ar pakuotes. Baterijas parduodančiose parduotuvėse yra surinkimo dėžutės.',
      ru: 'Опасные отходы: никогда не выбрасывайте в смешанные отходы или упаковку. В магазинах, где продают батарейки, есть ящики для сбора.',
      pl: 'Odpady niebezpieczne: nigdy do odpadów zmieszanych ani opakowań. W sklepach sprzedających baterie są pojemniki na zużyte.',
    },
  },
  {
    id: 'car-battery',
    category: 'hazardous',
    to: ['site', 'shop'],
    names: {
      en: ['Car battery', 'lead battery', 'accumulator'],
      lt: ['Automobilio akumuliatorius', 'akumuliatorius', 'švino akumuliatorius'],
      ru: ['Автомобильный аккумулятор', 'аккумулятор', 'свинцовый аккумулятор'],
      pl: ['Akumulator samochodowy', 'akumulator', 'akumulator kwasowy'],
    },
    tip: hazardousTip,
  },
  {
    id: 'small-electronics',
    category: 'hazardous',
    to: ['shop', 'site'],
    names: {
      en: ['Phones and small electronics', 'phone', 'mobile phone', 'laptop', 'tablet', 'kettle', 'hair dryer', 'toaster', 'headphones', 'remote control', 'electric toothbrush'],
      lt: ['Telefonai ir smulki elektronika', 'telefonas', 'mobilusis telefonas', 'nešiojamas kompiuteris', 'planšetė', 'virdulys', 'plaukų džiovintuvas', 'skrudintuvas', 'ausinės', 'pultelis', 'elektrinis dantų šepetėlis'],
      ru: ['Телефоны и мелкая электроника', 'телефон', 'мобильный телефон', 'ноутбук', 'планшет', 'чайник', 'фен', 'тостер', 'наушники', 'пульт', 'электрическая зубная щётка'],
      pl: ['Telefony i drobna elektronika', 'telefon', 'komórka', 'laptop', 'tablet', 'czajnik', 'suszarka do włosów', 'toster', 'słuchawki', 'pilot', 'elektryczna szczoteczka'],
    },
    tip: {
      en: `${electronicsTip.en} Wipe your data from phones and computers first.`,
      lt: `${electronicsTip.lt} Iš telefonų ir kompiuterių pirmiausia ištrinkite savo duomenis.`,
      ru: `${electronicsTip.ru} С телефонов и компьютеров сначала удалите свои данные.`,
      pl: `${electronicsTip.pl} Z telefonów i komputerów najpierw usuń swoje dane.`,
    },
  },
  {
    id: 'large-appliances',
    category: 'hazardous',
    to: ['shop', 'site'],
    names: {
      en: ['Large appliances', 'fridge', 'freezer', 'washing machine', 'dishwasher', 'oven', 'TV', 'television', 'microwave'],
      lt: ['Didelė buitinė technika', 'šaldytuvas', 'šaldiklis', 'skalbimo mašina', 'indaplovė', 'orkaitė', 'televizorius', 'mikrobangų krosnelė'],
      ru: ['Крупная бытовая техника', 'холодильник', 'морозилка', 'стиральная машина', 'посудомоечная машина', 'духовка', 'телевизор', 'микроволновка'],
      pl: ['Duże AGD', 'lodówka', 'zamrażarka', 'pralka', 'zmywarka', 'piekarnik', 'telewizor', 'mikrofalówka'],
    },
    tip: {
      en: 'Hand it in whole, not taken apart. Shops that sell appliances take old ones back.',
      lt: 'Atiduokite visą, neišardytą. Buitinę techniką parduodančios parduotuvės priima senus prietaisus.',
      ru: 'Сдавайте целиком, не разбирая. Магазины, продающие технику, принимают старые приборы.',
      pl: 'Oddaj w całości, nierozebrane. Sklepy sprzedające AGD przyjmują stare urządzenia.',
    },
  },
  {
    id: 'cables',
    category: 'hazardous',
    to: ['shop', 'site'],
    names: {
      en: ['Cables and chargers', 'cable', 'charger', 'wire', 'extension cord', 'USB cable', 'adapter'],
      lt: ['Laidai ir įkrovikliai', 'laidas', 'įkroviklis', 'ilgintuvas', 'USB laidas', 'adapteris'],
      ru: ['Кабели и зарядки', 'кабель', 'зарядка', 'провод', 'удлинитель', 'USB-кабель', 'адаптер'],
      pl: ['Kable i ładowarki', 'kabel', 'ładowarka', 'przewód', 'przedłużacz', 'kabel USB', 'zasilacz'],
    },
    tip: electronicsTip,
  },
  {
    id: 'light-bulbs',
    category: 'hazardous',
    to: ['shop', 'site'],
    names: {
      en: ['Light bulbs', 'bulb', 'LED bulb', 'energy-saving bulb', 'fluorescent tube', 'halogen bulb', 'lamp'],
      lt: ['Lemputės', 'lemputė', 'LED lemputė', 'taupioji lemputė', 'liuminescencinė lempa', 'halogeninė lemputė', 'kaitinamoji lemputė'],
      ru: ['Лампочки', 'лампочка', 'светодиодная лампа', 'энергосберегающая лампа', 'люминесцентная лампа', 'галогенная лампа', 'лампа накаливания'],
      pl: ['Żarówki', 'żarówka', 'żarówka LED', 'świetlówka', 'żarówka energooszczędna', 'żarówka halogenowa'],
    },
    tip: {
      en: "Not in the glass container. Shops that sell bulbs take used ones back. Energy-saving bulbs and tubes contain mercury: don't break them.",
      lt: 'Ne į stiklo konteinerį. Lemputes parduodančios parduotuvės priima panaudotas. Taupiosiose lemputėse ir lempose yra gyvsidabrio: nedaužykite jų.',
      ru: 'Не в контейнер для стекла. Магазины, продающие лампочки, принимают использованные. В энергосберегающих лампах есть ртуть: не разбивайте их.',
      pl: 'Nie do pojemnika na szkło. Sklepy sprzedające żarówki przyjmują zużyte. Świetlówki zawierają rtęć: nie tłucz ich.',
    },
  },
  {
    id: 'vapes',
    category: 'hazardous',
    to: ['shop', 'site'],
    names: {
      en: ['E-cigarettes and vapes', 'vape', 'e-cigarette', 'disposable vape', 'IQOS'],
      lt: ['Elektroninės cigaretės', 'el. cigaretė', 'elektroninė cigaretė', 'vienkartinė elektroninė cigaretė', 'veipas', 'IQOS'],
      ru: ['Электронные сигареты и вейпы', 'вейп', 'электронная сигарета', 'одноразовая электронная сигарета', 'IQOS'],
      pl: ['E-papierosy', 'e-papieros', 'wape', 'jednorazowy e-papieros', 'IQOS'],
    },
    tip: {
      en: 'They contain a battery: not in packaging or mixed waste.',
      lt: 'Jose yra baterija: nemeskite į pakuotes ar mišrias atliekas.',
      ru: 'В них есть батарейка: не выбрасывайте в упаковку или смешанные отходы.',
      pl: 'Zawierają baterię: nie wyrzucaj ich do opakowań ani odpadów zmieszanych.',
    },
  },
  {
    id: 'cds',
    category: 'hazardous',
    to: ['site'],
    names: {
      en: ['CDs, DVDs and cassettes', 'CD', 'DVD', 'video cassette', 'tape', 'vinyl record'],
      lt: ['CD, DVD diskai ir kasetės', 'diskas', 'CD', 'DVD', 'vaizdajuostė', 'kasetė', 'plokštelė'],
      ru: ['CD, DVD и кассеты', 'диск', 'компакт-диск', 'видеокассета', 'кассета', 'пластинка'],
      pl: ['Płyty CD, DVD i kasety', 'płyta', 'płyta CD', 'kaseta wideo', 'kaseta', 'płyta winylowa'],
    },
    tip: {
      en: "They aren't packaging. Bulky waste sites take them with electronics.",
      lt: 'Tai ne pakuotės. Didelių gabaritų atliekų aikštelės juos priima kartu su elektronika.',
      ru: 'Это не упаковка. Площадки крупногабаритных отходов принимают их вместе с электроникой.',
      pl: 'To nie opakowania. Punkty odpadów wielkogabarytowych przyjmują je razem z elektroniką.',
    },
  },
  {
    id: 'medicines',
    category: 'hazardous',
    to: ['pharmacy'],
    names: {
      en: ['Medicines', 'medicine', 'pills', 'tablets', 'expired medicines', 'syrup'],
      lt: ['Vaistai', 'vaistas', 'tabletės', 'piliulės', 'pasibaigusio galiojimo vaistai', 'sirupas'],
      ru: ['Лекарства', 'лекарство', 'таблетки', 'просроченные лекарства', 'сироп'],
      pl: ['Leki', 'lek', 'tabletki', 'przeterminowane leki', 'syrop'],
    },
    tip: {
      en: 'Any pharmacy takes them free of charge; veterinary medicines go to a veterinary pharmacy. The cardboard box goes in the packaging bin. Never flush medicines down the toilet.',
      lt: 'Bet kuri vaistinė juos priima nemokamai, veterinarinius vaistus – veterinarijos vaistinės. Kartoninę dėžutę meskite į pakuočių konteinerį. Niekada nepilkite vaistų į kanalizaciją.',
      ru: 'Любая аптека принимает их бесплатно, ветеринарные лекарства — ветеринарные аптеки. Картонную коробку положите в контейнер для упаковки. Никогда не смывайте лекарства в унитаз.',
      pl: 'Każda apteka przyjmuje je bezpłatnie, leki weterynaryjne – apteki weterynaryjne. Kartonowe pudełko wrzuć do pojemnika na opakowania. Nigdy nie spłukuj leków w toalecie.',
    },
  },
  {
    id: 'thermometer',
    category: 'hazardous',
    to: ['site'],
    names: {
      en: ['Mercury thermometer', 'thermometer', 'mercury'],
      lt: ['Gyvsidabrio termometras', 'termometras', 'gyvsidabris'],
      ru: ['Ртутный градусник', 'градусник', 'термометр', 'ртуть'],
      pl: ['Termometr rtęciowy', 'termometr', 'rtęć'],
    },
    tip: {
      en: 'Hazardous waste. Electronic thermometers go to electronics collection.',
      lt: 'Pavojingos atliekos. Elektroniniai termometrai atiduodami kaip elektronika.',
      ru: 'Опасные отходы. Электронные градусники сдают как электронику.',
      pl: 'Odpady niebezpieczne. Termometry elektroniczne oddaje się jako elektronikę.',
    },
  },
  {
    id: 'paint',
    category: 'hazardous',
    to: ['site'],
    names: {
      en: ['Paint, varnish and glue', 'paint', 'paint tin', 'varnish', 'glue', 'paint bucket', 'primer'],
      lt: ['Dažai, lakai ir klijai', 'dažai', 'dažų skardinė', 'lakas', 'klijai', 'dažų kibiras', 'gruntas'],
      ru: ['Краска, лак и клей', 'краска', 'банка с краской', 'лак', 'клей', 'ведро из-под краски', 'грунтовка'],
      pl: ['Farby, lakiery i kleje', 'farba', 'puszka po farbie', 'lakier', 'klej', 'wiadro po farbie', 'grunt'],
    },
    tip: hazardousTip,
  },
  {
    id: 'chemicals',
    category: 'hazardous',
    to: ['site'],
    names: {
      en: ['Household chemicals', 'chemicals', 'solvent', 'drain cleaner', 'pesticide', 'weed killer', 'antifreeze'],
      lt: ['Buitinė chemija', 'chemikalai', 'tirpiklis', 'kanalizacijos valiklis', 'pesticidai', 'herbicidas', 'antifrizas'],
      ru: ['Бытовая химия', 'химикаты', 'растворитель', 'средство для труб', 'пестициды', 'гербицид', 'антифриз'],
      pl: ['Chemia gospodarcza', 'chemikalia', 'rozpuszczalnik', 'udrażniacz do rur', 'pestycydy', 'środek chwastobójczy', 'płyn do chłodnic'],
    },
    tip: hazardousTip,
  },
  {
    id: 'motor-oil',
    category: 'hazardous',
    to: ['site'],
    names: {
      en: ['Motor oil and car fluids', 'engine oil', 'oil filter', 'brake fluid', 'car oil'],
      lt: ['Variklio alyva ir automobilių skysčiai', 'alyva', 'tepalai', 'tepalų filtras', 'stabdžių skystis'],
      ru: ['Моторное масло и автожидкости', 'моторное масло', 'масляный фильтр', 'тормозная жидкость'],
      pl: ['Olej silnikowy i płyny samochodowe', 'olej silnikowy', 'filtr oleju', 'płyn hamulcowy'],
    },
    tip: {
      en: 'Car service stations also take used oil free of charge.',
      lt: 'Panaudotą alyvą nemokamai priima ir automobilių servisai.',
      ru: 'Отработанное масло бесплатно принимают и автосервисы.',
      pl: 'Zużyty olej bezpłatnie przyjmują też warsztaty samochodowe.',
    },
  },
  {
    id: 'aerosol',
    category: 'hazardous',
    // nemenkom.lt, nkom.lt: no aerosol cans in the packaging bin. tratc.lt: empty ones are fine.
    to: ['site'],
    names: {
      en: ['Aerosol cans', 'spray can', 'deodorant spray', 'hairspray', 'spray paint', 'whipped cream can'],
      lt: ['Aerozolių balionėliai', 'aerozolis', 'purškiklis', 'dezodorantas', 'plaukų lakas', 'dažų aerozolis', 'grietinėlės balionėlis'],
      ru: ['Аэрозольные баллончики', 'аэрозоль', 'спрей', 'дезодорант', 'лак для волос', 'баллончик с краской', 'баллончик сливок'],
      pl: ['Puszki po aerozolach', 'aerozol', 'spray', 'dezodorant', 'lakier do włosów', 'farba w sprayu', 'bita śmietana w sprayu'],
    },
    tip: {
      en: "They can hold pressurised leftovers, so they don't go in the packaging bin.",
      lt: 'Juose gali likti suslėgto turinio, todėl į pakuočių konteinerį jie nemetami.',
      ru: 'В них может остаться содержимое под давлением, поэтому в контейнер для упаковки их не кладут.',
      pl: 'Mogą zawierać resztki pod ciśnieniem, więc nie wrzuca się ich do pojemnika na opakowania.',
    },
    regions: {
      mazeikiai: {
        to: ['packaging'],
        tip: {
          en: 'Telšiai region (TRATC): completely empty cans go in the packaging bin; ones with leftovers to a bulky waste site.',
          lt: 'Telšių regione (TRATC) visiškai tušti balionėliai metami į pakuočių konteinerį, su likučiais – vežami į didelių gabaritų atliekų aikštelę.',
          ru: 'В Тельшяйском регионе (TRATC) полностью пустые баллончики кладут в контейнер для упаковки, с остатками — везут на площадку крупногабаритных отходов.',
          pl: 'W regionie telszańskim (TRATC) całkiem puste puszki wrzuca się do pojemnika na opakowania, z resztkami – do punktu odpadów wielkogabarytowych.',
        },
      },
    },
  },

  // --- Bulky and building -----------------------------------------------------------------------
  {
    id: 'furniture',
    category: 'bulky',
    to: ['site'],
    names: {
      en: ['Furniture', 'sofa', 'couch', 'chair', 'table', 'wardrobe', 'bed', 'cabinet', 'armchair'],
      lt: ['Baldai', 'sofa', 'kėdė', 'stalas', 'spinta', 'lova', 'spintelė', 'fotelis'],
      ru: ['Мебель', 'диван', 'стул', 'стол', 'шкаф', 'кровать', 'тумбочка', 'кресло'],
      pl: ['Meble', 'sofa', 'kanapa', 'krzesło', 'stół', 'szafa', 'łóżko', 'szafka', 'fotel'],
    },
    tip: giveAwayTip,
    regions: {
      ...vilnius({ tip: dismantleTip }),
      // nemenkom.lt/dideliu-gabaritu-ir-pavojingu-atlieku-surinkimas: collection on request.
      nemencine: {
        tip: {
          en: `${dismantleTip.en} „Nemenčinės komunalininkas“ also collects bulky waste on request.`,
          lt: `${dismantleTip.lt} „Nemenčinės komunalininkas“ didelių gabaritų atliekas taip pat išveža pagal prašymą.`,
          ru: `${dismantleTip.ru} „Nemenčinės komunalininkas“ также вывозит крупногабаритные отходы по заявке.`,
          pl: `${dismantleTip.pl} „Nemenčinės komunalininkas“ odbiera też odpady wielkogabarytowe na zgłoszenie.`,
        },
      },
    },
  },
  {
    id: 'mattress',
    category: 'bulky',
    to: ['site'],
    names: {
      en: ['Mattress', 'mattresses', 'bed mattress'],
      lt: ['Čiužinys', 'čiužiniai', 'lovos čiužinys'],
      ru: ['Матрас', 'матрасы', 'матрац'],
      pl: ['Materac', 'materace'],
    },
  },
  {
    id: 'carpet',
    category: 'bulky',
    to: ['site'],
    names: {
      en: ['Carpets and rugs', 'carpet', 'rug', 'linoleum'],
      lt: ['Kilimai', 'kilimas', 'kilimėlis', 'linoleumas'],
      ru: ['Ковры', 'ковёр', 'коврик', 'линолеум'],
      pl: ['Dywany', 'dywan', 'chodnik', 'wykładzina', 'linoleum'],
    },
    tip: {
      en: "Textile containers don't take them.",
      lt: 'Į tekstilės konteinerius jų mesti negalima.',
      ru: 'В контейнеры для текстиля их не принимают.',
      pl: 'Pojemniki na tekstylia ich nie przyjmują.',
    },
  },
  {
    id: 'pillows',
    category: 'bulky',
    // kaunoratc.lt: textile containers don't take pillows and cushions.
    to: ['site'],
    names: {
      en: ['Pillows and cushions', 'pillow', 'cushion', 'sofa cushion'],
      lt: ['Pagalvės ir pagalvėlės', 'pagalvė', 'pagalvėlė', 'sofos pagalvėlė'],
      ru: ['Подушки', 'подушка', 'диванная подушка'],
      pl: ['Poduszki', 'poduszka', 'poduszka na kanapę'],
    },
    tip: {
      en: "Textile containers don't take them.",
      lt: 'Į tekstilės konteinerius jų mesti negalima.',
      ru: 'В контейнеры для текстиля их не принимают.',
      pl: 'Pojemniki na tekstylia ich nie przyjmują.',
    },
  },
  {
    id: 'tyres',
    category: 'bulky',
    to: ['site'],
    names: {
      en: ['Tyres', 'tires', 'car tyres', 'bicycle tyre', 'wheels'],
      lt: ['Padangos', 'padanga', 'automobilio padangos', 'dviračio padanga', 'ratai'],
      ru: ['Шины', 'покрышки', 'автомобильные шины', 'велосипедная шина', 'колёса'],
      pl: ['Opony', 'opona', 'opony samochodowe', 'opona rowerowa', 'koła'],
    },
    tip: {
      en: 'Sites take a few car tyres per resident a year for free. Tyre shops take back as many as you buy.',
      lt: 'Aikštelės nemokamai priima kelias lengvųjų automobilių padangas vienam gyventojui per metus. Padangų pardavėjai priima tiek, kiek perkate.',
      ru: 'Площадки бесплатно принимают несколько автомобильных шин на жителя в год. Продавцы шин принимают столько, сколько вы покупаете.',
      pl: 'Punkty przyjmują bezpłatnie kilka opon samochodowych na mieszkańca rocznie. Sklepy z oponami przyjmują tyle, ile kupujesz.',
    },
    regions: {
      // nemenkom.lt: "ne daugiau kaip 4 naudotas automobilio padangas" a year.
      ...vilnius({
        tip: {
          en: 'Vilnius district sites take up to 4 car tyres per resident a year for free. Tyre shops take back as many as you buy.',
          lt: 'Vilniaus rajono aikštelės nemokamai priima iki 4 automobilio padangų vienam gyventojui per metus. Padangų pardavėjai priima tiek, kiek perkate.',
          ru: 'Площадки Вильнюсского района бесплатно принимают до 4 автомобильных шин на жителя в год. Продавцы шин принимают столько, сколько вы покупаете.',
          pl: 'Punkty w rejonie wileńskim przyjmują bezpłatnie do 4 opon samochodowych na mieszkańca rocznie. Sklepy z oponami przyjmują tyle, ile kupujesz.',
        },
      }),
      // kaunoratc.lt/dgasa: up to 5 a year, no truck or farm machinery tyres.
      kauno: {
        tip: {
          en: 'Kaunas region sites take up to 5 tyres per resident a year for free (not truck or tractor tyres). Tyre shops take back as many as you buy.',
          lt: 'Kauno regiono aikštelės nemokamai priima iki 5 padangų vienam gyventojui per metus (ne sunkvežimių ar traktorių). Padangų pardavėjai priima tiek, kiek perkate.',
          ru: 'Площадки Каунасского региона бесплатно принимают до 5 шин на жителя в год (кроме грузовых и тракторных). Продавцы шин принимают столько, сколько вы покупаете.',
          pl: 'Punkty w regionie kowieńskim przyjmują bezpłatnie do 5 opon na mieszkańca rocznie (bez opon ciężarowych i ciągnikowych). Sklepy z oponami przyjmują tyle, ile kupujesz.',
        },
      },
    },
  },
  {
    id: 'construction',
    category: 'bulky',
    to: ['site'],
    names: {
      en: ['Renovation and building waste', 'rubble', 'bricks', 'concrete', 'tiles', 'plaster', 'plasterboard', 'drywall', 'insulation', 'mineral wool'],
      lt: ['Remonto ir statybos atliekos', 'statybinės atliekos', 'plytos', 'betonas', 'plytelės', 'tinkas', 'gipso kartonas', 'izoliacija', 'mineralinė vata'],
      ru: ['Строительный и ремонтный мусор', 'строительный мусор', 'кирпич', 'бетон', 'плитка', 'штукатурка', 'гипсокартон', 'утеплитель', 'минвата'],
      pl: ['Odpady remontowe i budowlane', 'gruz', 'cegły', 'beton', 'płytki', 'tynk', 'płyta gipsowa', 'izolacja', 'wełna mineralna'],
    },
    tip: {
      en: 'Never in any container. Sites take limited amounts from home renovation for free.',
      lt: 'Niekada nemeskite į jokį konteinerį. Aikštelės nemokamai priima ribotą būsto remonto atliekų kiekį.',
      ru: 'Никогда не выбрасывайте в контейнеры. Площадки бесплатно принимают ограниченное количество отходов от ремонта жилья.',
      pl: 'Nigdy do żadnego pojemnika. Punkty przyjmują bezpłatnie ograniczoną ilość odpadów z remontu mieszkania.',
    },
    regions: {
      // nemenkom.lt: up to 250 kg of mixed building waste per visit; vaatc.lt: sorted waste only.
      ...vilnius({
        tip: {
          en: 'Never in any container. Vilnius district sites take up to 250 kg per visit for free, sorted, from home renovation only.',
          lt: 'Niekada nemeskite į jokį konteinerį. Vilniaus rajono aikštelės nemokamai priima iki 250 kg per kartą, tik išrūšiuotas būsto remonto atliekas.',
          ru: 'Никогда не выбрасывайте в контейнеры. Площадки Вильнюсского района бесплатно принимают до 250 кг за раз, только рассортированные отходы от ремонта жилья.',
          pl: 'Nigdy do żadnego pojemnika. Punkty w rejonie wileńskim przyjmują bezpłatnie do 250 kg naraz, tylko posegregowane odpady z remontu mieszkania.',
        },
      }),
      // kaunoratc.lt/dgasa: up to 300 kg per resident a year.
      kauno: {
        tip: {
          en: 'Never in any container. Kaunas region sites take up to 300 kg per resident a year for free.',
          lt: 'Niekada nemeskite į jokį konteinerį. Kauno regiono aikštelės nemokamai priima iki 300 kg vienam gyventojui per metus.',
          ru: 'Никогда не выбрасывайте в контейнеры. Площадки Каунасского региона бесплатно принимают до 300 кг на жителя в год.',
          pl: 'Nigdy do żadnego pojemnika. Punkty w regionie kowieńskim przyjmują bezpłatnie do 300 kg na mieszkańca rocznie.',
        },
      },
    },
  },
  {
    id: 'windows-doors',
    category: 'bulky',
    to: ['site'],
    names: {
      en: ['Windows and doors', 'window frame', 'door', 'old windows'],
      lt: ['Langai ir durys', 'langų rėmai', 'durys', 'seni langai'],
      ru: ['Окна и двери', 'оконная рама', 'дверь', 'старые окна'],
      pl: ['Okna i drzwi', 'rama okienna', 'drzwi', 'stare okna'],
    },
  },
  {
    id: 'wood',
    category: 'bulky',
    to: ['site'],
    names: {
      en: ['Wood and boards', 'planks', 'pallets', 'chipboard', 'laminate', 'timber'],
      lt: ['Mediena ir lentos', 'lentos', 'paletės', 'medžio drožlių plokštė', 'laminatas', 'mediena'],
      ru: ['Древесина и доски', 'доски', 'поддоны', 'ДСП', 'ламинат', 'дерево'],
      pl: ['Drewno i deski', 'deski', 'palety', 'płyta wiórowa', 'panele', 'drewno'],
    },
  },
  {
    id: 'asbestos',
    category: 'bulky',
    to: ['site'],
    names: {
      en: ['Asbestos roofing', 'asbestos', 'slate', 'eternit', 'corrugated roofing sheets'],
      lt: ['Asbestinis šiferis', 'asbestas', 'šiferis', 'asbesto plokštės'],
      ru: ['Асбестовый шифер', 'асбест', 'шифер', 'этернит'],
      pl: ['Eternit', 'azbest', 'płyty azbestowe', 'płyty faliste'],
    },
    tip: {
      en: 'Hazardous: wrap it tightly and keep it apart from other waste. Not every site takes it, and there are limits.',
      lt: 'Pavojingos atliekos: sandariai supakuokite ir laikykite atskirai nuo kitų atliekų. Ne visos aikštelės jį priima, taikomi limitai.',
      ru: 'Опасные отходы: плотно упакуйте и держите отдельно от других отходов. Принимают не все площадки, есть лимиты.',
      pl: 'Odpady niebezpieczne: szczelnie zapakuj i trzymaj osobno od innych odpadów. Nie każdy punkt go przyjmuje, obowiązują limity.',
    },
  },
  {
    id: 'bicycle',
    category: 'bulky',
    to: ['site'],
    names: {
      en: ['Bicycles, scooters and prams', 'bike', 'bicycle', 'scooter', 'pram', 'stroller'],
      lt: ['Dviračiai, paspirtukai ir vežimėliai', 'dviratis', 'paspirtukas', 'vežimėlis'],
      ru: ['Велосипеды, самокаты и коляски', 'велосипед', 'самокат', 'коляска'],
      pl: ['Rowery, hulajnogi i wózki', 'rower', 'hulajnoga', 'wózek'],
    },
    tip: {
      en: 'Usable ones: give them away. Electric bikes and scooters go to electronics collection, because of the battery.',
      lt: 'Tinkamus naudoti atiduokite kitiems. Elektriniai dviračiai ir paspirtukai dėl baterijos atiduodami kaip elektronika.',
      ru: 'Годные отдайте. Электровелосипеды и электросамокаты из-за батареи сдают как электронику.',
      pl: 'Te w dobrym stanie oddaj. Rowery i hulajnogi elektryczne ze względu na baterię oddaje się jako elektronikę.',
    },
  },
  {
    id: 'large-plastic',
    category: 'bulky',
    to: ['site'],
    names: {
      en: ['Large plastic items', 'garden chair', 'plastic chair', 'bucket', 'basin', 'laundry basket', 'plastic box', 'garden hose'],
      lt: ['Dideli plastikiniai daiktai', 'sodo kėdė', 'plastikinė kėdė', 'kibiras', 'dubuo', 'skalbinių krepšys', 'plastikinė dėžė', 'laistymo žarna'],
      ru: ['Крупные пластиковые предметы', 'садовый стул', 'пластиковый стул', 'ведро', 'таз', 'корзина для белья', 'пластиковый ящик', 'садовый шланг'],
      pl: ['Duże przedmioty z plastiku', 'krzesło ogrodowe', 'plastikowe krzesło', 'wiadro', 'miska', 'kosz na pranie', 'plastikowa skrzynka', 'wąż ogrodowy'],
    },
    tip: {
      en: "They aren't packaging, so they don't go in the packaging bin.",
      lt: 'Tai ne pakuotės, todėl į pakuočių konteinerį jų mesti negalima.',
      ru: 'Это не упаковка, поэтому в контейнер для упаковки их не кладут.',
      pl: 'To nie opakowania, więc nie wrzuca się ich do pojemnika na opakowania.',
    },
  },

  // --- Textiles ---------------------------------------------------------------------------------
  {
    id: 'clothes',
    category: 'textile',
    to: ['textile'],
    names: {
      en: ['Clothes', 'clothing', 'shirt', 'jeans', 'jacket', 'sweater', 'old clothes', 'underwear', 'socks'],
      lt: ['Drabužiai', 'rūbai', 'marškiniai', 'džinsai', 'striukė', 'megztinis', 'seni drabužiai', 'apatiniai', 'kojinės'],
      ru: ['Одежда', 'рубашка', 'джинсы', 'куртка', 'свитер', 'старая одежда', 'бельё', 'носки'],
      pl: ['Ubrania', 'odzież', 'koszula', 'dżinsy', 'kurtka', 'sweter', 'stare ubrania', 'bielizna', 'skarpetki'],
    },
    tip: {
      en: `${textileTip.en} Wearable clothes can also go to charity containers and second-hand shops. Oily or chemical-soaked textiles: bulky waste site.`,
      lt: `${textileTip.lt} Dėvėtinus drabužius galima atiduoti ir į labdaros konteinerius ar dėvėtų drabužių parduotuves. Tepaluota ar chemikalais užteršta tekstilė – į didelių gabaritų atliekų aikštelę.`,
      ru: `${textileTip.ru} Годную одежду можно отдать и в благотворительные контейнеры или секонд-хенды. Текстиль в масле или химикатах — на площадку крупногабаритных отходов.`,
      pl: `${textileTip.pl} Ubrania nadające się do noszenia można też oddać do kontenerów charytatywnych lub second-handów. Tekstylia zabrudzone olejem lub chemikaliami – do punktu odpadów wielkogabarytowych.`,
    },
  },
  {
    id: 'shoes',
    category: 'textile',
    to: ['textile'],
    names: {
      en: ['Shoes', 'boots', 'trainers', 'sneakers', 'slippers'],
      lt: ['Batai', 'avalynė', 'auliniai batai', 'sportbačiai', 'šlepetės'],
      ru: ['Обувь', 'ботинки', 'сапоги', 'кроссовки', 'тапочки'],
      pl: ['Buty', 'obuwie', 'kozaki', 'adidasy', 'kapcie'],
    },
    tip: textileTip,
  },
  {
    id: 'bedding',
    category: 'textile',
    to: ['textile'],
    names: {
      en: ['Bedding, towels and curtains', 'bed sheets', 'duvet cover', 'towel', 'curtains', 'tablecloth', 'blanket'],
      lt: ['Patalynė, rankšluosčiai ir užuolaidos', 'paklodė', 'antklodės užvalkalas', 'rankšluostis', 'užuolaidos', 'staltiesė', 'pledas'],
      ru: ['Постельное бельё, полотенца и шторы', 'простыня', 'пододеяльник', 'полотенце', 'шторы', 'скатерть', 'плед'],
      pl: ['Pościel, ręczniki i zasłony', 'prześcieradło', 'poszwa', 'ręcznik', 'zasłony', 'obrus', 'koc'],
    },
    tip: textileTip,
  },
  {
    id: 'bags-belts',
    category: 'textile',
    to: ['textile'],
    names: {
      en: ['Bags, belts and accessories', 'handbag', 'backpack', 'belt', 'hat', 'scarf', 'gloves'],
      lt: ['Rankinės, diržai ir aksesuarai', 'rankinė', 'kuprinė', 'diržas', 'kepurė', 'šalikas', 'pirštinės'],
      ru: ['Сумки, ремни и аксессуары', 'сумка', 'рюкзак', 'ремень', 'шапка', 'шарф', 'перчатки'],
      pl: ['Torebki, paski i dodatki', 'torebka', 'plecak', 'pasek', 'czapka', 'szalik', 'rękawiczki'],
    },
    tip: textileTip,
  },
  {
    id: 'soft-toys',
    category: 'textile',
    to: ['textile'],
    names: {
      en: ['Soft toys', 'teddy bear', 'plush toy', 'stuffed animal'],
      lt: ['Minkšti žaislai', 'pliušinis žaislas', 'meškiukas', 'minkštas žaislas'],
      ru: ['Мягкие игрушки', 'плюшевая игрушка', 'мишка', 'мягкая игрушка'],
      pl: ['Pluszaki', 'maskotka', 'miś', 'pluszowa zabawka'],
    },
    tip: {
      en: 'Toys with batteries or electronics go to electronics collection.',
      lt: 'Žaislai su baterijomis ar elektronika atiduodami kaip elektronika.',
      ru: 'Игрушки с батарейками или электроникой сдают как электронику.',
      pl: 'Zabawki z bateriami lub elektroniką oddaje się jako elektronikę.',
    },
  },
  {
    id: 'rags',
    category: 'textile',
    to: ['textile', 'site'],
    names: {
      en: ['Worn-out textiles and rags', 'rags', 'torn clothes', 'fabric scraps', 'yarn'],
      lt: ['Susidėvėjusi tekstilė ir skudurai', 'skudurai', 'suplyšę drabužiai', 'audinio skiautės', 'siūlai'],
      ru: ['Изношенный текстиль и тряпки', 'тряпки', 'рваная одежда', 'обрезки ткани', 'пряжа'],
      pl: ['Zniszczone tekstylia i szmaty', 'szmaty', 'podarte ubrania', 'skrawki materiału', 'włóczka'],
    },
    tip: {
      en: 'Pack them in a separate bag from wearable clothes. Dirty or wet items only in a waterproof bag.',
      lt: 'Sudėkite į atskirą maišą nuo dėvėtinų drabužių. Purvinus ar šlapius – tik į vandeniui nelaidų maišą.',
      ru: 'Упакуйте в отдельный пакет от годной одежды. Грязные или мокрые вещи — только в непромокаемом пакете.',
      pl: 'Spakuj je do innego worka niż ubrania do noszenia. Brudne lub mokre rzeczy tylko w nieprzemakalnym worku.',
    },
  },

  // --- Other household waste --------------------------------------------------------------------
  {
    id: 'diapers',
    category: 'other',
    to: ['household'],
    names: {
      en: ['Diapers and nappies', 'diaper', 'nappy'],
      lt: ['Sauskelnės', 'sauskelnės vaikams', 'vystyklai'],
      ru: ['Подгузники', 'памперсы', 'подгузник'],
      pl: ['Pieluchy', 'pielucha', 'pampersy'],
    },
  },
  {
    id: 'wet-wipes',
    category: 'other',
    to: ['household'],
    names: {
      en: ['Wet wipes and cotton pads', 'wet wipe', 'baby wipes', 'make-up wipes', 'cotton pads', 'cotton buds'],
      lt: ['Drėgnosios servetėlės ir vatos diskeliai', 'drėgna servetėlė', 'drėgnosios servetėlės vaikams', 'makiažo valymo servetėlės', 'vatos diskeliai', 'ausų krapštukai'],
      ru: ['Влажные салфетки и ватные диски', 'влажная салфетка', 'детские салфетки', 'салфетки для снятия макияжа', 'ватные диски', 'ватные палочки'],
      pl: ['Chusteczki nawilżane i płatki kosmetyczne', 'chusteczka nawilżana', 'chusteczki dla dzieci', 'chusteczki do demakijażu', 'płatki kosmetyczne', 'patyczki higieniczne'],
    },
    tip: {
      en: 'Never flush them down the toilet.',
      lt: 'Niekada neleiskite jų į unitazą.',
      ru: 'Никогда не смывайте их в унитаз.',
      pl: 'Nigdy nie spłukuj ich w toalecie.',
    },
  },
  {
    id: 'tissues',
    category: 'other',
    to: ['household'],
    names: {
      en: ['Tissues and toilet paper', 'tissue', 'handkerchief', 'toilet paper', 'used tissues'],
      lt: ['Nosinaitės ir tualetinis popierius', 'nosinė', 'vienkartinė nosinaitė', 'tualetinis popierius'],
      ru: ['Бумажные платочки и туалетная бумага', 'носовой платок', 'платочки', 'туалетная бумага'],
      pl: ['Chusteczki higieniczne i papier toaletowy', 'chusteczka', 'chusteczki', 'papier toaletowy'],
    },
  },
  {
    id: 'hygiene',
    category: 'other',
    to: ['household'],
    names: {
      en: ['Sanitary pads and tampons', 'pads', 'tampons', 'panty liners', 'incontinence pads'],
      lt: ['Higieniniai paketai ir tamponai', 'higieniniai paketai', 'tamponai', 'įklotai'],
      ru: ['Прокладки и тампоны', 'прокладки', 'тампоны', 'ежедневки'],
      pl: ['Podpaski i tampony', 'podpaski', 'tampony', 'wkładki'],
    },
  },
  {
    id: 'toothbrush',
    category: 'other',
    to: ['household'],
    names: {
      en: ['Toothbrushes and dental floss', 'toothbrush', 'dental floss', 'toothpaste tube'],
      lt: ['Dantų šepetėliai ir siūlas', 'dantų šepetėlis', 'šepetėlis', 'dantų siūlas', 'dantų pastos tūbelė'],
      ru: ['Зубные щётки и нить', 'зубная щётка', 'щётка', 'зубная нить', 'тюбик от зубной пасты'],
      pl: ['Szczoteczki do zębów i nić', 'szczoteczka do zębów', 'szczoteczka', 'nić dentystyczna', 'tubka po paście'],
    },
    tip: {
      en: "They aren't packaging. An electric toothbrush goes to electronics collection.",
      lt: 'Tai ne pakuotės. Elektrinis dantų šepetėlis atiduodamas kaip elektronika.',
      ru: 'Это не упаковка. Электрическую зубную щётку сдают как электронику.',
      pl: 'To nie opakowania. Elektryczną szczoteczkę oddaje się jako elektronikę.',
    },
  },
  {
    id: 'razors',
    category: 'other',
    to: ['household'],
    names: {
      en: ['Razors', 'razor', 'razor blades', 'disposable razor'],
      lt: ['Skustuvai', 'skustuvas', 'skutimosi peiliukai', 'vienkartinis skustuvas'],
      ru: ['Бритвы', 'бритва', 'лезвия', 'одноразовый станок'],
      pl: ['Maszynki do golenia', 'maszynka', 'żyletki', 'jednorazowa maszynka'],
    },
  },
  {
    id: 'pet-litter',
    category: 'other',
    to: ['household'],
    names: {
      en: ['Pet litter and droppings', 'cat litter', 'dog poop', 'poop bag', 'cage bedding'],
      lt: ['Gyvūnų kraikas ir išmatos', 'kačių kraikas', 'šunų išmatos', 'išmatų maišelis', 'narvelio pakratai'],
      ru: ['Наполнитель и экскременты животных', 'кошачий наполнитель', 'собачьи экскременты', 'пакет для экскрементов', 'подстилка из клетки'],
      pl: ['Żwirek i odchody zwierząt', 'żwirek dla kota', 'psie kupy', 'woreczek na odchody', 'ściółka z klatki'],
    },
    tip: {
      en: 'Not in food waste or a home compost.',
      lt: 'Ne į maisto atliekas ir ne į namų kompostą.',
      ru: 'Не в пищевые отходы и не в домашний компост.',
      pl: 'Nie do odpadów spożywczych ani do przydomowego kompostownika.',
    },
  },
  {
    id: 'cigarettes',
    category: 'other',
    to: ['household'],
    names: {
      en: ['Cigarette butts', 'cigarettes', 'cigarette ends', 'tobacco'],
      lt: ['Nuorūkos', 'cigaretės', 'cigarečių nuorūkos', 'tabakas'],
      ru: ['Окурки', 'сигареты', 'табак'],
      pl: ['Niedopałki', 'papierosy', 'pety', 'tytoń'],
    },
    tip: {
      en: 'Make sure they are completely out.',
      lt: 'Įsitikinkite, kad jos visiškai užgesusios.',
      ru: 'Убедитесь, что они полностью потушены.',
      pl: 'Upewnij się, że są całkiem zgaszone.',
    },
  },
  {
    id: 'ash',
    category: 'other',
    to: ['household'],
    names: {
      en: ['Ash', 'ashes', 'stove ash', 'fireplace ash', 'barbecue ash'],
      lt: ['Pelenai', 'krosnies pelenai', 'židinio pelenai', 'kepsninės pelenai'],
      ru: ['Зола', 'пепел', 'зола из печи', 'зола из камина', 'зола от мангала'],
      pl: ['Popiół', 'popiół z pieca', 'popiół z kominka', 'popiół z grilla'],
    },
    tip: {
      en: 'Only when completely cold: hot ash can set the bin on fire.',
      lt: 'Tik visiškai atvėsusius: karšti pelenai gali uždegti konteinerį.',
      ru: 'Только полностью остывшую: горячая зола может поджечь контейнер.',
      pl: 'Tylko całkiem wystygły: gorący popiół może podpalić pojemnik.',
    },
  },
  {
    id: 'vacuum-dust',
    category: 'other',
    to: ['household'],
    names: {
      en: ['Vacuum cleaner bags and dust', 'vacuum bag', 'dust', 'sweepings', 'hair'],
      lt: ['Dulkių siurblio maišeliai ir dulkės', 'dulkių maišelis', 'dulkės', 'sąšlavos', 'plaukai'],
      ru: ['Мешки от пылесоса и пыль', 'мешок для пылесоса', 'пыль', 'сметённый мусор', 'волосы'],
      pl: ['Worki z odkurzacza i kurz', 'worek do odkurzacza', 'kurz', 'śmieci z zamiatania', 'włosy'],
    },
  },
  {
    id: 'sponges',
    category: 'other',
    to: ['household'],
    names: {
      en: ['Sponges and cleaning cloths', 'sponge', 'kitchen sponge', 'dishcloth', 'scourer'],
      lt: ['Kempinės ir valymo šluostės', 'kempinė', 'indų kempinė', 'šluostė', 'šveistukas'],
      ru: ['Губки и тряпки для уборки', 'губка', 'губка для посуды', 'тряпка', 'мочалка'],
      pl: ['Gąbki i ściereczki', 'gąbka', 'gąbka do naczyń', 'ściereczka', 'zmywak'],
    },
  },
  {
    id: 'ceramics',
    category: 'other',
    to: ['household'],
    names: {
      en: ['Ceramics and porcelain', 'broken plate', 'plate', 'mug', 'cup', 'porcelain', 'vase'],
      lt: ['Keramika ir porcelianas', 'sudužusi lėkštė', 'lėkštė', 'puodelis', 'porcelianas', 'vaza'],
      ru: ['Керамика и фарфор', 'разбитая тарелка', 'тарелка', 'кружка', 'чашка', 'фарфор', 'ваза'],
      pl: ['Ceramika i porcelana', 'stłuczony talerz', 'talerz', 'kubek', 'filiżanka', 'porcelana', 'wazon'],
    },
    tip: {
      en: 'Not in the glass container. Wrap sharp pieces. Lots of tiles or a toilet bowl: bulky waste site.',
      lt: 'Ne į stiklo konteinerį. Aštrias šukes suvyniokite. Daug plytelių ar unitazą vežkite į didelių gabaritų atliekų aikštelę.',
      ru: 'Не в контейнер для стекла. Острые осколки заверните. Много плитки или унитаз — на площадку крупногабаритных отходов.',
      pl: 'Nie do pojemnika na szkło. Ostre kawałki zawiń. Dużo płytek lub muszlę klozetową – do punktu odpadów wielkogabarytowych.',
    },
  },
  {
    id: 'toys',
    category: 'other',
    to: ['household'],
    names: {
      en: ['Plastic toys', 'toy', 'toys', 'lego', 'doll', 'toy car'],
      lt: ['Plastikiniai žaislai', 'žaislas', 'žaislai', 'lego', 'lėlė', 'žaislinė mašinėlė'],
      ru: ['Пластиковые игрушки', 'игрушка', 'игрушки', 'лего', 'кукла', 'машинка'],
      pl: ['Plastikowe zabawki', 'zabawka', 'zabawki', 'lego', 'lalka', 'samochodzik'],
    },
    tip: {
      en: "Toys aren't packaging. Give usable ones away; toys with batteries go to electronics collection, big ones to a bulky waste site.",
      lt: 'Žaislai nėra pakuotės. Tinkamus atiduokite kitiems; žaislus su baterijomis – kaip elektroniką, didelius – į didelių gabaritų atliekų aikštelę.',
      ru: 'Игрушки — это не упаковка. Годные отдайте; игрушки с батарейками сдайте как электронику, крупные — на площадку крупногабаритных отходов.',
      pl: 'Zabawki to nie opakowania. Te w dobrym stanie oddaj; zabawki na baterie oddaj jako elektronikę, duże – do punktu odpadów wielkogabarytowych.',
    },
  },
];
