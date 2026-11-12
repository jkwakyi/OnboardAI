/**
 * An address that is not a route (ON-65).
 *
 * Inside the shell, so the navigation is right there rather than leaving
 * someone on a dead page with the back button.
 */
import { useNavigate } from 'react-router'

import { Button, EmptyState } from '../components'
import { SearchX } from '../components/icons'
import { DEFAULT_PATH } from './navigation'

export default function NotFound() {
  const navigate = useNavigate()

  return (
    <EmptyState
      action={<Button onClick={() => navigate(DEFAULT_PATH)}>Go to chat</Button>}
      description="The address does not match any page in OnboardAI."
      icon={<SearchX />}
      title="Page not found"
    />
  )
}
