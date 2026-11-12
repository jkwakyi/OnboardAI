/**
 * The kitchen sink: every shared component, in every state (ON-64).
 *
 * Development only, at `#components`, and dropped from the production
 * bundle the same way the token gallery is - see `App.tsx` for the one
 * literal that does it.
 *
 * It exists because a component library is only as good as the one place
 * you can see all of it at once. States that are hard to reach in the real
 * app - a button mid-request, a dropzone rejecting a file, an error with a
 * retry - are all one scroll away here, which is what makes "every
 * component shows all its states" something anyone can check rather than
 * something a ticket asserts.
 */
import type { ReactNode } from 'react'
import { useState } from 'react'

import {
  ACCENTS,
  Button,
  Card,
  CitationChip,
  EmptyState,
  ErrorState,
  FileDropzone,
  FormField,
  ProgressRing,
  QuickAction,
  Skeleton,
  StatTile,
  StatusPill,
  Toast,
  type ButtonVariant,
  type StatusVariant,
} from '../components'
import { FileText, MessageSquare, Plus, Upload } from '../components/icons'
// As a string, not as a side effect: see TokenGallery.tsx. A plain CSS
// import survives tree-shaking and would ship this page's styles.
import galleryStyles from './ComponentGallery.css?inline'

const BUTTON_VARIANTS: ButtonVariant[] = ['primary', 'secondary', 'ghost', 'danger']
const STATUS_VARIANTS: StatusVariant[] = ['success', 'warning', 'danger', 'neutral']

function Sink({
  title,
  note,
  children,
}: {
  title: string
  note: string
  children: ReactNode
}) {
  return (
    <section className="sink-section">
      <h2 className="sink-heading">{title}</h2>
      <p className="sink-note">{note}</p>
      <div className="sink-row">{children}</div>
    </section>
  )
}

export default function ComponentGallery() {
  const [dropped, setDropped] = useState<string>('nothing yet')
  const [pressed, setPressed] = useState(0)

  return (
    <main className="sink">
      <style>{galleryStyles}</style>

      <header>
        <h1>Shared components</h1>
        <p className="sink-note">
          Every component from ON-64, in every state it has. Development only:
          this page is not in the alpha build. The design tokens behind it are
          at <code>#tokens</code>.
        </p>
      </header>

      <Sink title="Button" note="Four variants, two sizes, and the states each one has.">
        {BUTTON_VARIANTS.map((variant) => (
          <div className="sink-stack" key={variant}>
            <Button variant={variant} onClick={() => setPressed((count) => count + 1)}>
              {variant}
            </Button>
            <Button variant={variant} size="sm">
              {variant} sm
            </Button>
            <Button variant={variant} icon={<Plus />}>
              with icon
            </Button>
            <Button variant={variant} loading>
              loading
            </Button>
            <Button variant={variant} disabled>
              disabled
            </Button>
            <Button variant={variant} icon={<Plus />} aria-label={`Add, ${variant}`} />
          </div>
        ))}
      </Sink>

      <Sink title="Button presses" note="Proof the handlers are wired, not just drawn.">
        <p>
          Pressed <strong>{pressed}</strong> times.
        </p>
      </Sink>

      <Sink title="QuickAction" note="The left-rail button, one per accent.">
        <div className="sink-rail">
          <QuickAction label="Ask a question" accent="chat" />
          <QuickAction label="Upload a document" accent="documents" />
          <QuickAction label="Send to HR" accent="escalations" />
          <QuickAction label="Disabled" disabled />
        </div>
      </Sink>

      <Sink title="Card" note="With and without a label, an action, and each accent.">
        <Card>Plain card, no label.</Card>
        <Card label="No accent">A labelled section.</Card>
        {ACCENTS.map((accent) => (
          <Card
            accent={accent}
            action={<StatusPill variant="neutral">{accent}</StatusPill>}
            key={accent}
            label={`${accent} accent`}
          >
            The rule along the top says which area this belongs to.
          </Card>
        ))}
      </Sink>

      <Sink title="StatusPill" note="Colour is the second signal; the text is the first.">
        {STATUS_VARIANTS.map((variant) => (
          <StatusPill key={variant} variant={variant}>
            {variant}
          </StatusPill>
        ))}
      </Sink>

      <Sink title="ProgressRing" note="0, part-way, full, and a value out of range.">
        {[0, 33, 72, 100, 140].map((value) => (
          <ProgressRing key={value} label={`Example ${value}`} value={value} />
        ))}
        {ACCENTS.map((accent) => (
          <ProgressRing accent={accent} key={accent} label={accent} value={62} />
        ))}
      </Sink>

      <Sink title="StatTile" note="With a caption, with a ring, and with both.">
        <StatTile accent="documents" label="Documents" value={12} />
        <StatTile
          accent="documents"
          caption="2 added this week"
          label="Documents"
          value={12}
        />
        <StatTile accent="chat" label="Answered" percent={81} value="81%" />
        <StatTile
          accent="escalations"
          caption="3 waiting on HR"
          label="Escalations"
          percent={30}
          value={3}
        />
      </Sink>

      <Sink title="FormField" note="Every control, with helper text and with an error.">
        <div className="sink-stack sink-stack--wide">
          <FormField label="Work email" placeholder="you@example.com" type="email" />
          <FormField helper="At least 12 characters." label="Password" type="password" />
          <FormField error="That password is too short." label="Password" type="password" />
          <FormField
            error="Pick one of the two."
            helper="Both are wired to the control."
            label="Error and helper together"
          />
          <FormField as="select" label="Escalation status">
            <option>Open</option>
            <option>Answered</option>
          </FormField>
          <FormField as="textarea" label="Question" rows={3} />
          <FormField disabled label="Disabled" value="Read only" />
        </div>
      </Sink>

      <Sink title="FileDropzone" note="Drop a file, or choose one. Try a .docx to see it refuse.">
        <div className="sink-stack sink-stack--wide">
          <FileDropzone
            onError={(message) => setDropped(message)}
            onFileSelected={(file) => setDropped(`accepted ${file.name}`)}
          />
          <p className="sink-note">
            Last result: <code>{dropped}</code>
          </p>
          <FileDropzone disabled onFileSelected={() => undefined} />
        </div>
      </Sink>

      <Sink title="CitationChip" note="Focusable, so Tab reaches every source under an answer.">
        <CitationChip location="Section 4.2" title="Employee Handbook" />
        <CitationChip location="Page 7" title="Leave and Time Off Policy" />
        <CitationChip
          location="Section 1"
          title="A document with a very long title that has to be cut off somewhere"
        />
      </Sink>

      <Sink title="Toast" note="Polite for a confirmation, interrupting for a failure.">
        <div className="sink-stack sink-stack--wide">
          <Toast>A plain message.</Toast>
          <Toast title="Uploaded" variant="success">
            handbook.pdf is being processed.
          </Toast>
          <Toast title="Could not send" variant="danger">
            The escalation was not sent. Nothing was changed.
          </Toast>
          <Toast onDismiss={() => undefined} variant="info">
            With a close button.
          </Toast>
        </div>
      </Sink>

      <Sink title="EmptyState" note="A title, a reason, and the action that would fill it.">
        <EmptyState title="Nothing here yet" />
        <EmptyState
          action={<Button icon={<Upload />}>Upload a document</Button>}
          description="Upload a PDF or TXT file and employees can ask about it."
          icon={<FileText />}
          title="No documents yet"
        />
        <EmptyState
          description="Ask something in the chat and the answer appears here."
          icon={<MessageSquare />}
          title="No questions asked yet"
        />
      </Sink>

      <Sink title="ErrorState" note="Always with a retry: a reload loses what was typed.">
        <ErrorState onRetry={() => undefined} />
        <ErrorState
          description="The escalation was not sent."
          onRetry={() => undefined}
          retryLabel="Send again"
          title="Could not reach the HR Inbox"
        />
      </Sink>

      <Sink title="Skeleton" note="Text bars and a block, so the page does not jump.">
        <div className="sink-stack sink-stack--wide">
          <Skeleton />
          <Skeleton label="Loading documents" lines={5} />
          <Skeleton variant="block" />
        </div>
      </Sink>
    </main>
  )
}
