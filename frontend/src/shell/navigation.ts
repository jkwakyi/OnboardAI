/**
 * The route table, and the navigation derived from it (ON-65).
 *
 * One list. The rail is `ROUTES` filtered by role rather than a second
 * list written beside it, because two lists drift: a page gets added to
 * the router and not to the navigation, or worse, removed from the
 * navigation and left reachable by typing the URL.
 *
 * Order here is the order in the rail, so HR sees Documents, HR Inbox,
 * Chat, and an Employee sees the one route they have.
 */
import type { Accent } from '../components'
import { FileText, Inbox, MessageSquare, type LucideIcon } from '../components/icons'
import type { Role } from '../session/roles'

export interface RouteDefinition {
  path: string
  /** Shown in the rail and in the top bar. */
  title: string
  /** Who may open it. Anyone else gets the not-authorized view. */
  roles: readonly Role[]
  accent: Accent
  icon: LucideIcon
  /** The ticket that builds the page. Shown until it does. */
  ticket: string
}

export const ROUTES: readonly RouteDefinition[] = [
  {
    path: '/documents',
    title: 'Documents',
    roles: ['hr_administrator'],
    accent: 'documents',
    icon: FileText,
    ticket: 'ON-42',
  },
  {
    path: '/inbox',
    title: 'HR Inbox',
    roles: ['hr_administrator'],
    accent: 'escalations',
    icon: Inbox,
    ticket: 'ON-21',
  },
  {
    path: '/chat',
    title: 'Chat',
    roles: ['employee', 'hr_administrator'],
    accent: 'chat',
    icon: MessageSquare,
    ticket: 'ON-48',
  },
]

/** Where the login page lives. Outside the shell: it has no navigation. */
export const LOGIN_PATH = '/login'

/**
 * Where a signed-in person lands.
 *
 * Chat for both roles: the epic calls it the primary surface and names it
 * as the employee's default, and an HR administrator can ask questions
 * too - the rail gives them Chat as well.
 */
export const DEFAULT_PATH = '/chat'

export interface QuickAction {
  label: string
  path: string
  accent: Accent
}

export const QUICK_ACTIONS: Record<Role, QuickAction> = {
  employee: { label: 'Ask a question', path: '/chat', accent: 'chat' },
  hr_administrator: {
    label: 'Upload a document',
    path: '/documents',
    accent: 'documents',
  },
}

/** The routes this role may open, in rail order. */
export function navigationFor(role: Role): RouteDefinition[] {
  return ROUTES.filter((route) => route.roles.includes(role))
}

export function routeFor(path: string): RouteDefinition | undefined {
  return ROUTES.find((route) => route.path === path)
}

export function mayOpen(route: RouteDefinition, role: Role): boolean {
  return route.roles.includes(role)
}
