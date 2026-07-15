const LiveKit = window.LivekitClient || window.LiveKit;
if (!LiveKit) {
  const s = document.getElementById("status");
  if (s) s.textContent = "Error: LiveKit library failed to load — check internet/console (F12).";
  throw new Error("LiveKit not loaded");
}
const { Room, RoomEvent, Track } = LiveKit;

// ── DOM refs ───────────────────────────────────────────────────────────────
const welcomeEl        = document.getElementById("welcome");
const sessionEl        = document.getElementById("session");
const statusEl         = document.getElementById("status");
const langLabelEl      = document.getElementById("lang-label");
const modeLabelEl      = document.getElementById("mode-label");
const messagesEl       = document.getElementById("messages");
const btnStart         = document.getElementById("btn-start");
const btnEnd           = document.getElementById("btn-end");
const chatForm         = document.getElementById("chat-form");
const chatInput        = document.getElementById("chat-input");
const agentAudioEl     = document.getElementById("agent-audio");

// Config controls
const selLearnLang     = document.getElementById("sel-learn-lang");
const selNativeLang    = document.getElementById("sel-native-lang");
const selModel         = document.getElementById("sel-model");

// Section / curriculum selector (visible during active session)
const selSection       = document.getElementById("sel-section");
const sectionBar       = document.getElementById("section-bar");

// Feedback
const feedbackOverlay  = document.getElementById("feedback-overlay");
const btnThumbsUp      = document.getElementById("btn-thumbs-up");
const btnThumbsDown    = document.getElementById("btn-thumbs-down");
const feedbackComment  = document.getElementById("feedback-comment");
const btnSubmitFeedback= document.getElementById("btn-submit-feedback");
const btnSkipFeedback  = document.getElementById("btn-skip-feedback");

// ── State ──────────────────────────────────────────────────────────────────
let selectedRating   = null;
let currentRoomName  = null;
let currentSessionId = null;
let _pendingSection  = null;   // section chosen on welcome screen, triggered when Teddy joins

// ── Vocabulary data ────────────────────────────────────────────────────────
// article: 'der'=masculine, 'die'=feminine, 'das'=neuter, ''=no article (verbs/adj)
const VOCAB_SETS = {
  colors:     { title: 'Farben', titleAr: 'الألوان',   type: 'color', items: [
    { article:'das', de:'Rot',       en:'Red',        ar:'أحمر',   arGender:'m', color:'#ef4444' },
    { article:'das', de:'Blau',      en:'Blue',       ar:'أزرق',   arGender:'m', color:'#3b82f6' },
    { article:'das', de:'Grün',      en:'Green',      ar:'أخضر',   arGender:'m', color:'#22c55e' },
    { article:'das', de:'Gelb',      en:'Yellow',     ar:'أصفر',   arGender:'m', color:'#eab308' },
    { article:'das', de:'Orange',    en:'Orange',     ar:'برتقالي', arGender:'m', color:'#f97316' },
    { article:'das', de:'Lila',      en:'Purple',     ar:'بنفسجي', arGender:'m', color:'#a855f7' },
    { article:'das', de:'Rosa',      en:'Pink',       ar:'وردي',   arGender:'m', color:'#ec4899' },
    { article:'das', de:'Schwarz',   en:'Black',      ar:'أسود',   arGender:'m', color:'#374151' },
    { article:'das', de:'Weiß',      en:'White',      ar:'أبيض',   arGender:'m', color:'#d1d5db' },
    { article:'das', de:'Braun',     en:'Brown',      ar:'بني',    arGender:'m', color:'#92400e' },
  ]},
  breakfast:  { title: 'Frühstück', titleAr: 'الفطور',  items: [
    { emoji:'🥚', article:'das', de:'Ei',          en:'Egg',            ar:'بيضة',        arGender:'f' },
    { emoji:'🍞', article:'das', de:'Brot',        en:'Bread',          ar:'خبز',         arGender:'m' },
    { emoji:'🥛', article:'die', de:'Milch',       en:'Milk',           ar:'حليب',        arGender:'m' },
    { emoji:'🧇', article:'die', de:'Waffeln',     en:'Waffles',        ar:'وافل',        arGender:'m' },
    { emoji:'🥣', article:'das', de:'Müsli',       en:'Cereal',         ar:'موزلي',       arGender:'m' },
    { emoji:'🍳', article:'das', de:'Rührei',      en:'Scrambled eggs', ar:'بيض مخفوق',   arGender:'m' },
    { emoji:'🥐', article:'das', de:'Croissant',   en:'Croissant',      ar:'كرواسون',     arGender:'m' },
    { emoji:'🍯', article:'der', de:'Honig',       en:'Honey',          ar:'عسل',         arGender:'m' },
    { emoji:'🧈', article:'die', de:'Butter',      en:'Butter',         ar:'زبدة',        arGender:'f' },
    { emoji:'🍓', article:'die', de:'Beeren',      en:'Berries',        ar:'توت',         arGender:'m' },
  ]},
  fruits:     { title: 'Obst', titleAr: 'الفواكه',       items: [
    { emoji:'🍎', article:'der', de:'Apfel',       en:'Apple',      ar:'تفاحة',   arGender:'f' },
    { emoji:'🍌', article:'die', de:'Banane',      en:'Banana',     ar:'موزة',    arGender:'f' },
    { emoji:'🍓', article:'die', de:'Erdbeere',    en:'Strawberry', ar:'فراولة',  arGender:'f' },
    { emoji:'🍊', article:'die', de:'Orange',      en:'Orange',     ar:'برتقالة', arGender:'f' },
    { emoji:'🍇', article:'die', de:'Trauben',     en:'Grapes',     ar:'عنب',     arGender:'m' },
    { emoji:'🍑', article:'der', de:'Pfirsich',    en:'Peach',      ar:'خوخ',     arGender:'m' },
    { emoji:'🍒', article:'die', de:'Kirsche',     en:'Cherry',     ar:'كرز',     arGender:'m' },
    { emoji:'🍋', article:'die', de:'Zitrone',     en:'Lemon',      ar:'ليمون',   arGender:'m' },
    { emoji:'🥭', article:'die', de:'Mango',       en:'Mango',      ar:'مانجو',   arGender:'m' },
    { emoji:'🍍', article:'die', de:'Ananas',      en:'Pineapple',  ar:'أناناس',  arGender:'m' },
  ]},
  animals:    { title: 'Tiere', titleAr: 'الحيوانات',    items: [
    { emoji:'🐶', article:'der', de:'Hund',        en:'Dog',      ar:'كلب',    arGender:'m' },
    { emoji:'🐱', article:'die', de:'Katze',       en:'Cat',      ar:'قطة',    arGender:'f' },
    { emoji:'🦁', article:'der', de:'Löwe',        en:'Lion',     ar:'أسد',    arGender:'m' },
    { emoji:'🐘', article:'der', de:'Elefant',     en:'Elephant', ar:'فيل',    arGender:'m' },
    { emoji:'🦒', article:'die', de:'Giraffe',     en:'Giraffe',  ar:'زرافة',  arGender:'f' },
    { emoji:'🐧', article:'der', de:'Pinguin',     en:'Penguin',  ar:'بطريق',  arGender:'m' },
    { emoji:'🦊', article:'der', de:'Fuchs',       en:'Fox',      ar:'ثعلب',   arGender:'m' },
    { emoji:'🐻', article:'der', de:'Bär',         en:'Bear',     ar:'دب',     arGender:'m' },
    { emoji:'🐬', article:'der', de:'Delphin',     en:'Dolphin',  ar:'دولفين', arGender:'m' },
    { emoji:'🐒', article:'der', de:'Affe',        en:'Monkey',   ar:'قرد',    arGender:'m' },
  ]},
  sports:     { title: 'Sport & Spiele', titleAr: 'الرياضة والألعاب', items: [
    { emoji:'⚽', article:'der', de:'Fußball',     en:'Football',    ar:'كرة القدم',       arGender:'f' },
    { emoji:'🏀', article:'der', de:'Basketball',  en:'Basketball',  ar:'كرة السلة',       arGender:'f' },
    { emoji:'🎾', article:'das', de:'Tennis',      en:'Tennis',      ar:'التنس',           arGender:'m' },
    { emoji:'🏊', article:'das', de:'Schwimmen',   en:'Swimming',    ar:'السباحة',         arGender:'f' },
    { emoji:'🚴', article:'das', de:'Radfahren',   en:'Cycling',     ar:'ركوب الدراجة',    arGender:'m' },
    { emoji:'🎮', article:'die', de:'Videospiele', en:'Video games', ar:'ألعاب الفيديو',   arGender:'f' },
    { emoji:'🏃', article:'das', de:'Laufen',      en:'Running',     ar:'الجري',           arGender:'m' },
    { emoji:'🎨', article:'das', de:'Malen',       en:'Painting',    ar:'الرسم',           arGender:'m' },
    { emoji:'🎵', article:'die', de:'Musik',       en:'Music',       ar:'الموسيقى',        arGender:'f' },
    { emoji:'🧩', article:'das', de:'Puzzle',      en:'Puzzle',      ar:'أحجية',           arGender:'f' },
  ]},
  family:     { title: 'Familie', titleAr: 'العائلة',    items: [
    { emoji:'👨', article:'der', de:'Vater',       en:'Father',   ar:'أب',    arGender:'m' },
    { emoji:'👩', article:'die', de:'Mutter',      en:'Mother',   ar:'أم',    arGender:'f' },
    { emoji:'👦', article:'der', de:'Bruder',      en:'Brother',  ar:'أخ',    arGender:'m' },
    { emoji:'👧', article:'die', de:'Schwester',   en:'Sister',   ar:'أخت',   arGender:'f' },
    { emoji:'👴', article:'der', de:'Opa',         en:'Grandpa',  ar:'جد',    arGender:'m' },
    { emoji:'👵', article:'die', de:'Oma',         en:'Grandma',  ar:'جدة',   arGender:'f' },
    { emoji:'👶', article:'das', de:'Baby',        en:'Baby',     ar:'طفل',   arGender:'m' },
    { emoji:'🐕', article:'der', de:'Hund',        en:'Dog',      ar:'كلب',   arGender:'m' },
  ]},
  school:     { title: 'Schule', titleAr: 'المدرسة',     items: [
    { emoji:'📚', article:'die', de:'Bücher',      en:'Books',     ar:'كتب',        arGender:'m' },
    { emoji:'✏️', article:'der', de:'Bleistift',   en:'Pencil',    ar:'قلم رصاص',   arGender:'m' },
    { emoji:'📐', article:'das', de:'Lineal',      en:'Ruler',     ar:'مسطرة',      arGender:'f' },
    { emoji:'🎒', article:'der', de:'Rucksack',    en:'Backpack',  ar:'حقيبة ظهر',  arGender:'f' },
    { emoji:'🧮', article:'die', de:'Mathe',       en:'Math',      ar:'الرياضيات',  arGender:'f' },
    { emoji:'🎨', article:'die', de:'Kunst',       en:'Art',       ar:'الفن',       arGender:'m' },
    { emoji:'🌍', article:'die', de:'Geografie',   en:'Geography', ar:'الجغرافيا',  arGender:'f' },
    { emoji:'🔬', article:'die', de:'Biologie',    en:'Biology',   ar:'الأحياء',    arGender:'m' },
    { emoji:'📖', article:'das', de:'Lesen',       en:'Reading',   ar:'القراءة',    arGender:'f' },
  ]},
  seasons:    { title: 'Jahreszeiten', titleAr: 'الفصول', items: [
    { emoji:'🌸', article:'der', de:'Frühling',    en:'Spring', ar:'الربيع',     arGender:'m' },
    { emoji:'☀️', article:'der', de:'Sommer',      en:'Summer', ar:'الصيف',      arGender:'m' },
    { emoji:'🍂', article:'der', de:'Herbst',      en:'Autumn', ar:'الخريف',     arGender:'m' },
    { emoji:'❄️', article:'der', de:'Winter',      en:'Winter', ar:'الشتاء',     arGender:'m' },
    { emoji:'🌧️', article:'der', de:'Regen',       en:'Rain',   ar:'المطر',      arGender:'m' },
    { emoji:'⛄', article:'der', de:'Schnee',      en:'Snow',   ar:'الثلج',      arGender:'m' },
    { emoji:'🌈', article:'der', de:'Regenbogen',  en:'Rainbow',ar:'قوس قزح',    arGender:'m' },
    { emoji:'☀️', article:'die', de:'Sonne',       en:'Sun',    ar:'الشمس',      arGender:'f' },
  ]},
  food:       { title: 'Lieblingsessen', titleAr: 'الطعام المفضل', items: [
    { emoji:'🍕', article:'die', de:'Pizza',       en:'Pizza',    ar:'بيتزا',      arGender:'f' },
    { emoji:'🍝', article:'die', de:'Nudeln',      en:'Pasta',    ar:'معكرونة',    arGender:'f' },
    { emoji:'🍔', article:'der', de:'Burger',      en:'Burger',   ar:'برغر',       arGender:'m' },
    { emoji:'🍚', article:'der', de:'Reis',        en:'Rice',     ar:'أرز',        arGender:'m' },
    { emoji:'🥗', article:'der', de:'Salat',       en:'Salad',    ar:'سلطة',       arGender:'f' },
    { emoji:'🍜', article:'die', de:'Suppe',       en:'Soup',     ar:'شوربة',      arGender:'f' },
    { emoji:'🍗', article:'das', de:'Hähnchen',    en:'Chicken',  ar:'دجاج',       arGender:'m' },
    { emoji:'🥙', article:'das', de:'Sandwich',    en:'Sandwich', ar:'ساندويتش',   arGender:'m' },
    { emoji:'🧀', article:'der', de:'Käse',        en:'Cheese',   ar:'جبن',        arGender:'m' },
    { emoji:'🍣', article:'das', de:'Sushi',       en:'Sushi',    ar:'سوشي',       arGender:'m' },
  ]},
  vegetables: { title: 'Gemüse', titleAr: 'الخضروات',    items: [
    { emoji:'🥕', article:'die', de:'Karotte',     en:'Carrot',   ar:'جزرة',   arGender:'f' },
    { emoji:'🥦', article:'der', de:'Brokkoli',    en:'Broccoli', ar:'بروكلي', arGender:'m' },
    { emoji:'🍅', article:'die', de:'Tomate',      en:'Tomato',   ar:'طماطم',  arGender:'f' },
    { emoji:'🥔', article:'die', de:'Kartoffel',   en:'Potato',   ar:'بطاطا',  arGender:'f' },
    { emoji:'🌽', article:'der', de:'Mais',        en:'Corn',     ar:'ذرة',    arGender:'f' },
    { emoji:'🥒', article:'die', de:'Gurke',       en:'Cucumber', ar:'خيار',   arGender:'m' },
    { emoji:'🫑', article:'die', de:'Paprika',     en:'Pepper',   ar:'فلفل',   arGender:'m' },
    { emoji:'🧅', article:'die', de:'Zwiebel',     en:'Onion',    ar:'بصلة',   arGender:'f' },
  ]},
  drinks:     { title: 'Getränke', titleAr: 'المشروبات',  items: [
    { emoji:'🥛', article:'die', de:'Milch',       en:'Milk',  ar:'حليب',        arGender:'m' },
    { emoji:'🧃', article:'der', de:'Saft',        en:'Juice', ar:'عصير',        arGender:'m' },
    { emoji:'💧', article:'das', de:'Wasser',      en:'Water', ar:'ماء',         arGender:'m' },
    { emoji:'🍵', article:'der', de:'Tee',         en:'Tea',   ar:'شاي',         arGender:'m' },
    { emoji:'🥤', article:'die', de:'Limo',        en:'Soda',  ar:'مشروب غازي',  arGender:'m' },
    { emoji:'🧋', article:'der', de:'Kakao',       en:'Cocoa', ar:'كاكاو',       arGender:'m' },
  ]},
  icecream:   { title: 'Eis', titleAr: 'الآيس كريم',      items: [
    { emoji:'🍦', article:'die', de:'Vanille',     en:'Vanilla',    ar:'فانيليا',    arGender:'f' },
    { emoji:'🍫', article:'die', de:'Schokolade',  en:'Chocolate',  ar:'شوكولاتة',   arGender:'f' },
    { emoji:'🍓', article:'die', de:'Erdbeere',    en:'Strawberry', ar:'فراولة',     arGender:'f' },
    { emoji:'🍋', article:'die', de:'Zitrone',     en:'Lemon',      ar:'ليمون',      arGender:'m' },
    { emoji:'🍑', article:'der', de:'Pfirsich',    en:'Peach',      ar:'خوخ',        arGender:'m' },
    { emoji:'🫐', article:'die', de:'Blaubeere',   en:'Blueberry',  ar:'توت أزرق',   arGender:'m' },
  ]},
  hobbies:    { title: 'Hobbys', titleAr: 'الهوايات',     items: [
    { emoji:'📚', article:'das', de:'Lesen',       en:'Reading',    ar:'القراءة',              arGender:'f' },
    { emoji:'🎨', article:'das', de:'Zeichnen',    en:'Drawing',    ar:'الرسم',                arGender:'m' },
    { emoji:'🎵', article:'das', de:'Singen',      en:'Singing',    ar:'الغناء',               arGender:'m' },
    { emoji:'💃', article:'das', de:'Tanzen',      en:'Dancing',    ar:'الرقص',                arGender:'m' },
    { emoji:'🎮', article:'das', de:'Zocken',      en:'Gaming',     ar:'الألعاب الإلكترونية',  arGender:'f' },
    { emoji:'🌱', article:'das', de:'Gärtnern',    en:'Gardening',  ar:'البستنة',              arGender:'f' },
    { emoji:'🍳', article:'das', de:'Kochen',      en:'Cooking',    ar:'الطبخ',                arGender:'m' },
    { emoji:'🧵', article:'das', de:'Basteln',     en:'Crafts',     ar:'الأشغال اليدوية',      arGender:'f' },
  ]},
  superpower: { title: 'Superkräfte', titleAr: 'القوى الخارقة', items: [
    { emoji:'🦸', article:'das', de:'Fliegen',      en:'Flying',        ar:'الطيران',        arGender:'m' },
    { emoji:'👁️', article:'die', de:'Unsichtbarkeit',en:'Invisibility', ar:'الاختفاء',       arGender:'m' },
    { emoji:'🔮', article:'die', de:'Magie',        en:'Magic',         ar:'السحر',          arGender:'m' },
    { emoji:'💪', article:'die', de:'Super-Stärke', en:'Super Strength',ar:'القوة الخارقة',  arGender:'f' },
    { emoji:'⚡', article:'der', de:'Blitz',        en:'Lightning',     ar:'البرق',          arGender:'m' },
    { emoji:'🌊', article:'das', de:'Wasser',       en:'Water Control', ar:'التحكم بالماء',  arGender:'m' },
    { emoji:'🔥', article:'das', de:'Feuer',        en:'Fire',          ar:'النار',          arGender:'f' },
    { emoji:'🧠', article:'das', de:'Gedankenlesen',en:'Mind Reading',  ar:'قراءة الأفكار',  arGender:'f' },
  ]},
  jobs:       { title: 'Berufe', titleAr: 'المهن',       items: [
    { emoji:'👨‍⚕️', article:'der', de:'Arzt',          en:'Doctor',      ar:'طبيب',            arGender:'m' },
    { emoji:'👩‍🏫', article:'die', de:'Lehrerin',      en:'Teacher',     ar:'معلمة',           arGender:'f' },
    { emoji:'👨‍🚒', article:'der', de:'Feuerwehrmann', en:'Firefighter', ar:'رجل إطفاء',       arGender:'m' },
    { emoji:'👩‍🍳', article:'die', de:'Köchin',        en:'Chef',        ar:'طاهية',           arGender:'f' },
    { emoji:'👨‍🚀', article:'der', de:'Astronaut',     en:'Astronaut',   ar:'رائد فضاء',       arGender:'m' },
    { emoji:'👩‍🎨', article:'die', de:'Künstlerin',    en:'Artist',      ar:'فنانة',           arGender:'f' },
    { emoji:'👨‍💻', article:'der', de:'Programmierer', en:'Programmer',  ar:'مبرمج',           arGender:'m' },
    { emoji:'⚽',   article:'der', de:'Fußballer',     en:'Footballer',  ar:'لاعب كرة قدم',    arGender:'m' },
  ]},
  toys:       { title: 'Spielzeug', titleAr: 'الألعاب',  items: [
    { emoji:'🪆', article:'die', de:'Puppe',        en:'Doll',       ar:'دمية',      arGender:'f' },
    { emoji:'🚗', article:'das', de:'Auto',         en:'Car',        ar:'سيارة',     arGender:'f' },
    { emoji:'🧸', article:'der', de:'Teddybär',     en:'Teddy Bear', ar:'دبدوب',     arGender:'m' },
    { emoji:'🎪', article:'das', de:'Zelt',         en:'Tent',       ar:'خيمة',      arGender:'f' },
    { emoji:'🪀', article:'das', de:'Jojo',         en:'Yo-yo',      ar:'يويو',      arGender:'m' },
    { emoji:'🎯', article:'die', de:'Zielscheibe',  en:'Target',     ar:'هدف',       arGender:'m' },
    { emoji:'🧲', article:'der', de:'Magnet',       en:'Magnet',     ar:'مغناطيس',   arGender:'m' },
    { emoji:'🪁', article:'die', de:'Schleuder',    en:'Slingshot',  ar:'مقلاع',     arGender:'m' },
  ]},

  // ── Level 1: Basics ────────────────────────────────────────────────────────
  greetings:  { title: 'Hallo! (Begrüßung)', titleAr: 'مرحباً! (التحية)', type: 'phrase', items: [
    { emoji:'👋', article:'', de:'Hallo!',               en:'Hello!',              ar:'مرحباً!'          },
    { emoji:'👋', article:'', de:'Tschüss!',             en:'Goodbye!',            ar:'مع السلامة!'      },
    { emoji:'🌅', article:'', de:'Guten Morgen!',        en:'Good morning!',       ar:'صباح الخير!'      },
    { emoji:'🌙', article:'', de:'Gute Nacht!',          en:'Good night!',         ar:'تصبح على خير!'    },
    { emoji:'🤝', article:'', de:'Wie geht\'s?',         en:'How are you?',        ar:'كيف حالك؟'        },
    { emoji:'😊', article:'', de:'Mir geht\'s gut!',     en:'I\'m fine!',          ar:'أنا بخير!'        },
    { emoji:'😔', article:'', de:'Mir geht\'s nicht gut', en:'I\'m not feeling well', ar:'أنا لست بخير'  },
    { emoji:'🙋', article:'', de:'Ich heiße…',           en:'My name is…',         ar:'اسمي…'            },
    { emoji:'🎂', article:'', de:'Ich bin … Jahre alt',  en:'I am … years old',    ar:'عمري … سنوات'     },
    { emoji:'🌍', article:'', de:'Woher kommst du?',     en:'Where are you from?', ar:'من أين أنت؟'      },
    { emoji:'🏠', article:'', de:'Ich komme aus…',       en:'I come from…',        ar:'أنا من…'          },
    { emoji:'📚', article:'', de:'Ich bin Schüler(in)',  en:'I\'m a student',      ar:'أنا طالب'         },
  ]},
  numbers1:   { title: 'Zahlen 1–10', titleAr: 'الأرقام ١–١٠', type: 'number', items: [
    { emoji:'1', article:'', de:'eins',    en:'one',   ar:'واحد'  },
    { emoji:'2', article:'', de:'zwei',    en:'two',   ar:'اثنان' },
    { emoji:'3', article:'', de:'drei',    en:'three', ar:'ثلاثة' },
    { emoji:'4', article:'', de:'vier',    en:'four',  ar:'أربعة' },
    { emoji:'5', article:'', de:'fünf',    en:'five',  ar:'خمسة'  },
    { emoji:'6', article:'', de:'sechs',   en:'six',   ar:'ستة'   },
    { emoji:'7', article:'', de:'sieben',  en:'seven', ar:'سبعة'  },
    { emoji:'8', article:'', de:'acht',    en:'eight', ar:'ثمانية'},
    { emoji:'9', article:'', de:'neun',    en:'nine',  ar:'تسعة'  },
    { emoji:'🔟', article:'', de:'zehn',   en:'ten',   ar:'عشرة'  },
  ]},
  numbers2:   { title: 'Zahlen 11–20', titleAr: 'الأرقام ١١–٢٠', type: 'number', items: [
    { emoji:'11', article:'', de:'elf',          en:'eleven',   ar:'أحد عشر'  },
    { emoji:'12', article:'', de:'zwölf',        en:'twelve',   ar:'اثنا عشر' },
    { emoji:'13', article:'', de:'dreizehn',     en:'thirteen', ar:'ثلاثة عشر'},
    { emoji:'14', article:'', de:'vierzehn',     en:'fourteen', ar:'أربعة عشر'},
    { emoji:'15', article:'', de:'fünfzehn',     en:'fifteen',  ar:'خمسة عشر' },
    { emoji:'16', article:'', de:'sechzehn',     en:'sixteen',  ar:'ستة عشر'  },
    { emoji:'17', article:'', de:'siebzehn',     en:'seventeen',ar:'سبعة عشر' },
    { emoji:'18', article:'', de:'achtzehn',     en:'eighteen', ar:'ثمانية عشر'},
    { emoji:'19', article:'', de:'neunzehn',     en:'nineteen', ar:'تسعة عشر' },
    { emoji:'20', article:'', de:'zwanzig',      en:'twenty',   ar:'عشرون'    },
  ]},
  alphabet:   { title: 'Das ABC', titleAr: 'الحروف العربية', type: 'abc', items: [
    { emoji:'A', article:'', de:'wie Apfel',      en:'for Apple',     ar:'أرنب (أ)',   visualAr:'أ' },
    { emoji:'B', article:'', de:'wie Ball',       en:'for Ball',      ar:'باب (ب)',    visualAr:'ب' },
    { emoji:'C', article:'', de:'wie Computer',   en:'for Computer',  ar:'تفاحة (ت)',  visualAr:'ت' },
    { emoji:'D', article:'', de:'wie Delfin',     en:'for Dolphin',   ar:'ثعلب (ث)',   visualAr:'ث' },
    { emoji:'E', article:'', de:'wie Elefant',    en:'for Elephant',  ar:'جمل (ج)',    visualAr:'ج' },
    { emoji:'F', article:'', de:'wie Fisch',      en:'for Fish',      ar:'حصان (ح)',   visualAr:'ح' },
    { emoji:'G', article:'', de:'wie Giraffe',    en:'for Giraffe',   ar:'خروف (خ)',   visualAr:'خ' },
    { emoji:'H', article:'', de:'wie Hund',       en:'for Dog',       ar:'دب (د)',     visualAr:'د' },
    { emoji:'I', article:'', de:'wie Igel',       en:'for Hedgehog',  ar:'ذئب (ذ)',    visualAr:'ذ' },
    { emoji:'J', article:'', de:'wie Joghurt',    en:'for Yogurt',    ar:'رمان (ر)',   visualAr:'ر' },
    { emoji:'K', article:'', de:'wie Katze',      en:'for Cat',       ar:'زرافة (ز)',  visualAr:'ز' },
    { emoji:'L', article:'', de:'wie Löwe',       en:'for Lion',      ar:'سمكة (س)',   visualAr:'س' },
    { emoji:'M', article:'', de:'wie Maus',       en:'for Mouse',     ar:'شمس (ش)',    visualAr:'ش' },
    { emoji:'N', article:'', de:'wie Nase',       en:'for Nose',      ar:'صقر (ص)',    visualAr:'ص' },
    { emoji:'O', article:'', de:'wie Orange',     en:'for Orange',    ar:'ضفدع (ض)',   visualAr:'ض' },
    { emoji:'P', article:'', de:'wie Papagei',    en:'for Parrot',    ar:'طائرة (ط)',  visualAr:'ط' },
    { emoji:'Q', article:'', de:'wie Qualle',     en:'for Jellyfish', ar:'ظرف (ظ)',    visualAr:'ظ' },
    { emoji:'R', article:'', de:'wie Regenbogen', en:'for Rainbow',   ar:'عصفور (ع)',  visualAr:'ع' },
    { emoji:'S', article:'', de:'wie Sonne',      en:'for Sun',       ar:'غزال (غ)',   visualAr:'غ' },
    { emoji:'T', article:'', de:'wie Tiger',      en:'for Tiger',     ar:'فيل (ف)',    visualAr:'ف' },
    { emoji:'U', article:'', de:'wie Uhr',        en:'for Clock',     ar:'قطة (ق)',    visualAr:'ق' },
    { emoji:'V', article:'', de:'wie Vogel',      en:'for Bird',      ar:'كتاب (ك)',   visualAr:'ك' },
    { emoji:'W', article:'', de:'wie Wolke',      en:'for Cloud',     ar:'ليمون (ل)',  visualAr:'ل' },
    { emoji:'X', article:'', de:'wie Xylofon',    en:'for Xylophone', ar:'موز (م)',    visualAr:'م' },
    { emoji:'Y', article:'', de:'wie Yak',        en:'for Yak',       ar:'نجمة (ن)',   visualAr:'ن' },
    { emoji:'Z', article:'', de:'wie Zebra',      en:'for Zebra',     ar:'هدهد (ه)',   visualAr:'ه' },
  ]},

  // ── Level 2: Body & Family ─────────────────────────────────────────────────
  body:        { title: 'Mein Körper', titleAr: 'جسمي',  items: [
    { emoji:'🗣️', article:'der', de:'Kopf',         en:'Head',  ar:'رأس',   arGender:'m' },
    { emoji:'👀', article:'die', de:'Augen',        en:'Eyes',  ar:'عيون',  arGender:'f' },
    { emoji:'👃', article:'die', de:'Nase',         en:'Nose',  ar:'أنف',   arGender:'m' },
    { emoji:'👄', article:'der', de:'Mund',         en:'Mouth', ar:'فم',    arGender:'m' },
    { emoji:'👂', article:'die', de:'Ohren',        en:'Ears',  ar:'أذنان', arGender:'f' },
    { emoji:'🤲', article:'die', de:'Hände',        en:'Hands', ar:'يدين',  arGender:'f' },
    { emoji:'🦶', article:'die', de:'Füße',         en:'Feet',  ar:'أقدام', arGender:'f' },
    { emoji:'🫄', article:'der', de:'Bauch',        en:'Belly', ar:'بطن',   arGender:'m' },
    { emoji:'🦵', article:'die', de:'Beine',        en:'Legs',  ar:'أرجل',  arGender:'f' },
    { emoji:'💇', article:'die', de:'Haare',        en:'Hair',  ar:'شعر',   arGender:'m' },
  ]},

  // ── Level 3: Home ──────────────────────────────────────────────────────────
  rooms:       { title: 'Das Haus (Räume)', titleAr: 'غرف المنزل', items: [
    { emoji:'🛋️', article:'das', de:'Wohnzimmer',   en:'Living Room', ar:'غرفة المعيشة', arGender:'f' },
    { emoji:'🛏️', article:'das', de:'Schlafzimmer', en:'Bedroom',     ar:'غرفة النوم',   arGender:'f' },
    { emoji:'🚿', article:'das', de:'Badezimmer',   en:'Bathroom',    ar:'الحمام',        arGender:'m' },
    { emoji:'🍳', article:'die', de:'Küche',        en:'Kitchen',     ar:'المطبخ',        arGender:'m' },
    { emoji:'🌱', article:'der', de:'Garten',       en:'Garden',      ar:'الحديقة',       arGender:'f' },
    { emoji:'🚪', article:'der', de:'Flur',         en:'Hallway',     ar:'الممر',         arGender:'m' },
    { emoji:'🧸', article:'das', de:'Kinderzimmer', en:'Kids Room',   ar:'غرفة الأطفال',  arGender:'f' },
    { emoji:'🍽️', article:'das', de:'Esszimmer',    en:'Dining Room', ar:'غرفة الطعام',   arGender:'f' },
  ]},
  bedroom:     { title: 'Schlafzimmer', titleAr: 'غرفة النوم', items: [
    { emoji:'🛏️', article:'das', de:'Bett',         en:'Bed',       ar:'سرير',   arGender:'m' },
    { emoji:'💡', article:'die', de:'Lampe',        en:'Lamp',      ar:'مصباح',  arGender:'m' },
    { emoji:'🪟', article:'das', de:'Fenster',      en:'Window',    ar:'نافذة',  arGender:'f' },
    { emoji:'🚪', article:'die', de:'Tür',          en:'Door',      ar:'باب',    arGender:'m' },
    { emoji:'📚', article:'das', de:'Regal',        en:'Shelf',     ar:'رف',     arGender:'m' },
    { emoji:'🪞', article:'der', de:'Spiegel',      en:'Mirror',    ar:'مرآة',   arGender:'f' },
    { emoji:'🎴', article:'der', de:'Teppich',      en:'Carpet',    ar:'سجادة',  arGender:'f' },
    { emoji:'🧸', article:'der', de:'Teddybär',     en:'Teddy Bear',ar:'دبدوب',  arGender:'m' },
  ]},
  bathroom:    { title: 'Badezimmer', titleAr: 'الحمام', items: [
    { emoji:'🪥', article:'die', de:'Zahnbürste',   en:'Toothbrush', ar:'فرشاة أسنان',   arGender:'f' },
    { emoji:'🧼', article:'die', de:'Seife',        en:'Soap',       ar:'صابون',         arGender:'m' },
    { emoji:'🧴', article:'das', de:'Shampoo',      en:'Shampoo',    ar:'شامبو',         arGender:'m' },
    { emoji:'🚿', article:'die', de:'Dusche',       en:'Shower',     ar:'دش',            arGender:'m' },
    { emoji:'🛁', article:'die', de:'Badewanne',    en:'Bathtub',    ar:'حوض استحمام',   arGender:'m' },
    { emoji:'🪞', article:'der', de:'Spiegel',      en:'Mirror',     ar:'مرآة',          arGender:'f' },
    { emoji:'🚽', article:'die', de:'Toilette',     en:'Toilet',     ar:'مرحاض',         arGender:'m' },
    { emoji:'🏊', article:'das', de:'Handtuch',     en:'Towel',      ar:'منشفة',         arGender:'f' },
  ]},
  living_room: { title: 'Wohnzimmer', titleAr: 'غرفة المعيشة', items: [
    { emoji:'🛋️', article:'das', de:'Sofa',         en:'Sofa',      ar:'أريكة',    arGender:'f' },
    { emoji:'📺', article:'der', de:'Fernseher',    en:'TV',        ar:'تلفاز',    arGender:'m' },
    { emoji:'🪑', article:'der', de:'Stuhl',        en:'Chair',     ar:'كرسي',     arGender:'m' },
    { emoji:'🍽️', article:'der', de:'Tisch',        en:'Table',     ar:'طاولة',    arGender:'f' },
    { emoji:'📚', article:'das', de:'Bücherregal',  en:'Bookshelf', ar:'مكتبة',    arGender:'f' },
    { emoji:'🌿', article:'die', de:'Pflanze',      en:'Plant',     ar:'نبات',     arGender:'m' },
    { emoji:'🖼️', article:'das', de:'Bild',         en:'Picture',   ar:'صورة',     arGender:'f' },
    { emoji:'🪟', article:'das', de:'Fenster',      en:'Window',    ar:'نافذة',    arGender:'f' },
  ]},
  kitchen:     { title: 'Küche', titleAr: 'المطبخ',  items: [
    { emoji:'🍳', article:'der', de:'Herd',         en:'Stove',  ar:'موقد',   arGender:'m' },
    { emoji:'❄️', article:'der', de:'Kühlschrank',  en:'Fridge', ar:'ثلاجة',  arGender:'f' },
    { emoji:'🍽️', article:'der', de:'Teller',       en:'Plate',  ar:'طبق',    arGender:'m' },
    { emoji:'🥄', article:'der', de:'Löffel',       en:'Spoon',  ar:'ملعقة',  arGender:'f' },
    { emoji:'🍴', article:'die', de:'Gabel',        en:'Fork',   ar:'شوكة',   arGender:'f' },
    { emoji:'🔪', article:'das', de:'Messer',       en:'Knife',  ar:'سكين',   arGender:'m' },
    { emoji:'🥛', article:'das', de:'Glas',         en:'Glass',  ar:'كوب',    arGender:'m' },
    { emoji:'🫖', article:'die', de:'Tasse',        en:'Cup',    ar:'فنجان',  arGender:'m' },
  ]},

  // ── Level 4: Nature ────────────────────────────────────────────────────────
  garden:      { title: 'Garten', titleAr: 'الحديقة', items: [
    { emoji:'🌳', article:'der', de:'Baum',          en:'Tree',       ar:'شجرة',       arGender:'f' },
    { emoji:'🌸', article:'die', de:'Blume',         en:'Flower',     ar:'زهرة',       arGender:'f' },
    { emoji:'🌿', article:'das', de:'Gras',          en:'Grass',      ar:'عشب',        arGender:'m' },
    { emoji:'🐝', article:'die', de:'Biene',         en:'Bee',        ar:'نحلة',       arGender:'f' },
    { emoji:'🦋', article:'der', de:'Schmetterling', en:'Butterfly',  ar:'فراشة',      arGender:'f' },
    { emoji:'🐦', article:'der', de:'Vogel',         en:'Bird',       ar:'عصفور',      arGender:'m' },
    { emoji:'🐰', article:'der', de:'Hase',          en:'Rabbit',     ar:'أرنب',       arGender:'m' },
    { emoji:'🪱', article:'der', de:'Regenwurm',     en:'Earthworm',  ar:'دودة الأرض', arGender:'f' },
  ]},
  weather:     { title: 'Wetter', titleAr: 'الطقس',  items: [
    { emoji:'☀️', article:'die', de:'Sonne',         en:'Sun',         ar:'الشمس',           arGender:'f' },
    { emoji:'🌧️', article:'der', de:'Regen',         en:'Rain',        ar:'المطر',           arGender:'m' },
    { emoji:'❄️', article:'der', de:'Schnee',        en:'Snow',        ar:'الثلج',           arGender:'m' },
    { emoji:'💨', article:'der', de:'Wind',          en:'Wind',        ar:'الرياح',          arGender:'f' },
    { emoji:'☁️', article:'die', de:'Wolke',         en:'Cloud',       ar:'غيمة',            arGender:'f' },
    { emoji:'🌈', article:'der', de:'Regenbogen',    en:'Rainbow',     ar:'قوس قزح',         arGender:'m' },
    { emoji:'⛈️', article:'das', de:'Gewitter',      en:'Storm',       ar:'عاصفة رعدية',     arGender:'f' },
    { emoji:'🌡️', article:'die', de:'Temperatur',    en:'Temperature', ar:'درجة الحرارة',    arGender:'f' },
  ]},

  // ── Level 6: World ─────────────────────────────────────────────────────────
  transport:   { title: 'Transport & Verkehr', titleAr: 'المواصلات', items: [
    { emoji:'🚗', article:'das', de:'Auto',          en:'Car',        ar:'سيارة',        arGender:'f' },
    { emoji:'🚌', article:'der', de:'Bus',           en:'Bus',        ar:'حافلة',        arGender:'f' },
    { emoji:'🚂', article:'der', de:'Zug',           en:'Train',      ar:'قطار',         arGender:'m' },
    { emoji:'🚲', article:'das', de:'Fahrrad',       en:'Bicycle',    ar:'دراجة',        arGender:'f' },
    { emoji:'✈️', article:'das', de:'Flugzeug',      en:'Airplane',   ar:'طائرة',        arGender:'f' },
    { emoji:'🚢', article:'das', de:'Schiff',        en:'Ship',       ar:'سفينة',        arGender:'f' },
    { emoji:'🏍️', article:'das', de:'Motorrad',      en:'Motorcycle', ar:'دراجة نارية',  arGender:'f' },
    { emoji:'🚛', article:'der', de:'LKW',           en:'Truck',      ar:'شاحنة',        arGender:'f' },
  ]},

  // ── Level 7: Society ───────────────────────────────────────────────────────
  clothes:     { title: 'Kleidung', titleAr: 'الملابس', items: [
    { emoji:'👕', article:'das', de:'T-Shirt',       en:'T-shirt', ar:'قميص',   arGender:'m' },
    { emoji:'👖', article:'die', de:'Hose',          en:'Pants',   ar:'بنطال',  arGender:'m' },
    { emoji:'👟', article:'die', de:'Schuhe',        en:'Shoes',   ar:'حذاء',   arGender:'m' },
    { emoji:'🧦', article:'die', de:'Socken',        en:'Socks',   ar:'جوارب',  arGender:'f' },
    { emoji:'🧥', article:'die', de:'Jacke',         en:'Jacket',  ar:'سترة',   arGender:'f' },
    { emoji:'🎩', article:'der', de:'Hut',           en:'Hat',     ar:'قبعة',   arGender:'f' },
    { emoji:'👗', article:'das', de:'Kleid',         en:'Dress',   ar:'فستان',  arGender:'m' },
    { emoji:'🧣', article:'der', de:'Schal',         en:'Scarf',   ar:'وشاح',   arGender:'m' },
  ]},
};

const KEYWORD_MAP = [
  { kw: ['farbe','lieblingsfarbe','welche farbe','magst du farbe',
          'color','colour','favourite color','favorite color','what color',
          'لون','ألوان','لونك المفضل','ما هو لونك'],                                 set: 'colors'     },
  { kw: ['frühstück','gefrühstückt','zum frühstück','morgens gegessen',
          'breakfast','had for breakfast','eat for breakfast',
          'فطور','الفطور','ماذا تناولت في الفطور'],                                  set: 'breakfast'  },
  { kw: ['lieblingsfrucht','obst','früchte','frucht',
          'fruit','fruits','favourite fruit','favorite fruit',
          'فاكهة','فواكه','فاكهتك المفضلة'],                                          set: 'fruits'     },
  { kw: ['lieblingstier','haustier','tier','tiere','welches tier',
          'animal','animals','favourite animal','favorite animal','pet',
          'حيوان','حيوانات','حيوان أليف','حيوانك المفضل'],                            set: 'animals'    },
  { kw: ['spielst','sport','fußball','basketball','lieblingssport',
          'sport','sports','football','soccer','favourite sport','favorite sport',
          'رياضة','كرة القدم','كرة السلة','رياضتك المفضلة'],                          set: 'sports'     },
  { kw: ['geschwister','bruder','schwester','familie','eltern','oma','opa',
          'family','siblings','brother','sister','parents',
          'عائلة','أخ','أخت','أهل','جد','جدة'],                                       set: 'family'     },
  { kw: ['schule','klasse','lehrer','lehrerin','lieblingsfach','fach',
          'school','class','teacher','subject','favourite subject',
          'مدرسة','صف','معلم','معلمة','مادتك المفضلة'],                              set: 'school'     },
  { kw: ['jahreszeit','sommer','winter','frühling','herbst','lieblingsjahreszeit',
          'season','seasons','summer','spring','autumn','favourite season',
          'فصل','فصول','الصيف','الشتاء','الربيع','الخريف'],                          set: 'seasons'     },
  { kw: ['lieblingsessen','lieblingsgericht','was isst','mittag','abend',
          'favourite food','favorite food','lunch','dinner','eat for lunch',
          'طعام مفضل','غداء','عشاء','ماذا تأكل'],                                    set: 'food'       },
  { kw: ['gemüse','karotte','brokkoli','kartoffel',
          'vegetable','vegetables','carrot','broccoli',
          'خضروات','خضار','جزرة','بروكلي'],                                          set: 'vegetables' },
  { kw: ['getränk','getränke','trinkst du',
          'drink','drinks','what do you drink',
          'مشروب','مشروبات','ماذا تشرب'],                                            set: 'drinks'     },
  { kw: ['eis','eiscreme','eissorte','lieblingseis',
          'ice cream','icecream','favourite ice cream',
          'آيس كريم','بوظة','نكهة الآيس كريم المفضلة'],                              set: 'icecream'   },
  { kw: ['hobby','hobbys','freizeit','was machst du gerne',
          'hobby','hobbies','free time','what do you like to do',
          'هواية','هوايات','وقت الفراغ','ماذا تحب أن تفعل'],                        set: 'hobbies'    },
  { kw: ['superpower','superkraft','zauberstab','magie','fliegen könntest',
          'superpower','magic wand','super power','if you could fly',
          'قوة خارقة','عصا سحرية','سحر','لو استطعت الطيران'],                        set: 'superpower' },
  { kw: ['beruf','was willst du werden','was möchtest du werden','traumberuf',
          'job','jobs','when you grow up','dream job','want to be',
          'مهنة','عندما تكبر','حلم مهنتك','تريد أن تصبح'],                          set: 'jobs'       },
  { kw: ['spielzeug','puppe','lieblingssspielzeug','lieblingsspielzeug',
          'toy','toys','favourite toy','favorite toy',
          'لعبة','ألعاب','لعبتك المفضلة'],                                          set: 'toys'       },
  // Level 1 — Basics
  { kw: ['hallo','tschüss','guten morgen','gute nacht','wie geht','ich heiße','vorstellen',
          'begrüßung','hello','goodbye','good morning','how are you','my name is',
          'مرحباً','مع السلامة','صباح الخير','كيف حالك','اسمي'],                     set: 'greetings'   },
  { kw: ['eins','zwei','drei','vier','fünf','zahlen 1','zählen bis zehn','count to 10',
          'one','two','three','four','five','numbers 1',
          'واحد','اثنان','ثلاثة','أرقام من واحد','عد إلى عشرة'],                    set: 'numbers1'    },
  { kw: ['elf','zwölf','dreizehn','vierzehn','fünfzehn','zahlen 11','zwanzig','bis 20',
          'eleven','twelve','thirteen','twenty','count to 20',
          'أحد عشر','اثنا عشر','عشرون','عد إلى عشرين'],                            set: 'numbers2'    },
  { kw: ['abc','das abc','buchstabe','buchstaben','alphabet','wie apfel','wie ball',
          'letter','letters','alphabet',
          'الحروف العربية','حرف','حروف','الأبجدية'],                                 set: 'alphabet'    },
  // Level 2 — Body
  { kw: ['körper','kopf','augen','nase','mund','ohren','hände','füße','bauch','beine',
          'body','head','eyes','nose','mouth','hands','feet','body parts',
          'جسم','جسمي','رأس','عيون','أنف','فم','يدين'],                            set: 'body'        },
  // Level 3 — Home
  { kw: ['zimmer im haus','welches zimmer','kinderzimmer','esszimmer',
          'rooms','house rooms','dining room',
          'غرف المنزل','غرفة الأطفال','غرفة الطعام'],                               set: 'rooms'       },
  { kw: ['bett','kissen','schlafzimmer möbel','nachttisch','schlafzimmer',
          'bed','pillow','bedroom furniture',
          'غرفة النوم','سرير','مخدة'],                                              set: 'bedroom'     },
  { kw: ['zahnbürste','seife','dusche','badewanne','toilette','shampoo','handtuch',
          'toothbrush','soap','shower','bathtub','toilet',
          'الحمام','فرشاة أسنان','صابون','دش'],                                     set: 'bathroom'    },
  { kw: ['sofa','fernseher','bücherregal','wohnzimmer möbel',
          'sofa','tv','television','living room furniture',
          'غرفة المعيشة','أريكة','تلفاز'],                                          set: 'living_room' },
  { kw: ['herd','kühlschrank','teller','löffel','gabel','messer','küche möbel',
          'stove','fridge','plate','spoon','fork','knife','kitchen',
          'المطبخ','ثلاجة','طبق','ملعقة','شوكة','سكين'],                           set: 'kitchen'     },
  // Level 4 — Nature
  { kw: ['baum','blume','biene','schmetterling','garten','regenwurm','hase garten',
          'tree','flower','bee','butterfly','garden',
          'الحديقة','شجرة','زهرة','نحلة','فراشة'],                                  set: 'garden'      },
  { kw: ['sonne','regen','schnee','wind','wolke','gewitter','wetter heute','wie ist das wetter',
          'sun','rain','snow','wind','cloud','storm','weather',
          'الطقس','الشمس','المطر','الثلج','الرياح','غيمة'],                        set: 'weather'     },
  // Level 6 — World
  { kw: ['auto','bus','zug','fahrrad','flugzeug','schiff','motorrad','lkw','verkehr',
          'car','train','bicycle','airplane','ship','transport','vehicle',
          'مواصلات','سيارة','حافلة','قطار','طائرة'],                                set: 'transport'   },
  // Level 7 — Society
  { kw: ['t-shirt','hose','schuhe','socken','jacke','hut','kleid','schal','kleidung',
          'shirt','pants','shoes','socks','jacket','hat','dress','clothes',
          'ملابس','قميص','بنطال','حذاء','فستان'],                                  set: 'clothes'     },
];

// Message sent to Teddy when the user picks a section from the dropdown
const SECTION_MESSAGES = {
  greetings:   'Lass uns Begrüßungen üben! Sag mir: Hallo!',
  numbers1:    'Lass uns die Zahlen 1 bis 10 lernen! Fang an: eins!',
  numbers2:    'Lass uns die Zahlen 11 bis 20 lernen! Kannst du elf sagen?',
  alphabet:    'Lass uns das ABC lernen! A wie Apfel — sag es nach!',
  colors:      'Lass uns Farben üben! Was ist deine Lieblingsfarbe?',
  family:      'Lass uns über Familie sprechen! Hast du Geschwister?',
  body:        'Lass uns den Körper lernen! Zeig mir deinen Kopf!',
  rooms:       'Lass uns die Zimmer im Haus lernen! In welchem Zimmer bist du gerade?',
  bedroom:     'Lass uns das Schlafzimmer erkunden! Was steht in deinem Zimmer?',
  bathroom:    'Lass uns das Badezimmer lernen! Welche Farbe hat deine Zahnbürste?',
  living_room: 'Lass uns das Wohnzimmer erkunden! Habt ihr ein Sofa?',
  kitchen:     'Lass uns die Küche lernen! Wer kocht bei euch?',
  garden:      'Lass uns den Garten erkunden! Habt ihr einen Baum im Garten?',
  seasons:     'Lass uns über Jahreszeiten sprechen! Was ist deine Lieblingszeit?',
  weather:     'Lass uns über das Wetter sprechen! Wie ist das Wetter heute?',
  animals:     'Lass uns Tiere lernen! Hast du ein Haustier?',
  breakfast:   'Lass uns über Frühstück sprechen! Was isst du morgens?',
  fruits:      'Lass uns Obst lernen! Was ist deine Lieblingsfrucht?',
  vegetables:  'Lass uns Gemüse lernen! Magst du Karotten?',
  drinks:      'Lass uns Getränke lernen! Was trinkst du am liebsten?',
  food:        'Lass uns über Lieblingsessen sprechen! Was ist dein Lieblingsessen?',
  icecream:    'Lass uns Eissorten lernen! Welche Eissorte magst du am liebsten?',
  school:      'Lass uns über Schule sprechen! Was ist dein Lieblingsfach?',
  transport:   'Lass uns Transport lernen! Wie fährst du zur Schule?',
  sports:      'Lass uns über Sport sprechen! Was spielst du gerne?',
  hobbies:     'Lass uns über Hobbys sprechen! Was machst du gerne in der Freizeit?',
  clothes:     'Lass uns Kleidung lernen! Was trägst du heute?',
  jobs:        'Lass uns Berufe lernen! Was möchtest du werden?',
  toys:        'Lass uns Spielzeug lernen! Was ist dein Lieblingsspielzeug?',
  superpower:  'Lass uns Superkräfte besprechen! Welche Superpower hättest du gerne?',
};

// Arabic equivalents — used instead of SECTION_MESSAGES when learning Arabic
const SECTION_MESSAGES_AR = {
  greetings:   'لنتدرب على التحية! قل: مرحباً!',
  numbers1:    'لنتعلم الأرقام من واحد إلى عشرة! ابدأ: واحد!',
  numbers2:    'لنتعلم الأرقام من أحد عشر إلى عشرين! هل يمكنك قول أحد عشر؟',
  alphabet:    'لنتعلم الحروف العربية! أ مثل أرنب — كررها!',
  colors:      'لنتدرب على الألوان! ما هو لونك المفضل؟',
  family:      'لنتحدث عن العائلة! هل لديك إخوة؟',
  body:        'لنتعلم أجزاء الجسم! أرني رأسك!',
  rooms:       'لنتعلم غرف المنزل! في أي غرفة أنت الآن؟',
  bedroom:     'لنكتشف غرفة النوم! ماذا يوجد في غرفتك؟',
  bathroom:    'لنتعلم عن الحمام! ما لون فرشاة أسنانك؟',
  living_room: 'لنكتشف غرفة المعيشة! هل لديكم أريكة؟',
  kitchen:     'لنتعلم عن المطبخ! من يطبخ عندكم؟',
  garden:      'لنكتشف الحديقة! هل لديكم شجرة في الحديقة؟',
  seasons:     'لنتحدث عن الفصول! ما هو فصلك المفضل؟',
  weather:     'لنتحدث عن الطقس! كيف هو الطقس اليوم؟',
  animals:     'لنتعلم الحيوانات! هل لديك حيوان أليف؟',
  breakfast:   'لنتحدث عن الفطور! ماذا تأكل في الصباح؟',
  fruits:      'لنتعلم الفواكه! ما هي فاكهتك المفضلة؟',
  vegetables:  'لنتعلم الخضروات! هل تحب الجزر؟',
  drinks:      'لنتعلم المشروبات! ماذا تحب أن تشرب؟',
  food:        'لنتحدث عن الطعام المفضل! ما هو طعامك المفضل؟',
  icecream:    'لنتعلم نكهات الآيس كريم! ما هي نكهتك المفضلة؟',
  school:      'لنتحدث عن المدرسة! ما هي مادتك المفضلة؟',
  transport:   'لنتعلم المواصلات! كيف تذهب إلى المدرسة؟',
  sports:      'لنتحدث عن الرياضة! ما الذي تحب أن تلعبه؟',
  hobbies:     'لنتحدث عن الهوايات! ماذا تحب أن تفعل في وقت فراغك؟',
  clothes:     'لنتعلم الملابس! ماذا ترتدي اليوم؟',
  jobs:        'لنتعلم المهن! ماذا تريد أن تصبح؟',
  toys:        'لنتعلم الألعاب! ما هي لعبتك المفضلة؟',
  superpower:  'لنتحدث عن القوى الخارقة! أي قوة خارقة تريدها؟',
};

function detectVocabSet(text) {
  const t = text.toLowerCase();
  for (const { kw, set } of KEYWORD_MAP) {
    if (kw.some(k => t.includes(k))) return set;
  }
  return null;
}

function showVocabPanel(setKey) {
  if (!setKey || setKey === _currentVocabSet) return;
  _currentVocabSet = setKey;
  const panel = document.getElementById('vocab-panel');
  const titleEl = document.getElementById('vocab-title');
  const cardsEl = document.getElementById('vocab-cards');
  if (!panel || !titleEl || !cardsEl) return;
  const vs = VOCAB_SETS[setKey];
  if (!vs) return;

  const isArabic = selLearnLang && selLearnLang.value === 'ar';
  titleEl.textContent = (isArabic && vs.titleAr) ? vs.titleAr : vs.title;
  titleEl.dir = isArabic ? 'rtl' : 'ltr';

  // Apply type-specific grid layout
  cardsEl.className = '';
  if (vs.type === 'phrase')  cardsEl.classList.add('phrase-grid');
  if (vs.type === 'number')  cardsEl.classList.add('number-grid');
  if (vs.type === 'abc')     cardsEl.classList.add('abc-grid');
  cardsEl.innerHTML = '';
  vs.items.forEach((item, i) => {
    const card = document.createElement('div');
    card.className = 'vocab-card' + (isArabic ? ' rtl' : '');
    card.style.animationDelay = `${i * 110}ms`;

    // The word actually taught in this session (Arabic when learning Arabic, German otherwise)
    const word = (isArabic && item.ar) ? item.ar : item.de;
    card.dataset.word = word;

    // Visual: big emoji, color swatch, or large digit/letter (Arabic alphabet swaps in its own letter)
    const bigChar = (isArabic && vs.type === 'abc' && item.visualAr) ? item.visualAr : item.emoji;
    const visual = vs.type === 'color'
      ? `<div class="vc-swatch" style="background:${item.color}"></div>`
      : vs.type === 'number'
      ? `<div class="vc-num">${item.emoji}</div>`
      : vs.type === 'abc'
      ? `<div class="vc-letter">${bigChar}</div>`
      : `<div class="vc-emoji">${item.emoji}</div>`;

    let wordHtml;
    if (isArabic) {
      // Gender-colored span (masculine/feminine) instead of German's three-way article coloring
      wordHtml = item.arGender
        ? `<span class="art gender-${item.arGender}">${word}</span>`
        : word;
    } else {
      // Article rendered as colored inline span; none shown if article is empty
      const artHtml = item.article
        ? `<span class="art ${item.article}">${item.article}</span> `
        : '';
      wordHtml = `${artHtml}${word}`;
    }
    card.innerHTML = `${visual}<div class="vc-de">${wordHtml}</div>`;

    // Tap to answer — sends the taught-language word as the kid's spoken response
    card.addEventListener('click', () => {
      document.querySelectorAll('.vocab-card').forEach(c => c.classList.remove('selected'));
      card.classList.add('selected');
      if (room.state === 'connected') {
        room.localParticipant.sendText(word, { topic: 'lk.chat' })
          .then(() => addMessage(speakerLabel(true), word, 'user'))
          .catch(err => console.warn('Card answer send failed:', err));
      }
    });
    cardsEl.appendChild(card);
  });
  panel.classList.remove('hidden');
}

// Highlight cards whose taught-language word appears in the agent's current speech
function highlightVocabCards(text) {
  if (!_currentVocabSet) return;
  const lower = text.toLowerCase();
  document.querySelectorAll('.vocab-card').forEach(card => {
    const word = (card.dataset.word || '').toLowerCase();
    if (word && lower.includes(word)) {
      card.classList.add('highlighted');
    } else {
      card.classList.remove('highlighted');
    }
  });
}

// Clear all highlights (called when agent finishes speaking)
function clearHighlights() {
  document.querySelectorAll('.vocab-card.highlighted').forEach(c => c.classList.remove('highlighted'));
}

// ── Character / Lip-Sync ───────────────────────────────────────────────────
let _audioCtx      = null;
let _analyser      = null;
let _lipFrame      = null;
let _stateTimer    = null;
let _currentVocabSet = null;

function setCharacterState(state) {
  const label = document.getElementById('char-state-label');
  const bear  = document.getElementById('lingua-bear');
  if (!label || !bear) return;
  const labels = {
    speaking:  'Spricht…',
    listening: 'Hört zu…',
    thinking:  'Denkt nach…',
    idle:      'Hallo!',
  };
  label.textContent = labels[state] || 'Hallo!';
  label.className   = state;
  bear.className    = state === 'speaking' ? 'speaking' : '';
}

function startLipSync(livekitTrack) {
  stopLipSync();
  try {
    _audioCtx = new (window.AudioContext || window.webkitAudioContext)();
    const stream = new MediaStream([livekitTrack.mediaStreamTrack]);
    const src    = _audioCtx.createMediaStreamSource(stream);
    _analyser    = _audioCtx.createAnalyser();
    _analyser.fftSize = 512;
    _analyser.smoothingTimeConstant = 0.55;
    src.connect(_analyser);
    // Do NOT connect to destination — audio already plays via agentAudioEl

    const buf   = new Uint8Array(_analyser.frequencyBinCount);
    const mouth = document.getElementById('bear-mouth');

    function frame() {
      _lipFrame = requestAnimationFrame(frame);
      _analyser.getByteFrequencyData(buf);
      // Bins 3–40 ≈ 250 Hz–3.4 kHz (speech range at 44.1 kHz / fftSize 512)
      let sum = 0;
      for (let i = 3; i <= 40; i++) sum += buf[i];
      const open = Math.min((sum / 38) / 55, 1);
      if (mouth) {
        mouth.setAttribute('ry', String(5 + open * 18));
        mouth.setAttribute('cy', String(153 + open * 5));
      }
    }
    frame();
  } catch (e) {
    console.warn('LipSync setup failed:', e);
  }
}

function stopLipSync() {
  if (_lipFrame)  { cancelAnimationFrame(_lipFrame); _lipFrame = null; }
  if (_audioCtx)  { _audioCtx.close().catch(() => {}); _audioCtx = null; }
  _analyser = null;
  const mouth = document.getElementById('bear-mouth');
  if (mouth) { mouth.setAttribute('ry', '5'); mouth.setAttribute('cy', '153'); }
  setCharacterState('idle');
}

// Random eye blink every 3–6 s
(function scheduleBlink() {
  setTimeout(() => {
    const bl = document.getElementById('blink-left');
    const br = document.getElementById('blink-right');
    if (bl && br) {
      let t = 0;
      const tick = setInterval(() => {
        t += 20;
        const half = 80;
        const raw  = t < half ? 14 * t / half : 14 * (2 - t / half);
        const ry   = String(Math.max(0, Math.min(14, Math.round(raw))));
        bl.setAttribute('ry', ry);
        br.setAttribute('ry', ry);
        if (t >= half * 2) {
          bl.setAttribute('ry', '0');
          br.setAttribute('ry', '0');
          clearInterval(tick);
        }
      }, 16);
    }
    scheduleBlink();
  }, 3000 + Math.random() * 4000);
})();

const LANGUAGE_NAMES = {
  en: "English", hi: "Hindi", de: "German", ar: "Arabic",
};

const MODEL_LABELS = {
  pipeline: "OpenAI (GPT)",
  gemini_live: "Gemini",
  nvidia: "NVIDIA (Free)",
};

const room = new Room();

// ── Helpers ────────────────────────────────────────────────────────────────
function setStatus(text) { statusEl.textContent = text; }

function escapeHtml(v) {
  return String(v)
    .replaceAll("&", "&amp;").replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;").replaceAll('"', "&quot;");
}

// True while the learner's target language is Arabic — drives RTL layout and
// Arabic speaker labels throughout the transcript.
function isArabicLearn() { return !!(selLearnLang && selLearnLang.value === 'ar'); }

function speakerLabel(isUser) {
  if (isArabicLearn()) return isUser ? 'أنت' : 'تيدي';
  return isUser ? 'Du' : 'Teddy';
}

function addMessage(who, text, kind = "system") {
  const div = document.createElement("div");
  div.className = `msg ${kind}`;
  if (kind === "system") {
    div.textContent = text;
  } else {
    if (isArabicLearn()) div.dir = 'rtl';
    div.innerHTML = `<span class="who">${escapeHtml(who)}:</span> ${escapeHtml(text)}`;
  }
  messagesEl.appendChild(div);
  messagesEl.scrollTop = messagesEl.scrollHeight;
}

// ── Build voice config from UI selections ──────────────────────────────────
function getVoiceConfig() {
  return {
    voice_mode: selModel.value,
    language: selLearnLang.value,
    native_language: selNativeLang.value,
  };
}

// ── Connection ─────────────────────────────────────────────────────────────
async function fetchConnectionDetails(voiceConfig) {
  const res = await fetch("/api/connection-details", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ voice_config: voiceConfig }),
  });
  if (!res.ok) throw new Error((await res.text()) || `HTTP ${res.status}`);
  return res.json();
}

// ── Transcription (streaming, word-by-word safe) ───────────────────────────
const activeSegments = {};
const _captionDivsByTurn = {}; // turn_id -> its standalone translation-caption line

room.on(RoomEvent.TranscriptionReceived, (segments, participant) => {
  const kind = participant?.isLocal ? "user" : "agent";
  const who  = speakerLabel(participant?.isLocal);

  // Update character state
  if (participant?.isLocal) {
    setCharacterState('listening');
    clearTimeout(_stateTimer);
  } else {
    setCharacterState('speaking');
    clearTimeout(_stateTimer);
    _stateTimer = setTimeout(() => {
      setCharacterState('idle');
      clearHighlights();
    }, 3500);
  }

  for (const segment of segments) {
    const text = (segment.text || "").trim();
    if (!text) continue;
    if (!activeSegments[segment.id]) {
      const div = document.createElement("div");
      div.className = `msg ${kind}`;
      if (isArabicLearn()) div.dir = 'rtl';
      div.innerHTML = `<span class="who">${who}:</span> <span class="seg-text"></span>`;
      messagesEl.appendChild(div);
      activeSegments[segment.id] = div.querySelector(".seg-text");
    }
    activeSegments[segment.id].textContent = text;
    messagesEl.scrollTop = messagesEl.scrollHeight;

    if (!participant?.isLocal) {
      // Live highlight: as agent speaks, glow matching vocab cards in real time
      highlightVocabCards(text);
      if (segment.final) {
        // Detect new vocab topic from completed sentence
        const detected = detectVocabSet(text);
        if (detected) showVocabPanel(detected);
        // Clear highlights briefly then let next segment re-highlight
        setTimeout(clearHighlights, 800);
      }
    }
    if (segment.final) delete activeSegments[segment.id];
  }
});

// ── Data messages from agent ───────────────────────────────────────────────
room.on(RoomEvent.DataReceived, (payload, participant) => {
  try {
    const msg = JSON.parse(new TextDecoder().decode(payload));
    if (msg.type === "trace_info") {
      currentSessionId = msg.session_id || currentRoomName;
      return;
    }
    if (msg.type === "caption" && msg.translation && msg.turn_id) {
      // Silent translation caption — never spoken, text only. Keyed by turn_id
      // (not "the last Teddy bubble"): with non-streaming TTS like Edge TTS,
      // this text can arrive well before that turn's transcript bubble exists,
      // so attaching to "whatever's last" would land on the wrong turn.
      let cap = _captionDivsByTurn[msg.turn_id];
      if (!cap) {
        cap = document.createElement("div");
        cap.className = "msg caption";
        cap.dir = 'ltr'; // English caption always reads left-to-right, even under an RTL Arabic line
        messagesEl.appendChild(cap);
        _captionDivsByTurn[msg.turn_id] = cap;
      }
      cap.textContent = msg.translation;
      messagesEl.scrollTop = messagesEl.scrollHeight;
      return;
    }
    if (msg.type === "vocab_progress" && msg.set_key) {
      // Authoritative drill state from the backend: which card is active, which
      // words are done, and which single word Teddy is asking about right now.
      // Always shows the matching card panel so the visuals never fall out of
      // sync with what's actually being drilled server-side.
      showVocabPanel(msg.set_key);
      const doneSet = new Set(msg.done || []);
      document.querySelectorAll('.vocab-card').forEach(card => {
        const word = card.dataset.word || '';
        card.classList.toggle('vocab-done', doneSet.has(word));
        card.classList.toggle('vocab-current', !!msg.current && word === msg.current);
      });
      return;
    }
    if (typeof msg === "string" || msg.text) {
      const text = msg.text || msg;
      const who = participant?.isLocal ? "You" : "Coach";
      addMessage(who, text, participant?.isLocal ? "user" : "agent");
    }
  } catch {
    // Non-JSON data — ignore
  }
});

// ── Audio ──────────────────────────────────────────────────────────────────
room.on(RoomEvent.TrackSubscribed, (track, _pub, participant) => {
  if (track.kind === Track.Kind.Audio && !participant.isLocal) {
    track.attach(agentAudioEl);
    addMessage("", "Teddy ist da! Sprich mit ihm!", "system");
    startLipSync(track);

    // Trigger pre-selected section: show vocab cards + tell Teddy the topic
    if (_pendingSection) {
      const key = _pendingSection;
      _pendingSection = null;
      _currentVocabSet = null;
      showVocabPanel(key);
      const isArabic = selLearnLang && selLearnLang.value === 'ar';
      const msg = isArabic ? (SECTION_MESSAGES_AR[key] || SECTION_MESSAGES[key]) : SECTION_MESSAGES[key];
      if (msg) {
        // Small delay so Teddy's greeting fires first
        setTimeout(() => {
          room.localParticipant.sendText(msg, { topic: 'lk.chat' })
            .then(() => addMessage(speakerLabel(true), msg, 'user'))
            .catch(err => console.warn('Pending section message failed:', err));
        }, 2500);
      }
    }
  }
});

// ── Disconnect → show feedback ─────────────────────────────────────────────
room.on(RoomEvent.Disconnected, () => {
  stopLipSync();
  _currentVocabSet = null;
  const vp = document.getElementById('vocab-panel');
  if (vp) vp.classList.add('hidden');
  _pendingSection = null;
  setStatus("Session ended.");
  sessionEl.classList.add("hidden");
  showFeedback();
});

// ── Start call ─────────────────────────────────────────────────────────────
async function startCall() {
  const learnLang  = selLearnLang.value;
  const nativeLang = selNativeLang.value;

  if (learnLang === nativeLang) {
    setStatus("⚠️ Please choose a language different from your native one.");
    return;
  }

  btnStart.disabled = true;
  setStatus("Connecting…");

  try {
    const voiceConfig = getVoiceConfig();
    const details = await fetchConnectionDetails(voiceConfig);
    currentRoomName  = details.roomName;
    currentSessionId = details.roomName;

    messagesEl.innerHTML = "";
    sessionEl.classList.remove("hidden");
    welcomeEl.classList.add("hidden");

    const learnName  = LANGUAGE_NAMES[learnLang]  || learnLang;
    const nativeName = LANGUAGE_NAMES[nativeLang] || nativeLang;
    const modelLabel = MODEL_LABELS[selModel.value] || selModel.value;

    langLabelEl.textContent = `${learnName} ← ${nativeName}`;
    modeLabelEl.textContent = modelLabel;

    _pendingSection = selSection ? (selSection.value || null) : null;
    addMessage("", `Teddy lernt ${learnName} mit dir! Er begrüßt dich gleich…`, "system");

    await Promise.all([
      room.localParticipant.setMicrophoneEnabled(true),
      room.connect(details.serverUrl, details.participantToken),
    ]);
    setStatus(`Connected — speak in ${learnName} or ${nativeName}`);
  } catch (err) {
    console.error(err);
    setStatus(`Error: ${err.message}`);
    welcomeEl.classList.remove("hidden");
    sessionEl.classList.add("hidden");
  } finally {
    btnStart.disabled = false;
  }
}

// ── End call ───────────────────────────────────────────────────────────────
async function endCall() {
  await room.disconnect();
}

// ── Feedback modal ─────────────────────────────────────────────────────────
function showFeedback() {
  selectedRating = null;
  feedbackComment.value = "";
  btnThumbsUp.classList.remove("selected-up");
  btnThumbsDown.classList.remove("selected-down");
  btnSubmitFeedback.disabled = true;
  feedbackOverlay.classList.remove("hidden");
}

function closeFeedback() {
  feedbackOverlay.classList.add("hidden");
  showWelcome();
}

function showWelcome() {
  welcomeEl.classList.remove("hidden");
  sessionEl.classList.add("hidden");
  messagesEl.innerHTML = "";
  setStatus("Ready — choose a language and click Let's Chat!");
}

btnThumbsUp.addEventListener("click", () => {
  selectedRating = 1;
  btnThumbsUp.classList.add("selected-up");
  btnThumbsDown.classList.remove("selected-down");
  btnSubmitFeedback.disabled = false;
});

btnThumbsDown.addEventListener("click", () => {
  selectedRating = 0;
  btnThumbsDown.classList.add("selected-down");
  btnThumbsUp.classList.remove("selected-up");
  btnSubmitFeedback.disabled = false;
});

btnSubmitFeedback.addEventListener("click", async () => {
  if (selectedRating === null) return;
  btnSubmitFeedback.disabled = true;
  btnSubmitFeedback.textContent = "Saving…";
  try {
    await fetch("/api/feedback", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        session_id: currentSessionId,
        rating: selectedRating,
        comment: feedbackComment.value.trim() || null,
      }),
    });
  } catch (e) {
    console.warn("Feedback submission failed:", e);
  }
  closeFeedback();
});

btnSkipFeedback.addEventListener("click", () => closeFeedback());

// ── Section / theme selector ───────────────────────────────────────────────
// On the welcome screen the selection is stored and triggered when the session
// starts (see TrackSubscribed handler). Nothing visual happens pre-session.
// If the user somehow changes it while connected (shouldn't happen), switch live.

// ── Wire up main buttons ───────────────────────────────────────────────────
btnStart.addEventListener("click", startCall);
btnEnd.addEventListener("click", endCall);

chatForm.addEventListener("submit", async (e) => {
  e.preventDefault();
  const text = chatInput.value.trim();
  if (!text || room.state !== "connected") return;
  chatInput.value = "";
  try {
    await room.localParticipant.sendText(text, { topic: "lk.chat" });
    addMessage(speakerLabel(true), text, "user");
  } catch (err) {
    addMessage("", `Send failed: ${err.message}`, "system");
  }
});
