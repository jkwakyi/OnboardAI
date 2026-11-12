/**
 * FormField (ON-64).
 *
 * The `aria-describedby` wiring is the reason this component exists, so it
 * is what most of these check. Helper and error text look correct on screen
 * whether or not they are attached to the control, which is exactly why it
 * gets forgotten.
 */
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'

import FormField from './FormField'

/** The elements a control's aria-describedby points at, in order. */
function descriptions(control: HTMLElement): string[] {
  const ids = control.getAttribute('aria-describedby')?.split(' ') ?? []
  return ids.map((id) => document.getElementById(id)?.textContent ?? `#${id} is missing`)
}

describe('FormField', () => {
  it('labels its control', () => {
    render(<FormField label="Email address" />)

    expect(screen.getByLabelText('Email address')).toBeInstanceOf(HTMLInputElement)
  })

  it('accepts typing', async () => {
    render(<FormField label="Question" />)

    const input = screen.getByLabelText('Question')
    await userEvent.type(input, 'How much leave do I get?')

    expect(input).toHaveValue('How much leave do I get?')
  })

  it('describes the control with its helper text', () => {
    render(<FormField label="Password" helper="At least 12 characters." />)

    expect(descriptions(screen.getByLabelText('Password'))).toEqual([
      'At least 12 characters.',
    ])
  })

  it('describes the control with its error, and marks it invalid', () => {
    render(<FormField label="Password" error="That password is too short." />)

    const input = screen.getByLabelText('Password')
    expect(input).toHaveAttribute('aria-invalid', 'true')
    expect(descriptions(input)).toEqual(['That password is too short.'])
  })

  it('puts the error before the helper text', () => {
    // Someone who tabs back into a rejected field wants to hear what is
    // wrong before hearing the format rules a second time.
    render(
      <FormField label="Password" helper="At least 12 characters." error="Too short." />,
    )

    expect(descriptions(screen.getByLabelText('Password'))).toEqual([
      'Too short.',
      'At least 12 characters.',
    ])
  })

  it('announces an error that appears after the fact', () => {
    render(<FormField label="Password" error="Too short." />)

    expect(screen.getByRole('alert')).toHaveTextContent('Too short.')
  })

  it('describes nothing when there is nothing to say', () => {
    render(<FormField label="Email address" />)

    const input = screen.getByLabelText('Email address')
    expect(input).not.toHaveAttribute('aria-describedby')
    expect(input).not.toHaveAttribute('aria-invalid')
  })

  it('gives each field its own ids', () => {
    // Two fields on a page sharing a helper id is a wiring bug that only
    // shows up with a screen reader on the second one.
    render(
      <>
        <FormField label="First" helper="One" />
        <FormField label="Second" helper="Two" />
      </>,
    )

    expect(descriptions(screen.getByLabelText('First'))).toEqual(['One'])
    expect(descriptions(screen.getByLabelText('Second'))).toEqual(['Two'])
  })

  it('renders a select with its options', async () => {
    const onChange = vi.fn()
    render(
      <FormField as="select" label="Status" onChange={onChange}>
        <option value="open">Open</option>
        <option value="answered">Answered</option>
      </FormField>,
    )

    const select = screen.getByLabelText('Status')
    expect(select).toBeInstanceOf(HTMLSelectElement)

    await userEvent.selectOptions(select, 'answered')
    expect(select).toHaveValue('answered')
    expect(onChange).toHaveBeenCalled()
  })

  it('renders a textarea', () => {
    render(<FormField as="textarea" label="Question" rows={4} />)

    const textarea = screen.getByLabelText('Question')
    expect(textarea).toBeInstanceOf(HTMLTextAreaElement)
    expect(textarea).toHaveAttribute('rows', '4')
  })

  it('can be disabled', async () => {
    render(<FormField label="Email address" disabled />)

    const input = screen.getByLabelText('Email address')
    expect(input).toBeDisabled()

    await userEvent.type(input, 'hello')
    expect(input).toHaveValue('')
  })

  it('uses a caller-supplied id, so a form can point at the field', () => {
    render(<FormField label="Email address" id="login-email" helper="Work address." />)

    const input = screen.getByLabelText('Email address')
    expect(input).toHaveAttribute('id', 'login-email')
    expect(input).toHaveAttribute('aria-describedby', 'login-email-helper')
  })
})
