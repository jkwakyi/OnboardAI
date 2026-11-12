/**
 * The left rail (ON-65).
 *
 * The app name as plain text, one quick action, the routes this role may
 * open, and who is signed in with a way out at the bottom.
 *
 * The links are `NavLink`s, which set `aria-current="page"` on the active
 * one for us. That is the part a hand-rolled highlight usually misses: a
 * colour change says "you are here" to someone looking at it and nothing
 * at all to someone listening to it.
 */
import { NavLink, useNavigate } from 'react-router'

import { Button, QuickAction, accentClass, cx } from '../components'
import { LogOut, UserRound } from '../components/icons'
import { ROLE_LABELS } from '../session/roles'
import { useSession } from '../session/SessionContext'
import { LOGIN_PATH, QUICK_ACTIONS, navigationFor } from './navigation'
import './NavRail.css'

export default function NavRail() {
  const { session, signOut } = useSession()
  const navigate = useNavigate()

  if (session === null) {
    // The rail only renders inside the shell, which only renders for a
    // signed-in user. Belt and braces: nothing here would make sense.
    return null
  }

  const routes = navigationFor(session.role)
  const quickAction = QUICK_ACTIONS[session.role]

  return (
    <div className="rail">
      {/* Plain text, no mark. The epic rules out product branding. */}
      <p className="rail__name">OnboardAI</p>

      <section aria-labelledby="rail-quick" className="rail__group">
        <h2 className="section-label rail__group-title" id="rail-quick">
          Quick actions
        </h2>
        <QuickAction
          accent={quickAction.accent}
          label={quickAction.label}
          onClick={() => navigate(quickAction.path)}
        />
      </section>

      <nav aria-labelledby="rail-nav" className="rail__group">
        <h2 className="section-label rail__group-title" id="rail-nav">
          Navigation
        </h2>
        <ul className="rail__links" role="list">
          {routes.map((route) => (
            <li key={route.path}>
              <NavLink
                className={({ isActive }) =>
                  cx('rail__link', accentClass(route.accent), isActive && 'rail__link--active')
                }
                to={route.path}
              >
                <route.icon aria-hidden="true" className="rail__icon" />
                {route.title}
              </NavLink>
            </li>
          ))}
        </ul>
      </nav>

      <div className="rail__user">
        <UserRound aria-hidden="true" className="rail__avatar" />
        <div className="rail__who">
          <p className="rail__full-name">{session.fullName}</p>
          <p className="rail__role">{ROLE_LABELS[session.role]}</p>
        </div>
        <Button
          aria-label="Sign out"
          icon={<LogOut />}
          onClick={() => {
            signOut()
            navigate(LOGIN_PATH, { replace: true })
          }}
          size="sm"
          variant="ghost"
        />
      </div>
    </div>
  )
}
