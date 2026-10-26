"use client";

import { useState } from "react";
import Modal from "./Modal";
import { useSaveShortcut } from "@/lib/saving";
import { T } from "@/lib/text";

type Props = {
  value: string;
  error: string | null;
  onClose: () => void;
  /** 保存できたら true */
  onSave: (text: string) => Promise<boolean>;
};

/** 作品・話の AI への指示(instruction)を、ふだんの画面には出さずにモーダルで直す。保存はこの欄だけを送る。 */
export default function InstructionModal({ value, error, onClose, onSave }: Props) {
  const [draft, setDraft] = useState(value);
  const [busy, setBusy] = useState(false);
  const dirty = draft !== value;

  const close = () => {
    if (!dirty || window.confirm(T.styleEditor.discard)) onClose();
  };

  const save = async () => {
    setBusy(true);
    const ok = await onSave(draft);
    setBusy(false);
    if (ok) onClose();
  };

  useSaveShortcut(() => void save(), !busy && dirty);

  return (
    <Modal
      title={T.instruction.title}
      onClose={close}
      actions={
        <>
          <span className="meta">{dirty ? T.styleEditor.unsaved : T.record.noChanges}</span>
          <span className="spacer" />
          {error && <span className="status error">{error}</span>}
          <button type="button" onClick={close} disabled={busy}>
            {T.create.cancel}
          </button>
          <button type="button" className="primary" onClick={() => void save()} disabled={busy || !dirty}>
            {T.record.save}
          </button>
        </>
      }
    >
      <p className="hint">{T.instruction.note}</p>
      <textarea className="instruction-input" autoFocus value={draft} onChange={(e) => setDraft(e.target.value)} />
    </Modal>
  );
}
