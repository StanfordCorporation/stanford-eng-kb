import { useState } from 'react'

import { API_BASE, ORGS } from './lib'

type Mode = 'file' | 'text'
type Status =
  | { kind: 'idle' }
  | { kind: 'submitting' }
  | { kind: 'success'; chunks: number; characters: number }
  | { kind: 'error'; message: string }

export default function AddToKB() {
  const [orgId, setOrgId] = useState<string | null>(null)
  const [subId, setSubId] = useState<string | null>(null)
  const [mode, setMode] = useState<Mode>('file')
  const [text, setText] = useState('')
  const [file, setFile] = useState<File | null>(null)
  const [dragOver, setDragOver] = useState(false)
  const [status, setStatus] = useState<Status>({ kind: 'idle' })

  const org = ORGS.find((o) => o.id === orgId) ?? null
  const sub = org?.subs.find((s) => s.id === subId) ?? null
  const submitting = status.kind === 'submitting'

  function selectOrg(id: string) {
    setOrgId(id)
    setSubId(null)
    setStatus({ kind: 'idle' })
  }

  function selectSub(id: string) {
    setSubId(id)
    setStatus({ kind: 'idle' })
  }

  function onDrop(e: React.DragEvent<HTMLDivElement>) {
    e.preventDefault()
    setDragOver(false)
    const f = e.dataTransfer.files?.[0]
    if (f) setFile(f)
  }

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault()
    if (!org || !sub || submitting) return

    const form = new FormData()
    form.append('org_id', org.id)
    form.append('sub_id', sub.id)
    if (mode === 'file' && file) {
      form.append('file', file)
    } else if (mode === 'text' && text.trim()) {
      form.append('text', text)
    } else {
      return
    }

    setStatus({ kind: 'submitting' })
    try {
      // Auth comes from the session cookie set on login — no header needed.
      const res = await fetch(`${API_BASE}/api/ingest/upload`, {
        method: 'POST',
        credentials: 'include',
        body: form,
      })
      if (!res.ok) {
        const detail = await res.text()
        throw new Error(`HTTP ${res.status}: ${detail}`)
      }
      const data = (await res.json()) as { chunks: number; characters: number }
      setStatus({ kind: 'success', chunks: data.chunks, characters: data.characters })
      setFile(null)
      setText('')
    } catch (err) {
      setStatus({
        kind: 'error',
        message: err instanceof Error ? err.message : String(err),
      })
    }
  }

  const canSubmit =
    !!sub && !submitting && (mode === 'file' ? !!file : text.trim().length > 0)

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
                {submitting ? 'Uploading…' : 'Add to knowledge base'}
              </button>
            </div>

            {status.kind === 'success' && (
              <div className="add-kb-notice success">
                Added {status.chunks} chunks ({status.characters.toLocaleString()} characters)
                to <strong>{org!.name}</strong> · <strong>{sub.name}</strong>.
              </div>
            )}
            {status.kind === 'error' && (
              <div className="add-kb-notice error">Upload failed — {status.message}</div>
            )}
          </form>
        </section>
      )}
    </div>
  )
}
