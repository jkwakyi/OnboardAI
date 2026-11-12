/**
 * The icon set (ON-64).
 *
 * Lucide, installed as a dependency under the ISC licence. Nothing in this
 * repository holds a copied SVG file: the epic rules out third-party assets
 * that are not freely licensed, and a pasted icon is exactly the kind of
 * asset whose provenance nobody can reconstruct six months later.
 *
 * Everything imports icons from here rather than from `lucide-react`
 * directly. That keeps the set small and visible - adding an icon means
 * adding a line to this file - and means swapping the package later is one
 * edit instead of a search across the pages.
 */
export {
  ChevronDown,
  CircleCheckBig,
  FileText,
  FileUp,
  Info,
  Inbox,
  LoaderCircle,
  LogOut,
  MessageSquare,
  Plus,
  Quote,
  RefreshCw,
  SearchX,
  ShieldAlert,
  TriangleAlert,
  Upload,
  UserRound,
  X,
} from 'lucide-react'

export type { LucideIcon } from 'lucide-react'
