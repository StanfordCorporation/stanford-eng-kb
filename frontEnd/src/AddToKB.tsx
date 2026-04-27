import { useState } from 'react'

type SubGroup = { id: string; name: string }
type Org = {
  id: string
  name: string
  description: string
  subs: SubGroup[]
}

const ORGS: Org[] = [
  {
    id: 'stanford-legal',
    name: 'Stanford Legal',
    description: 'Legal practice covering property, family, and estate matters.',
    subs: [
      { id: 'property-law', name: 'Property Law Firm' },
      { id: 'family-law', name: 'Family Law' },
      { id: 'wills-estate', name: 'Wills & Estate Law' },
    ],
  },
  {
    id: 'stanford-finance',
    name: 'Stanford Finance',
    description: 'Financial services across mortgage and broking.',
    subs: [{ id: 'mortgage-broking', name: 'Mortgage & Broking Firm' }],
  },
  {
    id: 'stanford-innovations',
    name: 'Stanford Innovations',
    description: 'Internal R&D — technology and marketing.',
    subs: [
      { id: 'technology', name: 'Technology' },
      { id: 'marketing', name: 'Marketing' },
    ],
  },
]

type Mode = 'file' | 'text'

export default function AddToKB() {
  const [orgId, setOrgId] = useState<string | null>(null)
  const [subId, setSubId] = useState<string | null>(null)
  const [mode, setMode] = useState<Mode>('file')
  const [text, setText] = useState('')
  const [file, setFile] = useState<File | null>(null)
  const [dragOver, setDragOver] = useState(false)
  const [notice, setNotice] = useState<string | null>(null)

  const org = ORGS.find((o) => o.id === orgId) ?? null
  const sub = org?.subs.find((s) => s.id === subId) ?? null

  function selectOrg(id: string) {
    setOrgId(id)
    setSubId(null)
    setNotice(null)
  }

  function selectSub(id: string) {
    setSubId(id)
    setNotice(null)
  }

  function onDrop(e: React.DragEvent<HTMLDivElement>) {
    e.preventDefault()
    setDragOver(false)
    const f = e.dataTransfer.files?.[0]
    if (f) setFile(f)
  }

  function onSubmit(e: React.FormEvent) {
    e.preventDefault()
    setNotice('UI scaffolded — upload pipeline not yet wired up.')
  }

  const canSubmit = !!sub && (mode === 'file' ? !!file : text.trim().length > 0)

  return (
    <div className="add-kb-body">
      <section className="add-kb-step">
        <div className="add-kb-step-label">Step 1 — Organization</div>
        <div className="org-grid">
          {ORGS.map((o) => (
            <button
              key={o.id}
              type="button"
              className={`org-card ${orgId === o.id ? 'selected' : ''}`}
              onClick={() => selectOrg(o.id)}
            >
              <div className="org-name">{o.name}</div>
              <div className="org-desc">{o.description}</div>
              <div className="org-meta">
                {o.subs.length} {o.subs.length === 1 ? 'group' : 'groups'}
              </div>
            </button>
          ))}
        </div>
      </section>

      {org && (
        <section className="add-kb-step">
          <div className="add-kb-step-label">Step 2 — Group within {org.name}</div>
          <div className="sub-list">
            {org.subs.map((s) => (
              <button
                key={s.id}
                type="button"
                className={`sub-chip ${subId === s.id ? 'selected' : ''}`}
                onClick={() => selectSub(s.id)}
              >
                {s.name}
              </button>
            ))}
          </div>
        </section>
      )}

      {sub && (
        <section className="add-kb-step">
          <div className="add-kb-step-label">Step 3 — Add content</div>

          <div className="mode-tabs">
            <button
              type="button"
              className={`mode-tab ${mode === 'file' ? 'selected' : ''}`}
              onClick={() => setMode('file')}
            >
              Upload file
            </button>
            <button
              type="button"
              className={`mode-tab ${mode === 'text' ? 'selected' : ''}`}
              onClick={() => setMode('text')}
            >
              Paste text
            </button>
          </div>

          <form className="add-kb-form" onSubmit={onSubmit}>
            {mode === 'file' ? (
              <div
                className={`drop-zone ${dragOver ? 'drag-over' : ''}`}
                onDragOver={(e) => {
                  e.preventDefault()
                  setDragOver(true)
                }}
                onDragLeave={() => setDragOver(false)}
                onDrop={onDrop}
              >
                <input
                  id="kb-file"
                  type="file"
                  accept=".md,.txt,.pdf,.docx"
                  onChange={(e) => setFile(e.target.files?.[0] ?? null)}
                  style={{ display: 'none' }}
                />
                <label htmlFor="kb-file" className="drop-label">
                  {file ? (
                    <>
                      <strong>{file.name}</strong>
                      <span className="drop-hint">
                        {(file.size / 1024).toFixed(1)} KB · click to change
                      </span>
                    </>
                  ) : (
                    <>
                      <strong>Drop a file here, or click to browse</strong>
                      <span className="drop-hint">.md, .txt, .pdf, .docx</span>
                    </>
                  )}
                </label>
              </div>
            ) : (
              <textarea
                className="kb-textarea"
                placeholder="Paste or type the content to add to the knowledge base…"
                value={text}
                onChange={(e) => setText(e.target.value)}
                rows={10}
              />
            )}

            <div className="add-kb-actions">
              <div className="add-kb-target">
                Adding to <strong>{org!.name}</strong> · <strong>{sub.name}</strong>
              </div>
              <button type="submit" className="primary-btn" disabled={!canSubmit}>
                Add to knowledge base
              </button>
            </div>

            {notice && <div className="add-kb-notice">{notice}</div>}
          </form>
        </section>
      )}
    </div>
  )
}
