import { FileText, LayoutDashboard, ScrollText, Settings, Users } from 'lucide-react'
import type { ReactNode } from 'react'
import { NavLink } from 'react-router'
import { SignOutButton } from '@/components/sign-out-button'
import { cn } from '@/lib/utils'
import { useSessionStore } from '@/store/session-store'

const LINKS = [
  { to: '/admin', label: 'Dashboard', icon: LayoutDashboard, end: true },
  { to: '/admin/users', label: 'Users', icon: Users, end: false },
  { to: '/admin/settings', label: 'Settings', icon: Settings, end: false },
  { to: '/admin/logs', label: 'Logs', icon: ScrollText, end: false },
  { to: '/admin/reports', label: 'Reports', icon: FileText, end: false },
]

interface AdminLayoutProps {
  title: string
  description?: string
  actions?: ReactNode
  children: ReactNode
}

/** Admin pages: menu, page title and sign-out (mouse and keyboard use, normal sizes). */
export function AdminLayout({ title, description, actions, children }: AdminLayoutProps) {
  const admin = useSessionStore((s) => s.user)
  return (
    <div className="bg-background text-foreground min-h-svh">
      <header className="bg-card border-b">
        <div className="mx-auto flex max-w-6xl flex-wrap items-center justify-between gap-4 px-6 py-3">
          <nav aria-label="Admin" className="flex flex-wrap gap-1">
            {LINKS.map(({ to, label, icon: Icon, end }) => (
              <NavLink
                key={to}
                to={to}
                end={end}
                className={({ isActive }) =>
                  cn(
                    'flex items-center gap-2 rounded-lg px-3 py-2 text-sm font-medium transition-colors',
                    isActive ? 'bg-primary text-primary-foreground' : 'hover:bg-muted',
                  )
                }
              >
                <Icon className="size-4" aria-hidden />
                {label}
              </NavLink>
            ))}
          </nav>
          <div className="flex items-center gap-4">
            <span className="text-muted-foreground text-sm">{admin?.full_name}</span>
            <SignOutButton />
          </div>
        </div>
      </header>
      <main className="mx-auto flex max-w-6xl flex-col gap-6 p-6">
        <div className="flex flex-wrap items-end justify-between gap-4">
          <div>
            <h1 className="text-3xl font-bold">{title}</h1>
            {description && <p className="text-muted-foreground mt-1">{description}</p>}
          </div>
          {actions}
        </div>
        {children}
      </main>
    </div>
  )
}
