/**
 * FileDropzone (ON-64), used by the admin upload page (ON-42).
 *
 * Drag a file onto it, or click it to browse. Only PDF and TXT, and not an
 * empty file.
 *
 * It is a `<label>` wrapped around a real `<input type="file">`. The input
 * is hidden from view but not from the accessibility tree or the tab order,
 * so the whole thing is keyboard-operable and announces itself as a file
 * input without a single key handler of our own. The usual alternative - a
 * div with `onClick` and `onKeyDown` - has to reimplement all of that and
 * normally reimplements half.
 *
 * The check here is a courtesy to the person uploading, not a security
 * control. The server validates the file again; a check that runs in the
 * browser is a check the browser can be told to skip.
 */
import type { ChangeEvent, DragEvent } from 'react'
import { useId, useRef, useState } from 'react'

import { cx } from './classNames'
import { FileUp } from './icons'
import './FileDropzone.css'

/** What the Document Upload service accepts. */
export const ACCEPTED_EXTENSIONS = ['.pdf', '.txt']

const ACCEPT_ATTRIBUTE = '.pdf,.txt,application/pdf,text/plain'

export const WRONG_TYPE_MESSAGE = 'Only PDF and TXT documents can be uploaded.'
export const EMPTY_FILE_MESSAGE = 'That file is empty, so there is nothing to read from it.'

/** A size a person can read, rather than a count of bytes. */
export function formatFileSize(bytes: number): string {
  if (bytes < 1024) {
    return `${bytes} B`
  }

  const units = ['KB', 'MB', 'GB']
  let value = bytes / 1024
  let unit = 0
  while (value >= 1024 && unit < units.length - 1) {
    value /= 1024
    unit += 1
  }
  return `${value.toFixed(1)} ${units[unit]}`
}

/** The reason to reject the file, or null when there is none. */
export function validateFile(file: File): string | null {
  const name = file.name.toLowerCase()
  if (!ACCEPTED_EXTENSIONS.some((extension) => name.endsWith(extension))) {
    return WRONG_TYPE_MESSAGE
  }
  if (file.size === 0) {
    return EMPTY_FILE_MESSAGE
  }
  return null
}

export interface FileDropzoneProps {
  /** Called with a file that passed validation. */
  onFileSelected: (file: File) => void
  /** Called with the message shown to the user when one did not. */
  onError?: (message: string) => void
  disabled?: boolean
  className?: string
}

export default function FileDropzone({
  onFileSelected,
  onError,
  disabled = false,
  className,
}: FileDropzoneProps) {
  const inputId = useId()
  const errorId = `${inputId}-error`
  const [dragging, setDragging] = useState(false)
  const [file, setFile] = useState<File | null>(null)
  const [error, setError] = useState<string | null>(null)

  /**
   * Dragging over a child fires dragleave on the parent. Counting entries
   * and leaves is what stops the highlight flickering off every time the
   * pointer crosses the icon.
   */
  const depth = useRef(0)

  function accept(candidate: File | undefined): void {
    if (candidate === undefined) {
      return
    }

    const problem = validateFile(candidate)
    if (problem !== null) {
      setFile(null)
      setError(problem)
      onError?.(problem)
      return
    }

    setFile(candidate)
    setError(null)
    onFileSelected(candidate)
  }

  function handleChange(event: ChangeEvent<HTMLInputElement>): void {
    accept(event.target.files?.[0])
  }

  function handleDragEnter(event: DragEvent<HTMLElement>): void {
    event.preventDefault()
    depth.current += 1
    if (!disabled) {
      setDragging(true)
    }
  }

  function handleDragOver(event: DragEvent<HTMLElement>): void {
    // Without this the browser opens the file instead of handing it over.
    event.preventDefault()
  }

  function handleDragLeave(): void {
    depth.current = Math.max(0, depth.current - 1)
    if (depth.current === 0) {
      setDragging(false)
    }
  }

  function handleDrop(event: DragEvent<HTMLElement>): void {
    event.preventDefault()
    depth.current = 0
    setDragging(false)
    if (!disabled) {
      accept(event.dataTransfer?.files?.[0])
    }
  }

  return (
    <div className={cx('oa-drop', className)}>
      <label
        className={cx(
          'oa-drop__zone',
          dragging && 'oa-drop__zone--dragging',
          error !== null && 'oa-drop__zone--invalid',
          disabled && 'oa-drop__zone--disabled',
        )}
        htmlFor={inputId}
        onDragEnter={handleDragEnter}
        onDragOver={handleDragOver}
        onDragLeave={handleDragLeave}
        onDrop={handleDrop}
      >
        <FileUp className="oa-drop__icon" aria-hidden="true" />
        <span className="oa-drop__prompt">Drop a document here, or choose a file</span>
        <span className="oa-drop__hint">PDF or TXT</span>

        <input
          className="visually-hidden"
          id={inputId}
          type="file"
          accept={ACCEPT_ATTRIBUTE}
          disabled={disabled}
          onChange={handleChange}
          aria-describedby={error === null ? undefined : errorId}
          aria-invalid={error === null ? undefined : true}
        />
      </label>

      {file !== null && (
        <p className="oa-drop__file">
          <span className="oa-drop__name">{file.name}</span>
          <span className="oa-drop__size">{formatFileSize(file.size)}</span>
        </p>
      )}

      {error !== null && (
        <p className="oa-drop__error" id={errorId} role="alert">
          {error}
        </p>
      )}
    </div>
  )
}
