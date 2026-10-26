"use client";

import { useSyncExternalStore } from "react";

// globals.css の「スマホの幅」と同じ境目
const NARROW = "(max-width: 640px)";

const subscribe = (listener: () => void) => {
  const query = window.matchMedia(NARROW);
  query.addEventListener("change", listener);
  return () => query.removeEventListener("change", listener);
};

/** スマホの幅のとき true。 */
export const useNarrow = () => useSyncExternalStore(subscribe, () => window.matchMedia(NARROW).matches, () => false);
