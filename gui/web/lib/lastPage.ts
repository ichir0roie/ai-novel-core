/** ホーム画面のアプリとして起動したことを示す、manifest の start_url のクエリ */
export const LAUNCH_PARAM = "launch";

const STORAGE_KEY = "last-page";

export function saveLastPage(url: string) {
  try {
    localStorage.setItem(STORAGE_KEY, url);
  } catch {
    // 覚えられなければ、次の起動はトップから始まる
  }
}

export function loadLastPage(): string | null {
  try {
    const url = localStorage.getItem(STORAGE_KEY);
    // 他のサイトへは飛ばない
    return url?.startsWith("/") && !url.startsWith("//") ? url : null;
  } catch {
    return null;
  }
}
