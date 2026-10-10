"use client";

import { useState } from "react";
import Modal from "@/components/Modal";
import { invalidateOptions } from "@/components/ReferenceSelect";
import StampInput from "@/components/StampInput";
import { createRecord, type Rec } from "@/lib/api";
import { T } from "@/lib/text";

type Props = {
  /** 押した所の時刻(開始の初期値) */
  start: string | null;
  /** 親の出来事。根に足すなら null */
  parent: { id: number; label: string } | null;
  onClose: () => void;
  /** その場で出来事を足し終えたとき */
  onAdded: () => void;
};

/** 出来事のタイムラインで出来事を足す小さなモーダル。名前・期間・本文だけでその場で足すか、
 * ほかの欄(場所・当事者)も書くなら追加ページを別タブに開く。 */
export default function NewEventModal({ start: initialStart, parent, onClose, onAdded }: Props) {
  const [name, setName] = useState("");
  const [start, setStart] = useState<string | null>(initialStart);
  const [end, setEnd] = useState<string | null>(null);
  const [hidden, setHidden] = useState(false);
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // 出来事の時刻(`time`)は必須なので、開始と同じにする
  const data = (): Rec => ({
    name,
    time: start,
    start,
    end,
    hidden,
    text,
    parent_event_id: parent?.id ?? null,
  });

  const open = () => {
    const params = new URLSearchParams(
      Object.entries(data())
        .filter(([, v]) => v != null && v !== "" && v !== false)
        .map(([k, v]) => [k, String(v)]),
    );
    window.open(`/tables/event/new?${params}`, "_blank", "noopener,noreferrer");
    onClose();
  };

  const add = async () => {
    setBusy(true);
    setError(null);
    try {
      await createRecord("event", data());
      invalidateOptions("event");
      onAdded();
      onClose();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
      setBusy(false);
    }
  };

  return (
    <Modal
      title={T.eventTimeline.newEvent}
      onClose={onClose}
      actions={
        <>
          <button type="button" onClick={open} disabled={busy}>
            {T.timeline.openInNewTab}
          </button>
          <span className="spacer" />
          <button type="button" onClick={onClose} disabled={busy}>
            {T.create.cancel}
          </button>
          <button type="button" className="primary" onClick={() => void add()} disabled={busy || !name.trim() || !start}>
            {T.eventTimeline.add}
          </button>
        </>
      }
    >
      {error && <div className="status error">{error}</div>}
      <div className="hint">{parent ? T.eventTimeline.newChildOf(parent.label) : T.eventTimeline.newRoot}</div>
      <div className="field">
        <label>{T.eventTimeline.name}</label>
        <input type="text" value={name} onChange={(e) => setName(e.target.value)} autoFocus />
      </div>
      <div className="field">
        <label>{T.eventTimeline.start}</label>
        <StampInput value={start} onChange={setStart} />
      </div>
      <div className="field">
        <label>{T.eventTimeline.end}</label>
        <StampInput value={end} onChange={setEnd} />
      </div>
      <label className="hint">
        <input type="checkbox" checked={hidden} onChange={(e) => setHidden(e.target.checked)} /> {T.eventTimeline.hidden}
      </label>
      <div className="field">
        <label>{T.eventTimeline.text}</label>
        <textarea value={text} onChange={(e) => setText(e.target.value)} />
      </div>
    </Modal>
  );
}
