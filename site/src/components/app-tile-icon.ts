import {
  AppWindow, Calculator, CalendarDays, FileSpreadsheet, FileText, Globe, Mail, MessageCircle, Presentation, Search,
  Users, Video, type LucideIcon,
} from 'lucide-react'

/** Icon keys stored with each tile; the six defaults match the Phase 9 tiles. */
const ICONS: Record<string, LucideIcon> = {
  browser: Globe, calculator: Calculator, calendar: CalendarDays,
  word: FileText, excel: FileSpreadsheet, powerpoint: Presentation,
  app: AppWindow, globe: Globe, video: Video, users: Users, mail: Mail, search: Search, message: MessageCircle,
}

export const tileIcon = (key: string): LucideIcon => ICONS[key] ?? AppWindow
