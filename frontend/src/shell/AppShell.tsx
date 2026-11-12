/**
 * The application shell (ON-65).
 *
 * Every signed-in page renders inside this: the rail, the top bar, and a
 * content area that scrolls on its own so the navigation stays put. The
 * login page renders outside it.
 *
 * The shell holds no page logic. The only thing it knows about the page
 * is its title, which it reads out of the route table rather than being
 * told - otherwise every page would have to remember to set it, and the
 * one that forgot would show the previous page's.
 */
import { Outlet, useLocation } from 'react-router'

import NavRail from './NavRail'
import TopBar from './TopBar'
import { routeFor } from './navigation'
import './AppShell.css'

export const CONTENT_ID = 'main-content'

export default function AppShell() {
  const location = useLocation()
  const route = routeFor(location.pathname)

  return (
    <div className="shell">
      {/*
        First thing in the tab order, hidden until it has focus. Without it
        a keyboard user tabs through the whole rail on every page before
        reaching anything they came for.
      */}
      <a className="shell__skip" href={`#${CONTENT_ID}`}>
        Skip to content
      </a>

      <NavRail />

      <div className="shell__body">
        <TopBar title={route?.title ?? 'OnboardAI'} />
        {/*
          tabIndex -1 so the skip link can actually move focus here. A
          plain anchor to a non-focusable target scrolls the page and
          leaves the keyboard where it was, which is the usual reason a
          skip link appears to do nothing.
        */}
        <main className="shell__content" id={CONTENT_ID} tabIndex={-1}>
          <Outlet />
        </main>
      </div>
    </div>
  )
}
