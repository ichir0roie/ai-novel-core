"use client";

import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useEffect } from "react";
import { LAUNCH_PARAM, loadLastPage, saveLastPage } from "@/lib/lastPage";

/** 見ているページを覚え、ホーム画面のアプリとして起動したとき(start_url)は、最後に見ていたページへ移す。
 * スマホはアプリを裏に回すと止めてしまい、次に開くと start_url から読み直すので、これが無いと毎回トップに戻る。 */
export default function ResumeLastPage() {
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();

  useEffect(() => {
    if (searchParams.has(LAUNCH_PARAM)) {
      router.replace(loadLastPage() ?? "/");
      return;
    }
    const query = searchParams.toString();
    saveLastPage(query ? `${pathname}?${query}` : pathname);
  }, [pathname, searchParams, router]);

  return null;
}
