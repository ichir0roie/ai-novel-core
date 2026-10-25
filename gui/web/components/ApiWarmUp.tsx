"use client";

import { useEffect } from "react";
import { warmUp } from "@/lib/api";

const INTERVAL_MS = 60_000;

/** 画面が見えている間、API(Lambda)を 1 分ごとに叩いて温めておく。何も描かない。
 * 開いたときは画面の読み込みが API を叩くので、すぐには叩かない(並べて送ると、その分だけ別の実行環境が冷えたまま起きる) */
export default function ApiWarmUp() {
  useEffect(() => {
    let timer: number | undefined;
    const stop = () => {
      window.clearInterval(timer);
      timer = undefined;
    };
    const start = () => {
      stop();
      timer = window.setInterval(() => void warmUp(), INTERVAL_MS);
    };
    // 裏に回っている間(スマホが眠っている間も)はタイマーが止まり、実行環境が落ちているので、戻ったらすぐ叩く
    const resume = () => {
      void warmUp();
      start();
    };
    const onVisibilityChange = () => (document.visibilityState === "visible" ? resume() : stop());
    // bfcache から戻ったときは visibilitychange が来ないことがある
    const onPageShow = (event: PageTransitionEvent) => {
      if (event.persisted) resume();
    };
    if (document.visibilityState === "visible") start();
    document.addEventListener("visibilitychange", onVisibilityChange);
    window.addEventListener("pageshow", onPageShow);
    return () => {
      stop();
      document.removeEventListener("visibilitychange", onVisibilityChange);
      window.removeEventListener("pageshow", onPageShow);
    };
  }, []);
  return null;
}
