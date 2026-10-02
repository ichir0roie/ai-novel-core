"use client";

import { useState } from "react";
import Modal from "@/components/Modal";
import StampInput from "@/components/StampInput";
import type { Rec } from "@/lib/api";
import { T } from "@/lib/text";

type Props = {
  /** 話の追加ページに渡す初期値(押した所の時刻・作品・場所) */
  initial: Rec;
  /** 足す先の作品の名前。分かれば時刻の上に添える */
  storyLabel: string | null;
  onClose: () => void;
};

/** タイムラインの空いた所を押したときの小さなモーダル。時刻だけを直し、ボタンで話の追加ページを別タブに開く
 * (中身は追加ページで書く)。 */
export default function NewEpisodeModal({ initial, storyLabel, onClose }: Props) {
  const [start, setStart] = useState<string | null>((initial.start as string | null) ?? null);

  const open = () => {
    const params = new URLSearchParams(
      Object.entries({ ...initial, start }).filter(([, v]) => v != null).map(([k, v]) => [k, String(v)]),
    );
    window.open(`/tables/episode/new?${params}`, "_blank", "noopener,noreferrer");
    onClose();
  };

  return (
    <Modal
      title={T.timeline.newEpisode}
      onClose={onClose}
      compact
      actions={
        <>
          <span className="spacer" />
          <button type="button" onClick={onClose}>
            {T.create.cancel}
          </button>
          <button type="button" className="primary" onClick={open}>
            {T.timeline.openInNewTab}
          </button>
        </>
      }
    >
      {storyLabel && <div className="hint">{T.timeline.newEpisodeIn(storyLabel)}</div>}
      <div className="field">
        <label>{T.timeline.newEpisodeStart}</label>
        <StampInput value={start} onChange={setStart} />
      </div>
    </Modal>
  );
}
