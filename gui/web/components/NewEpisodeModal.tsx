"use client";

import { useState } from "react";
import EpisodeFields, { addEpisode, type EpisodeDraft } from "@/components/EpisodeFields";
import Modal from "@/components/Modal";
import { invalidateOptions } from "@/components/ReferenceSelect";
import type { Rec } from "@/lib/api";
import type { OpenModifiers } from "@/lib/openPage";
import { trackSaving, useSaveShortcut } from "@/lib/saving";
import { T } from "@/lib/text";

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

/** 追加ページへ移るときに、書きかけを初期値として渡す URL */
export function newEpisodeUrl(initial: Rec, draft: EpisodeDraft): string {
  const params = new URLSearchParams(
    Object.entries({ ...initial, start: draft.start, end: draft.end, title: draft.title || null, plot_text: draft.plot || null })
      .filter(([, v]) => v != null)
      .map(([k, v]) => [k, String(v)]),
  );
  return `/tables/episode/new?${params}`;
}

/** タイムラインの空いた所を押したときの小さなモーダル。時刻(start・end)・タイトル・プロットだけでその場で話を足すか、
 * ほかの欄も書くなら追加ページへ移る。 */
export default function NewEpisodeModal({ initial, storyLabel, onClose, onAdded, onOpenPage }: Props) {
  const [draft, setDraft] = useState<EpisodeDraft>({
    start: (initial.start as string | null) ?? null,
    end: (initial.end as string | null) ?? null,
    title: "",
    plot: "",
  });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const storyId = typeof initial.story_id === "number" ? initial.story_id : null;

  const add = async () => {
    if (storyId === null) return;
    setBusy(true);
    setError(null);
    try {
      // 前の話を引くあいだからロックする(引いているうちに欄を直されても、足す行には入らない)
      await trackSaving(addEpisode(initial, draft));
      invalidateOptions("episode");
      onAdded();
      onClose();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
      setBusy(false);
    }
  };

  useSaveShortcut(() => void add(), !busy && storyId !== null && !!draft.start);

  return (
    <Modal
      title={T.timeline.newEpisode}
      onClose={onClose}
      actions={
        <>
          <button type="button" onClick={(e) => onOpenPage(newEpisodeUrl(initial, draft), e)} disabled={busy}>
            {T.timeline.openForm}
          </button>
          <span className="spacer" />
          <button type="button" onClick={onClose} disabled={busy}>
            {T.create.cancel}
          </button>
          <button type="button" className="primary" onClick={() => void add()} disabled={busy || storyId === null || !draft.start}>
            {T.timeline.addEpisode}
          </button>
        </>
      }
    >
      {error && <div className="status error">{error}</div>}
      <div className="hint">{storyLabel ? T.timeline.newEpisodeIn(storyLabel) : T.timeline.newEpisodeNoStory}</div>
      <EpisodeFields value={draft} onChange={setDraft} />
    </Modal>
  );
}
