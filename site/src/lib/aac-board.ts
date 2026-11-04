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
  icon: LucideIcon
}

export interface BoardCategory {
  id: string
  label: string
  icon: LucideIcon
  tiles: BoardTile[]
}

/** Communication board (AAC, Phase 9): categories of common words and phrases. */
export const BOARD: BoardCategory[] = [
  {
    id: 'needs',
    label: 'Needs',
    icon: Droplet,
    tiles: [
      { text: 'I need water', icon: Droplet },
      { text: "I'm hungry", icon: Apple },
      { text: 'I need the toilet', icon: Bath },
      { text: 'I need my medicine', icon: Pill },
      { text: 'I want to rest', icon: Bed },
      { text: "I'm cold", icon: Snowflake },
      { text: "I'm hot", icon: Thermometer },
      { text: 'Please help me move', icon: Hand },
      { text: 'I need help', icon: HeartPulse },
    ],
  },
  {
    id: 'feelings',
    label: 'Feelings',
    icon: Smile,
    tiles: [
      { text: "I'm happy", icon: Smile },
      { text: "I'm sad", icon: Frown },
      { text: "I'm in pain", icon: Zap },
      { text: "I'm tired", icon: Moon },
      { text: "I'm scared", icon: CircleHelp },
      { text: "I'm okay", icon: ThumbsUp },
      { text: "I'm bored", icon: Meh },
      { text: 'I feel sick', icon: Thermometer },
    ],
  },
  {
    id: 'people',
    label: 'People',
    icon: UsersRound,
    tiles: [
      { text: 'Please call my caregiver', icon: Phone },
      { text: 'I want to see my family', icon: UsersRound },
      { text: 'Please call a doctor', icon: Stethoscope },
      { text: 'Please call a nurse', icon: HeartPulse },
      { text: 'I want to talk to someone', icon: MessageCircle },
    ],
  },
  {
    id: 'answers',
    label: 'Answers',
    icon: CircleCheck,
    tiles: [
      { text: 'Yes', icon: CircleCheck },
      { text: 'No', icon: CircleX },
      { text: 'Maybe', icon: CircleHelp },
      { text: 'Wait, please', icon: Hourglass },
      { text: "I don't know", icon: Meh },
      { text: 'Please say that again', icon: Repeat },
      { text: 'Stop', icon: Octagon },
    ],
  },
  {
    id: 'greetings',
    label: 'Greetings',
    icon: Hand,
    tiles: [
      { text: 'Hello', icon: Hand },
      { text: 'Good morning', icon: Sun },
      { text: 'Good night', icon: Moon },
      { text: 'Thank you', icon: Heart },
      { text: "I'm sorry", icon: Frown },
      { text: 'Goodbye', icon: Hand },
      { text: 'I love you', icon: Heart },
    ],
  },
]
