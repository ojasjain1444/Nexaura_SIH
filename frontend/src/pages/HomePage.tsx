import {
  ArrowRight,
  BadgeCheck,
  BookMarked,
  FlaskConical,
  MessageSquareText,
  ScrollText,
  ShieldCheck,
} from 'lucide-react'
import type { ComponentType } from 'react'
import { Link } from 'react-router-dom'
import { Button, Card } from '../components/ui'

// Reduced from 8 to 4 — one representative capability per major section of
// the app, rather than an exhaustive list. Apple's own product pages favor
// a handful of clear highlights over a complete feature inventory; a
// visitor deciding whether to use the assistant needs a quick sense of
// what it does, not a full spec sheet.
const capabilities: {
  title: string
  description: string
  icon: ComponentType<{ size?: number; className?: string }>
}[] = [
  { icon: MessageSquareText, title: 'Ask in plain language', description: 'Get source-backed answers about any Indian Standard, cited to the exact clause.' },
  { icon: BookMarked, title: 'Find applicable standards', description: 'Describe your product to see exactly which standards apply to it.' },
  { icon: ScrollText, title: 'Understand certification', description: 'Step-by-step guidance through BIS licensing and registration.' },
  { icon: FlaskConical, title: 'Locate testing labs', description: 'BIS-recognized laboratories near you, by category.' },
]

export function HomePage() {
  return (
    <div className="mx-auto max-w-5xl space-y-16 pb-8">
      <section className="overflow-hidden rounded-3xl border border-slate-200/80 bg-white shadow-[var(--shadow-sm)]">
        <div className="grid grid-cols-1 lg:grid-cols-2">
          <div className="px-6 py-12 sm:px-12 sm:py-16">
            <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">
              Smart India Hackathon 2026 &middot; SIH26107
            </p>
            <h1 className="mt-5 max-w-md text-[2rem] font-semibold leading-[1.15] tracking-tight text-slate-900 sm:text-[2.5rem]">
              One assistant for every Indian Standard.
            </h1>
            <p className="mt-5 max-w-sm text-[15px] leading-relaxed text-slate-500">
              Find applicable standards, understand certification, and get source-backed
              answers &mdash; without digging through hundreds of PDFs and portals.
            </p>
            <div className="mt-9 flex flex-wrap gap-3">
              <Link to="/assistant">
                <Button size="lg">
                  Ask the Assistant <ArrowRight size={16} />
                </Button>
              </Link>
              <Link to="/standards">
                <Button size="lg" variant="secondary">
                  Browse Standards
                </Button>
              </Link>
            </div>
          </div>
          <div className="hidden items-center justify-center bg-slate-50 lg:flex">
            <div className="flex h-40 w-40 items-center justify-center rounded-[2.5rem] bg-white shadow-[var(--shadow-lg)]">
              <ShieldCheck size={64} className="text-accent-500" strokeWidth={1.5} />
            </div>
          </div>
        </div>
      </section>

      <section>
        <h2 className="mb-8 text-center text-2xl font-semibold tracking-tight text-slate-900">What it does</h2>
        <div className="grid grid-cols-1 gap-5 sm:grid-cols-2 lg:grid-cols-4">
          {capabilities.map((c) => (
            <Card key={c.title} className="flex flex-col items-start gap-3 p-6">
              <div className="flex h-11 w-11 items-center justify-center rounded-2xl bg-accent-50 text-accent-600">
                <c.icon size={20} />
              </div>
              <div>
                <h3 className="text-[15px] font-semibold text-slate-900">{c.title}</h3>
                <p className="mt-1.5 text-sm leading-relaxed text-slate-500">{c.description}</p>
              </div>
            </Card>
          ))}
        </div>
      </section>

      <Card className="flex flex-col items-center gap-4 p-10 text-center sm:p-14">
        <div className="flex h-12 w-12 items-center justify-center rounded-2xl bg-accent-50 text-accent-600">
          <BadgeCheck size={22} />
        </div>
        <div>
          <p className="text-lg font-semibold text-slate-900">Built for MSMEs, startups, students &amp; consumers</p>
          <p className="mt-1.5 text-sm text-slate-500">One place to find, understand, and act on Indian Standards.</p>
        </div>
        <Link to="/assistant">
          <Button>
            Start a conversation <ArrowRight size={15} />
          </Button>
        </Link>
      </Card>
    </div>
  )
}
