import { useSyncExternalStore } from "react";

// 画面が選んでいる作品。API は時刻をこの作品の暦で出し入れし(`db/story_scope.py`)、作品を渡さずに足した人物・アイデア・場所をこの作品に置く
export const STORY_HEADER = "x-novel-story";
const STORAGE_KEY = "selected-story";

// 読んだら、ページを開き直すまで同じ作品を使う(読み込んだ時刻と、あとで送る時刻の暦を揃える)
let selected: number | null | undefined;

export function selectedStoryId(): number | null {
  if (typeof window === "undefined") return null;
  if (selected === undefined) {
    selected = null;
    try {
      const id = Number(localStorage.getItem(STORAGE_KEY));
      if (Number.isInteger(id) && id > 0) selected = id;
    } catch {
      // 覚えられないブラウザでは、選ばずに(西暦で)開く
    }
  }
  return selected;
}

/** API の要求に付ける作品のヘッダ */
export function storyHeaders(): Record<string, string> {
  const id = selectedStoryId();
  return id === null ? {} : { [STORY_HEADER]: String(id) };
}

/** 作品を選び直す。読み込んだ時刻・選択肢はどれも前の作品の暦で数えてあるので、ページを読み直してから使う
 * (書きかけがあって読み直しを止めたら、そのページは前の作品のまま) */
export function selectStory(id: number | null) {
  try {
    if (id === null) localStorage.removeItem(STORAGE_KEY);
    else localStorage.setItem(STORAGE_KEY, String(id));
  } catch {
    // 覚えられないブラウザでは選び直せない
    return;
  }
  window.location.reload();
}

const subscribe = () => () => {};

/** 画面が選んでいる作品。サーバーで描くときは選んでいないことにする */
export const useSelectedStoryId = () => useSyncExternalStore(subscribe, selectedStoryId, () => null);
