import { useRef, useState } from 'react'

const clamp = (v: number) => Math.min(1, Math.max(0, v))
const round = (v: number) => Math.round(v * 1000) / 1000

/** A picture on which the user drags a box (mouse or finger). The box is given as
 *  [left, top, right, bottom], fractions of the picture, like `roi` in cameras.json. */
export default function AreaPicker({ src, roi, onChange }: {
  src: string; roi: number[] | null; onChange: (roi: number[]) => void
}) {
  const ref = useRef<HTMLDivElement>(null)
  const [start, setStart] = useState<number[] | null>(null)
  const [draft, setDraft] = useState<number[] | null>(null)

  const at = (e: React.PointerEvent) => {
    const r = ref.current!.getBoundingClientRect()
    return [clamp((e.clientX - r.left) / r.width), clamp((e.clientY - r.top) / r.height)]
  }
  const box = (a: number[], b: number[]) =>
    [Math.min(a[0], b[0]), Math.min(a[1], b[1]), Math.max(a[0], b[0]), Math.max(a[1], b[1])]

  const shown = draft ?? roi
  return (
    <div
      ref={ref}
      dir="ltr"
      style={{ position: 'relative', overflow: 'hidden', borderRadius: 8, touchAction: 'none', cursor: 'crosshair', userSelect: 'none' }}
      onPointerDown={(e) => { e.currentTarget.setPointerCapture(e.pointerId); const p = at(e); setStart(p); setDraft([...p, ...p]) }}
      onPointerMove={(e) => start && setDraft(box(start, at(e)))}
      onPointerUp={() => {
        if (draft && draft[2] - draft[0] > 0.03 && draft[3] - draft[1] > 0.03) onChange(draft.map(round))  // ignore a tap
        setStart(null); setDraft(null)
      }}
    >
      <img src={src} alt="" draggable={false} style={{ width: '100%', display: 'block' }} />
      {shown && (
        <div style={{
          position: 'absolute', pointerEvents: 'none', borderRadius: 4,
          left: `${shown[0] * 100}%`, top: `${shown[1] * 100}%`,
          width: `${(shown[2] - shown[0]) * 100}%`, height: `${(shown[3] - shown[1]) * 100}%`,
          border: '3px solid var(--mantine-color-teal-5)', boxShadow: '0 0 0 9999px rgba(0, 0, 0, 0.5)',
        }} />
      )}
    </div>
  )
}
