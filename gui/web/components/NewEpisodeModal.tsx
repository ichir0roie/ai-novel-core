"use client";

import { useState } from "react";
import Modal from "@/components/Modal";
import { invalidateOptions } from "@/components/ReferenceSelect";
import StampInput from "@/components/StampInput";
import { createRecord, getPreviousEpisode, type Rec } from "@/lib/api";
import type { OpenModifiers } from "@/lib/openPage";
import { trackSaving, useSaveShortcut } from "@/lib/saving";
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
  /** 追加ページへ移る(Ctrl(⌘)を押しながらなら別タブで開く) */
  onOpenPage: (url: string, e: OpenModifiers) => void;
};

/** タイムラインの空いた所を押したときの小さなモーダル。時刻(start・end)・タイトル・プロットだけでその場で話を足すか、
 * ほかの欄も書くなら追加ページへ移る。 */
export default function NewEpisodeModal({ initial, storyLabel, onClose, onAdded, onOpenPage }: Props) {
  const [start, setStart] = useState<string | null>((initial.start as string | null) ?? null);
  const [end, setEnd] = useState<string | null>((initial.end as string | null) ?? null);
  const [title, setTitle] = useState("");
  const [plot, setPlot] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const storyId = typeof initial.story_id === "number" ? initial.story_id : null;

  const open = (e: OpenModifiers) => {
    const params = new URLSearchParams(
      Object.entries({ ...initial, start, end, title: title || null, plot_text: plot || null }).filter(([, v]) => v != null).map(([k, v]) => [k, String(v)]),
    );
    onOpenPage(`/tables/episode/new?${params}`, e);
  };

  const add = async () => {
    if (storyId === null) return;
    setBusy(true);
    setError(null);
    try {
      const data: Rec = { ...initial, start, end, title, plot_text: plot };
      // 前の話を引くあいだからロックする(引いているうちに欄を直されても、足す行には入らない)
      await trackSaving(
        getPreviousEpisode(storyId, start).then((previous) => {
          for (const key of COPIED_KEYS) {
            const v = previous?.[key];
            if (v != null && !(Array.isArray(v) && v.length === 0)) data[key] = v;
          }
          return createRecord("episode", data);
        }),
      );
      invalidateOptions("episode");
      onAdded();
      onClose();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
      setBusy(false);
    }
  };

  useSaveShortcut(() => void add(), !busy && storyId !== null && !!start);

  return (
    <Modal
      title={T.timeline.newEpisode}
      onClose={onClose}
      actions={
        <>
          <button type="button" onClick={open} disabled={busy}>
            {T.timeline.openForm}
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
        <label>{T.timeline.start}</label>
        <StampInput value={start} onChange={setStart} />
      </div>
      <div className="field">
        <label>{T.timeline.end}</label>
        <StampInput value={end} onChange={setEnd} />
      </div>
      <div className="field">
        <label>{T.timeline.newEpisodeTitle}</label>
        <input type="text" value={title} onChange={(e) => setTitle(e.target.value)} />
      </div>
      <div className="field">
        <label>{T.timeline.newEpisodePlot}</label>
        <textarea value={plot} onChange={(e) => setPlot(e.target.value)} />
      </div>
    </Modal>
  );
}
