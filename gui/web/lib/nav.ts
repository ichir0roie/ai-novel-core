/** クリックによるページ移動を、既存のタブに留まらず別タブで開く。 */
export function openInNewTab(url: string) {
  window.open(url, "_blank", "noopener,noreferrer");
}
