/**
 * ErrorState (ON-64).
 *
 * What a page shows when a request failed. Always with a retry: a dead end
 * that offers nothing leaves a reload as the only way out, and a reload
 * loses whatever the user had typed.
 *
 * The description is where the error shape from the Interface Contracts
 * gets turned into a sentence. A raw status code is not one.
 */
import EmptyState from './EmptyState'
import Button from './Button'
import { RefreshCw, TriangleAlert } from './icons'

export interface ErrorStateProps {
  title?: string
  description?: string
  retryLabel?: string
  onRetry: () => void
  className?: string
}

export default function ErrorState({
  title = 'Something went wrong',
  description = 'The request did not get through. Nothing was changed.',
  retryLabel = 'Try again',
  onRetry,
  className,
}: ErrorStateProps) {
  return (
    <EmptyState
      className={className}
      tone="danger"
      icon={<TriangleAlert />}
      title={title}
      description={description}
      action={
        <Button variant="secondary" icon={<RefreshCw />} onClick={onRetry}>
          {retryLabel}
        </Button>
      }
    />
  )
}
