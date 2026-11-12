/**
 * The top bar (ON-65): which page this is, and who is looking at it.
 */
import { ROLE_LABELS } from '../session/roles'
import { useSession } from '../session/SessionContext'
import './TopBar.css'

export default function TopBar({ title }: { title: string }) {
  const { session } = useSession()

  return (
    <header className="topbar">
      <h1 className="topbar__title">{title}</h1>
      {session !== null && (
        <p className="topbar__chip">
          {/* The chip reads as a bare "HR administrator" otherwise, which
              is a fact with no subject. */}
          <span className="visually-hidden">Signed in as </span>
          {ROLE_LABELS[session.role]}
        </p>
      )}
    </header>
  )
}
