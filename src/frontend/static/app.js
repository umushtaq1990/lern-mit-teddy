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
  colors:     { title: 'Farben',                   type: 'color', items: [
    { article:'das', de:'Rot',       en:'Red',        color:'#ef4444' },
    { article:'das', de:'Blau',      en:'Blue',       color:'#3b82f6' },
    { article:'das', de:'Grün',      en:'Green',      color:'#22c55e' },
    { article:'das', de:'Gelb',      en:'Yellow',     color:'#eab308' },
    { article:'das', de:'Orange',    en:'Orange',     color:'#f97316' },
    { article:'das', de:'Lila',      en:'Purple',     color:'#a855f7' },
    { article:'das', de:'Rosa',      en:'Pink',       color:'#ec4899' },
    { article:'das', de:'Schwarz',   en:'Black',      color:'#374151' },
    { article:'das', de:'Weiß',      en:'White',      color:'#d1d5db' },
    { article:'das', de:'Braun',     en:'Brown',      color:'#92400e' },
  ]},
  breakfast:  { title: 'Frühstück',                 items: [
    { emoji:'🥚', article:'das', de:'Ei',          en:'Egg'        },
    { emoji:'🍞', article:'das', de:'Brot',        en:'Bread'      },
    { emoji:'🥛', article:'die', de:'Milch',       en:'Milk'       },
    { emoji:'🧇', article:'die', de:'Waffeln',     en:'Waffles'    },
    { emoji:'🥣', article:'das', de:'Müsli',       en:'Cereal'     },
    { emoji:'🍳', article:'das', de:'Rührei',      en:'Scrambled eggs'},
    { emoji:'🥐', article:'das', de:'Croissant',   en:'Croissant'  },
    { emoji:'🍯', article:'der', de:'Honig',       en:'Honey'      },
    { emoji:'🧈', article:'die', de:'Butter',      en:'Butter'     },
    { emoji:'🍓', article:'die', de:'Beeren',      en:'Berries'    },
  ]},
  fruits:     { title: 'Obst',                       items: [
    { emoji:'🍎', article:'der', de:'Apfel',       en:'Apple'      },
    { emoji:'🍌', article:'die', de:'Banane',      en:'Banana'     },
    { emoji:'🍓', article:'die', de:'Erdbeere',    en:'Strawberry' },
    { emoji:'🍊', article:'die', de:'Orange',      en:'Orange'     },
    { emoji:'🍇', article:'die', de:'Trauben',     en:'Grapes'     },
    { emoji:'🍑', article:'der', de:'Pfirsich',    en:'Peach'      },
    { emoji:'🍒', article:'die', de:'Kirsche',     en:'Cherry'     },
    { emoji:'🍋', article:'die', de:'Zitrone',     en:'Lemon'      },
    { emoji:'🥭', article:'die', de:'Mango',       en:'Mango'      },
    { emoji:'🍍', article:'die', de:'Ananas',      en:'Pineapple'  },
  ]},
  animals:    { title: 'Tiere',                      items: [
    { emoji:'🐶', article:'der', de:'Hund',        en:'Dog'        },
    { emoji:'🐱', article:'die', de:'Katze',       en:'Cat'        },
    { emoji:'🦁', article:'der', de:'Löwe',        en:'Lion'       },
    { emoji:'🐘', article:'der', de:'Elefant',     en:'Elephant'   },
    { emoji:'🦒', article:'die', de:'Giraffe',     en:'Giraffe'    },
    { emoji:'🐧', article:'der', de:'Pinguin',     en:'Penguin'    },
    { emoji:'🦊', article:'der', de:'Fuchs',       en:'Fox'        },
    { emoji:'🐻', article:'der', de:'Bär',         en:'Bear'       },
    { emoji:'🐬', article:'der', de:'Delphin',     en:'Dolphin'    },
    { emoji:'🐒', article:'der', de:'Affe',        en:'Monkey'     },
  ]},
  sports:     { title: 'Sport & Spiele',      items: [
    { emoji:'⚽', article:'der', de:'Fußball',     en:'Football'   },
    { emoji:'🏀', article:'der', de:'Basketball',  en:'Basketball' },
    { emoji:'🎾', article:'das', de:'Tennis',      en:'Tennis'     },
    { emoji:'🏊', article:'das', de:'Schwimmen',   en:'Swimming'   },
    { emoji:'🚴', article:'das', de:'Radfahren',   en:'Cycling'    },
    { emoji:'🎮', article:'die', de:'Videospiele', en:'Video games'},
    { emoji:'🏃', article:'das', de:'Laufen',      en:'Running'    },
    { emoji:'🎨', article:'das', de:'Malen',       en:'Painting'   },
    { emoji:'🎵', article:'die', de:'Musik',       en:'Music'      },
    { emoji:'🧩', article:'das', de:'Puzzle',      en:'Puzzle'     },
  ]},
  family:     { title: 'Familie',                    items: [
    { emoji:'👨', article:'der', de:'Vater',       en:'Father'     },
    { emoji:'👩', article:'die', de:'Mutter',      en:'Mother'     },
    { emoji:'👦', article:'der', de:'Bruder',      en:'Brother'    },
    { emoji:'👧', article:'die', de:'Schwester',   en:'Sister'     },
    { emoji:'👴', article:'der', de:'Opa',         en:'Grandpa'    },
    { emoji:'👵', article:'die', de:'Oma',         en:'Grandma'    },
    { emoji:'👶', article:'das', de:'Baby',        en:'Baby'       },
    { emoji:'🐕', article:'der', de:'Hund',        en:'Dog'        },
  ]},
  school:     { title: 'Schule',                     items: [
    { emoji:'📚', article:'die', de:'Bücher',      en:'Books'      },
    { emoji:'✏️', article:'der', de:'Bleistift',   en:'Pencil'     },
    { emoji:'📐', article:'das', de:'Lineal',      en:'Ruler'      },
    { emoji:'🎒', article:'der', de:'Rucksack',    en:'Backpack'   },
    { emoji:'🧮', article:'die', de:'Mathe',       en:'Math'       },
    { emoji:'🎨', article:'die', de:'Kunst',       en:'Art'        },
    { emoji:'🌍', article:'die', de:'Geografie',   en:'Geography'  },
    { emoji:'🔬', article:'die', de:'Biologie',    en:'Biology'    },
    { emoji:'📖', article:'das', de:'Lesen',       en:'Reading'    },
  ]},
  seasons:    { title: 'Jahreszeiten',               items: [
    { emoji:'🌸', article:'der', de:'Frühling',    en:'Spring'     },
    { emoji:'☀️', article:'der', de:'Sommer',      en:'Summer'     },
    { emoji:'🍂', article:'der', de:'Herbst',      en:'Autumn'     },
    { emoji:'❄️', article:'der', de:'Winter',      en:'Winter'     },
    { emoji:'🌧️', article:'der', de:'Regen',       en:'Rain'       },
    { emoji:'⛄', article:'der', de:'Schnee',      en:'Snow'       },
    { emoji:'🌈', article:'der', de:'Regenbogen',  en:'Rainbow'    },
    { emoji:'☀️', article:'die', de:'Sonne',       en:'Sun'        },
  ]},
  food:       { title: 'Lieblingsessen',             items: [
    { emoji:'🍕', article:'die', de:'Pizza',       en:'Pizza'      },
    { emoji:'🍝', article:'die', de:'Nudeln',      en:'Pasta'      },
    { emoji:'🍔', article:'der', de:'Burger',      en:'Burger'     },
    { emoji:'🍚', article:'der', de:'Reis',        en:'Rice'       },
    { emoji:'🥗', article:'der', de:'Salat',       en:'Salad'      },
    { emoji:'🍜', article:'die', de:'Suppe',       en:'Soup'       },
    { emoji:'🍗', article:'das', de:'Hähnchen',    en:'Chicken'    },
    { emoji:'🥙', article:'das', de:'Sandwich',    en:'Sandwich'   },
    { emoji:'🧀', article:'der', de:'Käse',        en:'Cheese'     },
    { emoji:'🍣', article:'das', de:'Sushi',       en:'Sushi'      },
  ]},
  vegetables: { title: 'Gemüse',                     items: [
    { emoji:'🥕', article:'die', de:'Karotte',     en:'Carrot'     },
    { emoji:'🥦', article:'der', de:'Brokkoli',    en:'Broccoli'   },
    { emoji:'🍅', article:'die', de:'Tomate',      en:'Tomato'     },
    { emoji:'🥔', article:'die', de:'Kartoffel',   en:'Potato'     },
    { emoji:'🌽', article:'der', de:'Mais',        en:'Corn'       },
    { emoji:'🥒', article:'die', de:'Gurke',       en:'Cucumber'   },
    { emoji:'🫑', article:'die', de:'Paprika',     en:'Pepper'     },
    { emoji:'🧅', article:'die', de:'Zwiebel',     en:'Onion'      },
  ]},
  drinks:     { title: 'Getränke',                   items: [
    { emoji:'🥛', article:'die', de:'Milch',       en:'Milk'       },
    { emoji:'🧃', article:'der', de:'Saft',        en:'Juice'      },
    { emoji:'💧', article:'das', de:'Wasser',      en:'Water'      },
    { emoji:'🍵', article:'der', de:'Tee',         en:'Tea'        },
    { emoji:'🥤', article:'die', de:'Limo',        en:'Soda'       },
    { emoji:'🧋', article:'der', de:'Kakao',       en:'Cocoa'      },
  ]},
  icecream:   { title: 'Eis',                        items: [
    { emoji:'🍦', article:'die', de:'Vanille',     en:'Vanilla'    },
    { emoji:'🍫', article:'die', de:'Schokolade',  en:'Chocolate'  },
    { emoji:'🍓', article:'die', de:'Erdbeere',    en:'Strawberry' },
    { emoji:'🍋', article:'die', de:'Zitrone',     en:'Lemon'      },
    { emoji:'🍑', article:'der', de:'Pfirsich',    en:'Peach'      },
    { emoji:'🫐', article:'die', de:'Blaubeere',   en:'Blueberry'  },
  ]},
  hobbies:    { title: 'Hobbys',                     items: [
    { emoji:'📚', article:'das', de:'Lesen',       en:'Reading'    },
    { emoji:'🎨', article:'das', de:'Zeichnen',    en:'Drawing'    },
    { emoji:'🎵', article:'das', de:'Singen',      en:'Singing'    },
    { emoji:'💃', article:'das', de:'Tanzen',      en:'Dancing'    },
    { emoji:'🎮', article:'das', de:'Zocken',      en:'Gaming'     },
    { emoji:'🌱', article:'das', de:'Gärtnern',    en:'Gardening'  },
    { emoji:'🍳', article:'das', de:'Kochen',      en:'Cooking'    },
    { emoji:'🧵', article:'das', de:'Basteln',     en:'Crafts'     },
  ]},
  superpower: { title: 'Superkräfte',               items: [
    { emoji:'🦸', article:'das', de:'Fliegen',      en:'Flying'        },
    { emoji:'👁️', article:'die', de:'Unsichtbarkeit',en:'Invisibility' },
    { emoji:'🔮', article:'die', de:'Magie',        en:'Magic'         },
    { emoji:'💪', article:'die', de:'Super-Stärke', en:'Super Strength'},
    { emoji:'⚡', article:'der', de:'Blitz',        en:'Lightning'     },
    { emoji:'🌊', article:'das', de:'Wasser',       en:'Water Control' },
    { emoji:'🔥', article:'das', de:'Feuer',        en:'Fire'          },
    { emoji:'🧠', article:'das', de:'Gedankenlesen',en:'Mind Reading'  },
  ]},
  jobs:       { title: 'Berufe',                     items: [
    { emoji:'👨‍⚕️', article:'der', de:'Arzt',          en:'Doctor'     },
    { emoji:'👩‍🏫', article:'die', de:'Lehrerin',      en:'Teacher'    },
    { emoji:'👨‍🚒', article:'der', de:'Feuerwehrmann', en:'Firefighter'},
    { emoji:'👩‍🍳', article:'die', de:'Köchin',        en:'Chef'       },
    { emoji:'👨‍🚀', article:'der', de:'Astronaut',     en:'Astronaut'  },
    { emoji:'👩‍🎨', article:'die', de:'Künstlerin',    en:'Artist'     },
    { emoji:'👨‍💻', article:'der', de:'Programmierer', en:'Programmer' },
    { emoji:'⚽',   article:'der', de:'Fußballer',     en:'Footballer' },
  ]},
  toys:       { title: 'Spielzeug',                  items: [
    { emoji:'🪆', article:'die', de:'Puppe',        en:'Doll'       },
    { emoji:'🚗', article:'das', de:'Auto',         en:'Car'        },
    { emoji:'🧸', article:'der', de:'Teddybär',     en:'Teddy Bear' },
    { emoji:'🎪', article:'das', de:'Zelt',         en:'Tent'       },
    { emoji:'🪀', article:'das', de:'Jojo',         en:'Yo-yo'      },
    { emoji:'🎯', article:'die', de:'Zielscheibe',  en:'Target'     },
    { emoji:'🧲', article:'der', de:'Magnet',       en:'Magnet'     },
    { emoji:'🪁', article:'die', de:'Schleuder',    en:'Slingshot'  },
  ]},

  // ── Level 1: Basics ────────────────────────────────────────────────────────
  greetings:  { title: 'Hallo! (Begrüßung)', type: 'phrase', items: [
    { emoji:'👋', article:'', de:'Hallo!',               en:'Hello!'             },
    { emoji:'👋', article:'', de:'Tschüss!',             en:'Goodbye!'           },
    { emoji:'🌅', article:'', de:'Guten Morgen!',        en:'Good morning!'      },
    { emoji:'🌙', article:'', de:'Gute Nacht!',          en:'Good night!'        },
    { emoji:'🤝', article:'', de:'Wie geht\'s?',         en:'How are you?'       },
    { emoji:'😊', article:'', de:'Mir geht\'s gut!',     en:'I\'m fine!'         },
    { emoji:'🙋', article:'', de:'Ich heiße…',           en:'My name is…'        },
    { emoji:'🎂', article:'', de:'Ich bin … Jahre alt',  en:'I am … years old'   },
    { emoji:'🌍', article:'', de:'Woher kommst du?',     en:'Where are you from?'},
    { emoji:'🏠', article:'', de:'Ich komme aus…',       en:'I come from…'       },
  ]},
  numbers1:   { title: 'Zahlen 1–10', type: 'number', items: [
    { emoji:'1', article:'', de:'eins',    en:'one'    },
    { emoji:'2', article:'', de:'zwei',    en:'two'    },
    { emoji:'3', article:'', de:'drei',    en:'three'  },
    { emoji:'4', article:'', de:'vier',    en:'four'   },
    { emoji:'5', article:'', de:'fünf',    en:'five'   },
    { emoji:'6', article:'', de:'sechs',   en:'six'    },
    { emoji:'7', article:'', de:'sieben',  en:'seven'  },
    { emoji:'8', article:'', de:'acht',    en:'eight'  },
    { emoji:'9', article:'', de:'neun',    en:'nine'   },
    { emoji:'🔟', article:'', de:'zehn',   en:'ten'    },
  ]},
  numbers2:   { title: 'Zahlen 11–20', type: 'number', items: [
    { emoji:'11', article:'', de:'elf',          en:'eleven'    },
    { emoji:'12', article:'', de:'zwölf',        en:'twelve'    },
    { emoji:'13', article:'', de:'dreizehn',     en:'thirteen'  },
    { emoji:'14', article:'', de:'vierzehn',     en:'fourteen'  },
    { emoji:'15', article:'', de:'fünfzehn',     en:'fifteen'   },
    { emoji:'16', article:'', de:'sechzehn',     en:'sixteen'   },
    { emoji:'17', article:'', de:'siebzehn',     en:'seventeen' },
    { emoji:'18', article:'', de:'achtzehn',     en:'eighteen'  },
    { emoji:'19', article:'', de:'neunzehn',     en:'nineteen'  },
    { emoji:'20', article:'', de:'zwanzig',      en:'twenty'    },
  ]},
  alphabet:   { title: 'Das ABC', type: 'abc', items: [
    { emoji:'A', article:'', de:'wie Apfel',      en:'for Apple'     },
    { emoji:'B', article:'', de:'wie Ball',       en:'for Ball'      },
    { emoji:'C', article:'', de:'wie Computer',   en:'for Computer'  },
    { emoji:'D', article:'', de:'wie Delfin',     en:'for Dolphin'   },
    { emoji:'E', article:'', de:'wie Elefant',    en:'for Elephant'  },
    { emoji:'F', article:'', de:'wie Fisch',      en:'for Fish'      },
    { emoji:'G', article:'', de:'wie Giraffe',    en:'for Giraffe'   },
    { emoji:'H', article:'', de:'wie Hund',       en:'for Dog'       },
    { emoji:'I', article:'', de:'wie Igel',       en:'for Hedgehog'  },
    { emoji:'J', article:'', de:'wie Joghurt',    en:'for Yogurt'    },
    { emoji:'K', article:'', de:'wie Katze',      en:'for Cat'       },
    { emoji:'L', article:'', de:'wie Löwe',       en:'for Lion'      },
    { emoji:'M', article:'', de:'wie Maus',       en:'for Mouse'     },
    { emoji:'N', article:'', de:'wie Nase',       en:'for Nose'      },
    { emoji:'O', article:'', de:'wie Orange',     en:'for Orange'    },
    { emoji:'P', article:'', de:'wie Papagei',    en:'for Parrot'    },
    { emoji:'Q', article:'', de:'wie Qualle',     en:'for Jellyfish' },
    { emoji:'R', article:'', de:'wie Regenbogen', en:'for Rainbow'   },
    { emoji:'S', article:'', de:'wie Sonne',      en:'for Sun'       },
    { emoji:'T', article:'', de:'wie Tiger',      en:'for Tiger'     },
    { emoji:'U', article:'', de:'wie Uhr',        en:'for Clock'     },
    { emoji:'V', article:'', de:'wie Vogel',      en:'for Bird'      },
    { emoji:'W', article:'', de:'wie Wolke',      en:'for Cloud'     },
    { emoji:'X', article:'', de:'wie Xylofon',    en:'for Xylophone' },
    { emoji:'Y', article:'', de:'wie Yak',        en:'for Yak'       },
    { emoji:'Z', article:'', de:'wie Zebra',      en:'for Zebra'     },
  ]},

  // ── Level 2: Body & Family ─────────────────────────────────────────────────
  body:        { title: 'Mein Körper',               items: [
    { emoji:'🗣️', article:'der', de:'Kopf',         en:'Head'    },
    { emoji:'👀', article:'die', de:'Augen',        en:'Eyes'    },
    { emoji:'👃', article:'die', de:'Nase',         en:'Nose'    },
    { emoji:'👄', article:'der', de:'Mund',         en:'Mouth'   },
    { emoji:'👂', article:'die', de:'Ohren',        en:'Ears'    },
    { emoji:'🤲', article:'die', de:'Hände',        en:'Hands'   },
    { emoji:'🦶', article:'die', de:'Füße',         en:'Feet'    },
    { emoji:'🫄', article:'der', de:'Bauch',        en:'Belly'   },
    { emoji:'🦵', article:'die', de:'Beine',        en:'Legs'    },
    { emoji:'💇', article:'die', de:'Haare',        en:'Hair'    },
  ]},

  // ── Level 3: Home ──────────────────────────────────────────────────────────
  rooms:       { title: 'Das Haus (Räume)',           items: [
    { emoji:'🛋️', article:'das', de:'Wohnzimmer',   en:'Living Room'  },
    { emoji:'🛏️', article:'das', de:'Schlafzimmer', en:'Bedroom'      },
    { emoji:'🚿', article:'das', de:'Badezimmer',   en:'Bathroom'     },
    { emoji:'🍳', article:'die', de:'Küche',        en:'Kitchen'      },
    { emoji:'🌱', article:'der', de:'Garten',       en:'Garden'       },
    { emoji:'🚪', article:'der', de:'Flur',         en:'Hallway'      },
    { emoji:'🧸', article:'das', de:'Kinderzimmer', en:'Kids Room'    },
    { emoji:'🍽️', article:'das', de:'Esszimmer',    en:'Dining Room'  },
  ]},
  bedroom:     { title: 'Schlafzimmer',               items: [
    { emoji:'🛏️', article:'das', de:'Bett',         en:'Bed'        },
    { emoji:'💡', article:'die', de:'Lampe',        en:'Lamp'       },
    { emoji:'🪟', article:'das', de:'Fenster',      en:'Window'     },
    { emoji:'🚪', article:'die', de:'Tür',          en:'Door'       },
    { emoji:'📚', article:'das', de:'Regal',        en:'Shelf'      },
    { emoji:'🪞', article:'der', de:'Spiegel',      en:'Mirror'     },
    { emoji:'🎴', article:'der', de:'Teppich',      en:'Carpet'     },
    { emoji:'🧸', article:'der', de:'Teddybär',     en:'Teddy Bear' },
  ]},
  bathroom:    { title: 'Badezimmer',                 items: [
    { emoji:'🪥', article:'die', de:'Zahnbürste',   en:'Toothbrush' },
    { emoji:'🧼', article:'die', de:'Seife',        en:'Soap'       },
    { emoji:'🧴', article:'das', de:'Shampoo',      en:'Shampoo'    },
    { emoji:'🚿', article:'die', de:'Dusche',       en:'Shower'     },
    { emoji:'🛁', article:'die', de:'Badewanne',    en:'Bathtub'    },
    { emoji:'🪞', article:'der', de:'Spiegel',      en:'Mirror'     },
    { emoji:'🚽', article:'die', de:'Toilette',     en:'Toilet'     },
    { emoji:'🏊', article:'das', de:'Handtuch',     en:'Towel'      },
  ]},
  living_room: { title: 'Wohnzimmer',                 items: [
    { emoji:'🛋️', article:'das', de:'Sofa',         en:'Sofa'       },
    { emoji:'📺', article:'der', de:'Fernseher',    en:'TV'         },
    { emoji:'🪑', article:'der', de:'Stuhl',        en:'Chair'      },
    { emoji:'🍽️', article:'der', de:'Tisch',        en:'Table'      },
    { emoji:'📚', article:'das', de:'Bücherregal',  en:'Bookshelf'  },
    { emoji:'🌿', article:'die', de:'Pflanze',      en:'Plant'      },
    { emoji:'🖼️', article:'das', de:'Bild',         en:'Picture'    },
    { emoji:'🪟', article:'das', de:'Fenster',      en:'Window'     },
  ]},
  kitchen:     { title: 'Küche',                      items: [
    { emoji:'🍳', article:'der', de:'Herd',         en:'Stove'  },
    { emoji:'❄️', article:'der', de:'Kühlschrank',  en:'Fridge' },
    { emoji:'🍽️', article:'der', de:'Teller',       en:'Plate'  },
    { emoji:'🥄', article:'der', de:'Löffel',       en:'Spoon'  },
    { emoji:'🍴', article:'die', de:'Gabel',        en:'Fork'   },
    { emoji:'🔪', article:'das', de:'Messer',       en:'Knife'  },
    { emoji:'🥛', article:'das', de:'Glas',         en:'Glass'  },
    { emoji:'🫖', article:'die', de:'Tasse',        en:'Cup'    },
  ]},

  // ── Level 4: Nature ────────────────────────────────────────────────────────
  garden:      { title: 'Garten',                     items: [
    { emoji:'🌳', article:'der', de:'Baum',          en:'Tree'       },
    { emoji:'🌸', article:'die', de:'Blume',         en:'Flower'     },
    { emoji:'🌿', article:'das', de:'Gras',          en:'Grass'      },
    { emoji:'🐝', article:'die', de:'Biene',         en:'Bee'        },
    { emoji:'🦋', article:'der', de:'Schmetterling', en:'Butterfly'  },
    { emoji:'🐦', article:'der', de:'Vogel',         en:'Bird'       },
    { emoji:'🐰', article:'der', de:'Hase',          en:'Rabbit'     },
    { emoji:'🪱', article:'der', de:'Regenwurm',     en:'Earthworm'  },
  ]},
  weather:     { title: 'Wetter',                     items: [
    { emoji:'☀️', article:'die', de:'Sonne',         en:'Sun'         },
    { emoji:'🌧️', article:'der', de:'Regen',         en:'Rain'        },
    { emoji:'❄️', article:'der', de:'Schnee',        en:'Snow'        },
    { emoji:'💨', article:'der', de:'Wind',          en:'Wind'        },
    { emoji:'☁️', article:'die', de:'Wolke',         en:'Cloud'       },
    { emoji:'🌈', article:'der', de:'Regenbogen',    en:'Rainbow'     },
    { emoji:'⛈️', article:'das', de:'Gewitter',      en:'Storm'       },
    { emoji:'🌡️', article:'die', de:'Temperatur',    en:'Temperature' },
  ]},

  // ── Level 6: World ─────────────────────────────────────────────────────────
  transport:   { title: 'Transport & Verkehr',         items: [
    { emoji:'🚗', article:'das', de:'Auto',          en:'Car'        },
    { emoji:'🚌', article:'der', de:'Bus',           en:'Bus'        },
    { emoji:'🚂', article:'der', de:'Zug',           en:'Train'      },
    { emoji:'🚲', article:'das', de:'Fahrrad',       en:'Bicycle'    },
    { emoji:'✈️', article:'das', de:'Flugzeug',      en:'Airplane'   },
    { emoji:'🚢', article:'das', de:'Schiff',        en:'Ship'       },
    { emoji:'🏍️', article:'das', de:'Motorrad',      en:'Motorcycle' },
    { emoji:'🚛', article:'der', de:'LKW',           en:'Truck'      },
  ]},

  // ── Level 7: Society ───────────────────────────────────────────────────────
  clothes:     { title: 'Kleidung',                   items: [
    { emoji:'👕', article:'das', de:'T-Shirt',       en:'T-shirt'  },
    { emoji:'👖', article:'die', de:'Hose',          en:'Pants'    },
    { emoji:'👟', article:'die', de:'Schuhe',        en:'Shoes'    },
    { emoji:'🧦', article:'die', de:'Socken',        en:'Socks'    },
    { emoji:'🧥', article:'die', de:'Jacke',         en:'Jacket'   },
    { emoji:'🎩', article:'der', de:'Hut',           en:'Hat'      },
    { emoji:'👗', article:'das', de:'Kleid',         en:'Dress'    },
    { emoji:'🧣', article:'der', de:'Schal',         en:'Scarf'    },
  ]},
};

const KEYWORD_MAP = [
  { kw: ['farbe','lieblingsfarbe','welche farbe','magst du farbe',
          'color','colour','favourite color','favorite color','what color'],        set: 'colors'     },
  { kw: ['frühstück','gefrühstückt','zum frühstück','morgens gegessen',
          'breakfast','had for breakfast','eat for breakfast'],                     set: 'breakfast'  },
  { kw: ['lieblingsfrucht','obst','früchte','frucht',
          'fruit','fruits','favourite fruit','favorite fruit'],                     set: 'fruits'     },
  { kw: ['lieblingstier','haustier','tier','tiere','welches tier',
          'animal','animals','favourite animal','favorite animal','pet'],           set: 'animals'    },
  { kw: ['spielst','sport','fußball','basketball','lieblingssport',
          'sport','sports','football','soccer','favourite sport','favorite sport'], set: 'sports'     },
  { kw: ['geschwister','bruder','schwester','familie','eltern','oma','opa',
          'family','siblings','brother','sister','parents'],                        set: 'family'     },
  { kw: ['schule','klasse','lehrer','lehrerin','lieblingsfach','fach',
          'school','class','teacher','subject','favourite subject'],                set: 'school'     },
  { kw: ['jahreszeit','sommer','winter','frühling','herbst','lieblingsjahreszeit',
          'season','seasons','summer','spring','autumn','favourite season'],              set: 'seasons'     },
  { kw: ['lieblingsessen','lieblingsgericht','was isst','mittag','abend',
          'favourite food','favorite food','lunch','dinner','eat for lunch'],       set: 'food'       },
  { kw: ['gemüse','karotte','brokkoli','kartoffel',
          'vegetable','vegetables','carrot','broccoli'],                            set: 'vegetables' },
  { kw: ['getränk','getränke','trinkst du',
          'drink','drinks','what do you drink'],                                    set: 'drinks'     },
  { kw: ['eis','eiscreme','eissorte','lieblingseis',
          'ice cream','icecream','favourite ice cream'],                            set: 'icecream'   },
  { kw: ['hobby','hobbys','freizeit','was machst du gerne',
          'hobby','hobbies','free time','what do you like to do'],                 set: 'hobbies'    },
  { kw: ['superpower','superkraft','zauberstab','magie','fliegen könntest',
          'superpower','magic wand','super power','if you could fly'],             set: 'superpower' },
  { kw: ['beruf','was willst du werden','was möchtest du werden','traumberuf',
          'job','jobs','when you grow up','dream job','want to be'],               set: 'jobs'       },
  { kw: ['spielzeug','puppe','lieblingssspielzeug','lieblingsspielzeug',
          'toy','toys','favourite toy','favorite toy'],                             set: 'toys'       },
  // Level 1 — Basics
  { kw: ['hallo','tschüss','guten morgen','gute nacht','wie geht','ich heiße','vorstellen',
          'begrüßung','hello','goodbye','good morning','how are you','my name is'],  set: 'greetings'   },
  { kw: ['eins','zwei','drei','vier','fünf','zahlen 1','zählen bis zehn','count to 10',
          'one','two','three','four','five','numbers 1'],                            set: 'numbers1'    },
  { kw: ['elf','zwölf','dreizehn','vierzehn','fünfzehn','zahlen 11','zwanzig','bis 20',
          'eleven','twelve','thirteen','twenty','count to 20'],                      set: 'numbers2'    },
  { kw: ['abc','das abc','buchstabe','buchstaben','alphabet','wie apfel','wie ball',
          'letter','letters','alphabet'],                                             set: 'alphabet'    },
  // Level 2 — Body
  { kw: ['körper','kopf','augen','nase','mund','ohren','hände','füße','bauch','beine',
          'body','head','eyes','nose','mouth','hands','feet','body parts'],          set: 'body'        },
  // Level 3 — Home
  { kw: ['zimmer im haus','welches zimmer','kinderzimmer','esszimmer',
          'rooms','house rooms','dining room'],                                      set: 'rooms'       },
  { kw: ['bett','kissen','schlafzimmer möbel','nachttisch','schlafzimmer',
          'bed','pillow','bedroom furniture'],                                       set: 'bedroom'     },
  { kw: ['zahnbürste','seife','dusche','badewanne','toilette','shampoo','handtuch',
          'toothbrush','soap','shower','bathtub','toilet'],                          set: 'bathroom'    },
  { kw: ['sofa','fernseher','bücherregal','wohnzimmer möbel',
          'sofa','tv','television','living room furniture'],                         set: 'living_room' },
  { kw: ['herd','kühlschrank','teller','löffel','gabel','messer','küche möbel',
          'stove','fridge','plate','spoon','fork','knife','kitchen'],                set: 'kitchen'     },
  // Level 4 — Nature
  { kw: ['baum','blume','biene','schmetterling','garten','regenwurm','hase garten',
          'tree','flower','bee','butterfly','garden'],                               set: 'garden'      },
  { kw: ['sonne','regen','schnee','wind','wolke','gewitter','wetter heute','wie ist das wetter',
          'sun','rain','snow','wind','cloud','storm','weather'],                     set: 'weather'     },
  // Level 6 — World
  { kw: ['auto','bus','zug','fahrrad','flugzeug','schiff','motorrad','lkw','verkehr',
          'car','train','bicycle','airplane','ship','transport','vehicle'],          set: 'transport'   },
  // Level 7 — Society
  { kw: ['t-shirt','hose','schuhe','socken','jacke','hut','kleid','schal','kleidung',
          'shirt','pants','shoes','socks','jacket','hat','dress','clothes'],         set: 'clothes'     },
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
  titleEl.textContent = vs.title;
  // Apply type-specific grid layout
  cardsEl.className = '';
  if (vs.type === 'phrase')  cardsEl.classList.add('phrase-grid');
  if (vs.type === 'number')  cardsEl.classList.add('number-grid');
  if (vs.type === 'abc')     cardsEl.classList.add('abc-grid');
  cardsEl.innerHTML = '';
  vs.items.forEach((item, i) => {
    const card = document.createElement('div');
    card.className = 'vocab-card';
    card.style.animationDelay = `${i * 110}ms`;
    card.dataset.de = item.de;

    // Visual: big emoji, color swatch, or large digit/letter
    const visual = vs.type === 'color'
      ? `<div class="vc-swatch" style="background:${item.color}"></div>`
      : vs.type === 'number'
      ? `<div class="vc-num">${item.emoji}</div>`
      : vs.type === 'abc'
      ? `<div class="vc-letter">${item.emoji}</div>`
      : `<div class="vc-emoji">${item.emoji}</div>`;

    // Article rendered as colored inline span; none shown if article is empty
    const artHtml = item.article
      ? `<span class="art ${item.article}">${item.article}</span> `
      : '';

    // German only — no English translation (emoji/swatch provides the visual cue)
    card.innerHTML = `${visual}<div class="vc-de">${artHtml}${item.de}</div>`;

    // Tap to answer — sends German word as kid's spoken response
    card.addEventListener('click', () => {
      document.querySelectorAll('.vocab-card').forEach(c => c.classList.remove('selected'));
      card.classList.add('selected');
      if (room.state === 'connected') {
        room.localParticipant.sendText(item.de, { topic: 'lk.chat' })
          .then(() => addMessage('Du', item.de, 'user'))
          .catch(err => console.warn('Card answer send failed:', err));
      }
    });
    cardsEl.appendChild(card);
  });
  panel.classList.remove('hidden');
}

// Highlight cards whose German word appears in the agent's current speech
function highlightVocabCards(text) {
  if (!_currentVocabSet) return;
  const lower = text.toLowerCase();
  document.querySelectorAll('.vocab-card').forEach(card => {
    const de = (card.dataset.de || '').toLowerCase();
    if (de && lower.includes(de)) {
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

function addMessage(who, text, kind = "system") {
  const div = document.createElement("div");
  div.className = `msg ${kind}`;
  if (kind === "system") {
    div.textContent = text;
  } else {
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

room.on(RoomEvent.TranscriptionReceived, (segments, participant) => {
  const kind = participant?.isLocal ? "user" : "agent";
  const who  = participant?.isLocal ? "Du" : "Teddy";

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
      const msg = SECTION_MESSAGES[key];
      if (msg) {
        // Small delay so Teddy's greeting fires first
        setTimeout(() => {
          room.localParticipant.sendText(msg, { topic: 'lk.chat' })
            .then(() => addMessage('Du', msg, 'user'))
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
    addMessage("You", text, "user");
  } catch (err) {
    addMessage("", `Send failed: ${err.message}`, "system");
  }
});
