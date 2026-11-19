import {
  Apple,
  Bath,
  Bed,
  CircleCheck,
  CircleHelp,
  CircleX,
  Droplet,
  Frown,
  Hand,
  Heart,
  HeartPulse,
  Hourglass,
  Meh,
  MessageCircle,
  Moon,
  Octagon,
  Phone,
  Pill,
  Repeat,
  Smile,
  Snowflake,
  Stethoscope,
  Sun,
  Thermometer,
  ThumbsUp,
  UsersRound,
  Zap,
  type LucideIcon,
} from 'lucide-react'

export interface BoardTile {
  text: string
  /** The same phrase in Filipino (shown and spoken when FILIPINO is chosen). */
  fil: string
  icon: LucideIcon
}

export interface BoardCategory {
  id: string
  label: string
  fil: string
  icon: LucideIcon
  tiles: BoardTile[]
}

/** Communication board (AAC, Phase 9): categories of common words and phrases. */
export const BOARD: BoardCategory[] = [
  {
    id: 'needs',
    label: 'Needs',
    fil: 'Mga Kailangan',
    icon: Droplet,
    tiles: [
      { text: 'I need water', fil: 'Kailangan ko ng tubig', icon: Droplet },
      { text: "I'm hungry", fil: 'Gutom na ako', icon: Apple },
      { text: 'I need the toilet', fil: 'Kailangan kong mag-CR', icon: Bath },
      { text: 'I need my medicine', fil: 'Kailangan ko ang gamot ko', icon: Pill },
      { text: 'I want to rest', fil: 'Gusto kong magpahinga', icon: Bed },
      { text: "I'm cold", fil: 'Nilalamig ako', icon: Snowflake },
      { text: "I'm hot", fil: 'Naiinitan ako', icon: Thermometer },
      { text: 'Please help me move', fil: 'Pakitulungan akong gumalaw', icon: Hand },
      { text: 'I need help', fil: 'Tulungan mo ako', icon: HeartPulse },
    ],
  },
  {
    id: 'feelings',
    label: 'Feelings',
    fil: 'Damdamin',
    icon: Smile,
    tiles: [
      { text: "I'm happy", fil: 'Masaya ako', icon: Smile },
      { text: "I'm sad", fil: 'Malungkot ako', icon: Frown },
      { text: "I'm in pain", fil: 'May masakit sa akin', icon: Zap },
      { text: "I'm tired", fil: 'Pagod na ako', icon: Moon },
      { text: "I'm scared", fil: 'Natatakot ako', icon: CircleHelp },
      { text: "I'm okay", fil: 'Okay lang ako', icon: ThumbsUp },
      { text: "I'm bored", fil: 'Naiinip ako', icon: Meh },
      { text: 'I feel sick', fil: 'Masama ang pakiramdam ko', icon: Thermometer },
    ],
  },
  {
    id: 'people',
    label: 'People',
    fil: 'Mga Tao',
    icon: UsersRound,
    tiles: [
      { text: 'Please call my caregiver', fil: 'Pakitawag ang aking tagapag-alaga', icon: Phone },
      { text: 'I want to see my family', fil: 'Gusto kong makita ang pamilya ko', icon: UsersRound },
      { text: 'Please call a doctor', fil: 'Pakitawag ang doktor', icon: Stethoscope },
      { text: 'Please call a nurse', fil: 'Pakitawag ang nars', icon: HeartPulse },
      { text: 'I want to talk to someone', fil: 'Gusto kong may makausap', icon: MessageCircle },
    ],
  },
  {
    id: 'answers',
    label: 'Answers',
    fil: 'Mga Sagot',
    icon: CircleCheck,
    tiles: [
      { text: 'Yes', fil: 'Oo', icon: CircleCheck },
      { text: 'No', fil: 'Hindi', icon: CircleX },
      { text: 'Maybe', fil: 'Siguro', icon: CircleHelp },
      { text: 'Wait, please', fil: 'Sandali lang po', icon: Hourglass },
      { text: "I don't know", fil: 'Hindi ko alam', icon: Meh },
      { text: 'Please say that again', fil: 'Pakiulit po', icon: Repeat },
      { text: 'Stop', fil: 'Tigil', icon: Octagon },
    ],
  },
  {
    id: 'greetings',
    label: 'Greetings',
    fil: 'Pagbati',
    icon: Hand,
    tiles: [
      { text: 'Hello', fil: 'Kumusta', icon: Hand },
      { text: 'Good morning', fil: 'Magandang umaga', icon: Sun },
      { text: 'Good night', fil: 'Magandang gabi', icon: Moon },
      { text: 'Thank you', fil: 'Salamat', icon: Heart },
      { text: "I'm sorry", fil: 'Patawad', icon: Frown },
      { text: 'Goodbye', fil: 'Paalam', icon: Hand },
      { text: 'I love you', fil: 'Mahal kita', icon: Heart },
    ],
  },
]
