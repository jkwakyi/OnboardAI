/**
 * FormField (ON-64).
 *
 * A label, a control, and the two kinds of text that go under one: helper
 * text that is always there, and an error that appears when something is
 * wrong. Both are wired to the control with `aria-describedby`, which is
 * the part that is easy to leave out and impossible to notice without a
 * screen reader - the text sits right there on screen either way.
 *
 * The control is a real `<input>`, `<select>` or `<textarea>`. None of them
 * is reimplemented: a native select already knows how to open on a phone,
 * and nothing here would.
 */
import type {
  InputHTMLAttributes,
  ReactElement,
  ReactNode,
  SelectHTMLAttributes,
  TextareaHTMLAttributes,
} from 'react'
import { useId } from 'react'

import { cx } from './classNames'
import './FormField.css'

interface FormFieldCommon {
  /** The visible label. Always present: a placeholder is not a label. */
  label: string
  /** Standing guidance, such as an accepted format. */
  helper?: string
  /** Shown when the value is wrong, and marks the control invalid. */
  error?: string
  className?: string
}

type InputField = FormFieldCommon & { as?: 'input' } & InputHTMLAttributes<HTMLInputElement>
type SelectField = FormFieldCommon & { as: 'select' } & SelectHTMLAttributes<HTMLSelectElement>
type TextareaField = FormFieldCommon & {
  as: 'textarea'
} & TextareaHTMLAttributes<HTMLTextAreaElement>

export type FormFieldProps = InputField | SelectField | TextareaField

interface FormFieldImplProps extends FormFieldCommon {
  as?: 'input' | 'select' | 'textarea'
  id?: string
  children?: ReactNode
}

function FormFieldImpl({
  label,
  helper,
  error,
  as = 'input',
  className,
  id,
  children,
  ...rest
}: FormFieldImplProps) {
  const generatedId = useId()
  const controlId = id ?? generatedId
  const helperId = `${controlId}-helper`
  const errorId = `${controlId}-error`
  const invalid = error !== undefined

  // The error comes first, so someone who tabs back into a field that was
  // rejected hears what is wrong before hearing the format rules again.
  const describedBy =
    cx(invalid && errorId, helper !== undefined && helperId) || undefined

  const controlProps = {
    id: controlId,
    className: 'oa-field__control',
    'aria-describedby': describedBy,
    'aria-invalid': invalid || undefined,
    ...rest,
  }

  return (
    <div className={cx('oa-field', invalid && 'oa-field--invalid', className)}>
      <label className="oa-field__label" htmlFor={controlId}>
        {label}
      </label>

      {as === 'select' ? (
        <select {...controlProps}>{children}</select>
      ) : as === 'textarea' ? (
        <textarea {...controlProps} />
      ) : (
        <input {...controlProps} />
      )}

      {helper !== undefined && (
        <p className="oa-field__helper" id={helperId}>
          {helper}
        </p>
      )}
      {invalid && (
        // role="alert" so an error that appears after submission is
        // announced, rather than waiting for the user to wander back.
        <p className="oa-field__error" id={errorId} role="alert">
          {error}
        </p>
      )}
    </div>
  )
}

/** See Button: the cast is what gives callers the per-control prop types. */
const FormField = FormFieldImpl as (props: FormFieldProps) => ReactElement

export default FormField
