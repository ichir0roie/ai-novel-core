"use client";

import { useState } from "react";
import Modal from "@/components/Modal";
import { invalidateOptions } from "@/components/ReferenceSelect";
import StampInput from "@/components/StampInput";
import { createRecord, getPreviousEpisode, type Rec } from "@/lib/api";
import { T } from "@/lib/text";

// 追加ページと同じく、同じ作品の前の話から写す欄(lib/previousEpisode.ts)
const COPIED_KEYS = ["location_id", "viewpoint_character_id", "character_ids"] as const;

type Props = {
  /** 話の追加ページに渡す初期値(押した所の時刻・作品・場所) */
  initial: Rec;
  /** 足す先の作品の名前。分かれば時刻の上に添える */
  storyLabel: string | null;
  onClose: () => void;
  /** その場で話を足し終えたとき */
  onAdded: () => void;
};

/** タイムラインの空いた所を押したときの小さなモーダル。時刻とプロットだけでその場で話を足すか、
 * ほかの欄も書くなら追加ページを別タブに開く。 */
export default function NewEpisodeModal({ initial, storyLabel, onClose, onAdded }: Props) {
  const [start, setStart] = useState<string | null>((initial.start as string | null) ?? null);
  const [plot, setPlot] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const storyId = typeof initial.story_id === "number" ? initial.story_id : null;

  const open = () => {
    const params = new URLSearchParams(
      Object.entries({ ...initial, start, plot_text: plot || null }).filter(([, v]) => v != null).map(([k, v]) => [k, String(v)]),
    );
    window.open(`/tables/episode/new?${params}`, "_blank", "noopener,noreferrer");
    onClose();
  };

  const add = async () => {
    if (storyId === null) return;
    setBusy(true);
    setError(null);
    try {
      const data: Rec = { ...initial, start, plot_text: plot };
      const previous = await getPreviousEpisode(storyId, start);
      for (const key of COPIED_KEYS) {
        const v = previous?.[key];
        if (v != null && !(Array.isArray(v) && v.length === 0)) data[key] = v;
      }
      await createRecord("episode", data);
      invalidateOptions("episode");
      onAdded();
      onClose();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
      setBusy(false);
    }
  };

  return (
    <Modal
      title={T.timeline.newEpisode}
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
          <button type="button" className="primary" onClick={() => void add()} disabled={busy || storyId === null || !start}>
            {T.timeline.addEpisode}
          </button>
        </>
      }
    >
      {error && <div className="status error">{error}</div>}
      <div className="hint">{storyLabel ? T.timeline.newEpisodeIn(storyLabel) : T.timeline.newEpisodeNoStory}</div>
      <div className="field">
        <label>{T.timeline.newEpisodeStart}</label>
        <StampInput value={start} onChange={setStart} />
      </div>
      <div className="field">
        <label>{T.timeline.newEpisodePlot}</label>
        <textarea value={plot} onChange={(e) => setPlot(e.target.value)} />
      </div>
    </Modal>
  );
}
