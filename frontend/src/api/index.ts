/**
 * The API Client (ON-38).
 *
 * Everything that talks to the Backend API goes through here, so there is
 * one place that knows the base path, one place that attaches the login
 * token, and one place that decides what a status code means to a person.
 *
 * The endpoints arrive with their own tickets. `auth` is ON-38's;
 * documents are ON-42, chat is ON-48, escalations are ON-66.
 */
export { login } from './auth'
export {
  MAX_QUESTION_CHARACTERS,
  askQuestion,
  type ChatAnswer,
  type Citation,
} from './chat'
export { API_BASE_URL, createApiClient, type ApiClient, type RequestOptions } from './client'
export { FILE_FIELD, uploadDocument, type UploadedDocument } from './documents'
export { uploadWithProgress, type UploadOptions } from './upload'
export {
  ApiError,
  NETWORK_MESSAGE,
  NetworkError,
  UNKNOWN_MESSAGE,
  detailFrom,
  messageForStatus,
} from './errors'
