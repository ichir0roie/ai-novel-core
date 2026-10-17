"use client";

import { useSaving } from "@/lib/saving";
import { T } from "@/lib/text";

/** 保存が走っている間、画面全体を覆って操作を止め、ぐるぐるを出す。 */
export default function SavingOverlay() {
  const saving = useSaving();
  if (!saving) return null;
  return (
    <div className="saving-overlay" role="status" aria-live="polite">
      <div className="saving-spinner" aria-hidden />
      <span>{T.savingOverlay}</span>
    </div>
  );
}
