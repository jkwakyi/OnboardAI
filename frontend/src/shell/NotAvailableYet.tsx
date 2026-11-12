/**
 * The placeholder a route shows until its page is built (ON-65).
 *
 * The shell routes everything the epic names, including the pages that do
 * not exist yet, so the navigation is the real navigation from the start
 * rather than a set of links that go nowhere. What a route renders in the
 * meantime says which ticket builds it, because "coming soon" tells a
 * teammate nothing they can act on.
 */
import { EmptyState } from '../components'
import type { RouteDefinition } from './navigation'

export default function NotAvailableYet({ route }: { route: RouteDefinition }) {
  return (
    <EmptyState
      description={`The ${route.title.toLowerCase()} page is built in ${route.ticket}. The navigation, the layout and the guards around it are already here.`}
      icon={<route.icon />}
      title={`${route.title} is not available yet`}
    />
  )
}
