/**
 * The route table (ON-65).
 *
 * The rail is derived from this, so these assertions are about what each
 * role can see *and* what they can reach. The epic fixes both lists:
 * Employee gets Chat; HR administrator gets Documents, HR Inbox, Chat.
 */
import { describe, expect, it } from 'vitest'

import { ROLES } from '../session/roles'
import {
  DEFAULT_PATH,
  QUICK_ACTIONS,
  ROUTES,
  mayOpen,
  navigationFor,
  routeFor,
} from './navigation'

describe('navigation', () => {
  it('gives an Employee the chat page and nothing else', () => {
    expect(navigationFor('employee').map((route) => route.title)).toEqual(['Chat'])
  })

  it('gives an HR administrator documents, the inbox and chat, in that order', () => {
    expect(navigationFor('hr_administrator').map((route) => route.title)).toEqual([
      'Documents',
      'HR Inbox',
      'Chat',
    ])
  })

  it('keeps the HR pages away from an Employee', () => {
    for (const path of ['/documents', '/inbox']) {
      const route = routeFor(path)
      expect(route, `${path} is not in the route table`).toBeDefined()
      expect(mayOpen(route!, 'employee')).toBe(false)
      expect(mayOpen(route!, 'hr_administrator')).toBe(true)
    }
  })

  it('lets both roles into chat, which is the primary surface', () => {
    const chat = routeFor('/chat')!

    for (const role of ROLES) {
      expect(mayOpen(chat, role)).toBe(true)
    }
  })

  it('lands everybody on a page they are allowed to open', () => {
    const landing = routeFor(DEFAULT_PATH)

    expect(landing, 'the default path is not a route').toBeDefined()
    for (const role of ROLES) {
      expect(mayOpen(landing!, role), `${role} cannot open the default path`).toBe(true)
    }
  })

  it('gives every role a quick action that goes somewhere they may go', () => {
    for (const role of ROLES) {
      const action = QUICK_ACTIONS[role]
      const route = routeFor(action.path)

      expect(route, `${action.path} is not a route`).toBeDefined()
      expect(mayOpen(route!, role), `${role} cannot open their own quick action`).toBe(
        true,
      )
    }
  })

  it('describes every route fully', () => {
    // A route with no icon or no accent renders a hole in the rail; one
    // with no ticket leaves a placeholder page that cannot say who owns it.
    for (const route of ROUTES) {
      expect(route.path, 'a route has no path').toMatch(/^\//)
      expect(route.title.length, `${route.path} has no title`).toBeGreaterThan(0)
      expect(route.roles.length, `${route.path} is open to nobody`).toBeGreaterThan(0)
      expect(route.ticket, `${route.path} names no ticket`).toMatch(/^ON-\d+$/)
      expect(typeof route.icon, `${route.path} has no icon`).not.toBe('undefined')
    }
  })

  it('lists each path once', () => {
    const paths = ROUTES.map((route) => route.path)

    expect(paths).toHaveLength(new Set(paths).size)
  })
})
