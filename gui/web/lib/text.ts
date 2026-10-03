// 画面に出す文言はすべてここに置き、ページ・コンポーネントは文言を直書きしない。
// db の値(場所の category など)は文言ではなく値なので、ここには置かない。

const join = (keys: string[]) => keys.join(", ");
const dash = (v: unknown) => (v == null ? "-" : String(v));
const span = (start: unknown, end: unknown) => (start == null && end == null ? "" : `${start ?? ""} – ${end ?? ""}`);

export const T = {
  appName: "novel db",
  appDescription: "Data editing GUI for ai-novel-core",
  pageTitle: (kind: string, record?: string | null) => (record ? `${kind} - ${record}` : kind),

  loading: "Loading…",
  openRecord: "Open record",
  close: "Close",
  required: "required",
  none: "(none)",
  select: "Select",
  filter: "Filter",
  noCandidates: "No candidates",
  yes: "Yes",
  no: "No",
  zoom: "Zoom",
  invalidJson: (error: string) => `Invalid JSON: ${error}`,
  cannotReachApi: (error: string) => `Cannot reach API: ${error} (check that uvicorn is running)`,
  signInRequired: "Sign in required.",
  span,

  nav: {
    menu: "Menu",
    endpoints: "Endpoints",
    timeline: "Timeline",
    search: "Jump to a page (type a table or page name)",
    noMatch: "No matching page",
    searchHint: "Ctrl+K: search pages",
  },

  home: {
    title: "Tables",
  },

  list: {
    episodesOf: (story: string) => `Episodes of ${story}`,
    story: (id: string) => `story ${id}`,
    stories: "Stories",
    tree: "Tree",
    list: "List",
    add: "+ Add",
    empty: "(empty)",
    searchPlaceholder: "Search name / text",
    search: "Search",
    removeFilter: "Remove this filter",
    filterBy: (label: string) => `Filter by this ${label}`,
    name: "Name",
    text: "Text",
    prev: "Prev",
    next: "Next",
    range: (from: number, to: number, total: number) => `${from}–${to} of ${total}`,
    selectAll: "Select all on this page",
    select: "Select",
    deleteSelected: (count: number) => `Delete selected (${count})`,
    confirmDeleteSelected: (count: number) => `Delete ${count} selected rows? This cannot be undone.`,
  },

  record: {
    clickToEdit: "Click to edit",
    saved: (keys: string[]) => `Saved (${join(keys)})`,
    changed: (keys: string[]) => `Changed: ${join(keys)}`,
    noChanges: "No changes",
    revert: "Revert",
    saveAndBack: "Save and back",
    save: "Save",
    emptySection: "(empty — click to edit)",
    ageAt: "Age",
    ageInYear: (age: number) => `(age ${age})`,
    delete: "Delete",
    confirmDeleteEpisode: (label: string) =>
      `Delete episode "${label}"? Its cast and idea links are removed too. Events, ideas and memes taken from its text stay. This cannot be undone.`,
    deleteFailed: (error: string) => `Could not delete: ${error}`,
  },

  create: {
    title: (label: string) => `New ${label}`,
    cancel: "Cancel",
    add: "Add",
  },

  endpoints: {
    title: "Call endpoint",
    area: {
      world: "Read world",
      story: "Stories / episodes",
      randomizer: "Add / edit / delete",
      idea: "Idea staging",
      meme: "Memes",
      review: "Review",
      fact_check: "Fact check",
    } as Record<string, string>,
    writesDb: "writes db",
    running: "Running…",
    run: "Run",
    jsonHint: 'Write dicts and arrays as JSON (e.g. {"id": 3, "kind": "概念"} / [1, 2])',
    searchPlaceholder: "Search endpoints",
    selectOne: "Select an endpoint on the left",
  },

  related: {
    relationGraph: { title: "Relation graph", sub: "Only relations involving this character" },
    mapCentered: { title: "Map centered here", sub: "Map centered on this location" },
    appearsIn: "Appears in",
    noLinkedText: "(no linked text)",
    episodeList: "Episode list",
    episodeSummary: (episodes: number, letters: number) => `${episodes} episodes / ${letters.toLocaleString()} chars`,
    unsynced: (n: number) => ` / ${n} unsynced`,
  },

  episodeContext: {
    title: "In this episode's time & place",
  },

  episodeCharacters: {
    button: (n: number) => `Characters (${n})`,
    modalTitle: "Characters in this episode",
    none: "(no characters yet)",
  },

  characterSheet: {
    record: "Record",
    at: (time: string | null) => (time ? `At ${time}` : "Parameters (no time limits)"),
    born: "Born",
    died: "Died",
    age: "Age",
    location: "Location",
    noText: "(no text)",
    noHistory: "(no history)",
    undated: "Year undecided",
  },

  storyTree: {
    episodes: (n: number) => `${n} episodes`,
    stories: (n: number) => `${n} stories`,
    noStories: "No stories yet",
    moveToRoot: "Move here to make it a top-level story (no parent)",
    moveFailed: (error: string) => `Could not move: ${error}`,
    move: "Move",
    cancelMove: "Cancel move",
    moveModeHint: (name: string) => `Moving "${name}" — click another story to make it the new parent (Esc to cancel)`,
    collapseAll: "Collapse all",
    addChild: "Add child story",
    addEpisode: "Add episode",
  },

  characterTree: {
    characters: (n: number) => `${n} characters`,
    openLocation: "Open location",
    noCharacters: "No characters yet",
    noLocation: "No location",
    collapseAll: "Collapse all",
  },

  ideaTree: {
    empty: "No ideas yet",
    addChild: "Add child",
    move: "Move",
    cancelMove: "Cancel move",
    moveModeHint: (name: string) => `Moving "${name}" — click another idea to make it the new parent`,
    moveToRoot: "Move here to make it a root idea (no parent)",
    moveFailed: (error: string) => `Could not move: ${error}`,
    collapse: "Collapse",
    expand: "Expand",
    collapseAll: "Collapse all",
    delete: "Delete",
    confirmDeleteWithChildren: (name: string, count: number) =>
      `"${name}" has ${count} child idea${count === 1 ? "" : "s"}. They will be detached (moved to root) and then "${name}" will be deleted. Continue?`,
    deleteFailed: (error: string) => `Could not delete: ${error}`,
  },

  picker: {
    count: (n: number) => `${n} selected`,
    done: "Done",
  },

  treeSelect: {
    collapse: "Collapse",
    expand: "Expand",
  },

  childList: {
    removeRow: "Remove this row",
    addRow: "+ Add row",
    close: "Close",
  },

  maps: {
    title: "Location map",
    centeredOn: (name: string) => `Map centered on ${name}`,
    fullMap: "Full map",
    cannotPlace: (id: number) => `Location id=${id} has neither coordinates nor a polygon, so it cannot be placed on the map. `,
    nonePlaceable: "No location has coordinates or a polygon.",
    radius: (km: number) => `radius ≈ ${Math.round(km).toLocaleString()} km, 1° latitude ≈ ${Math.round((km * Math.PI) / 180).toLocaleString()} km`,
    radiusUnknown: "radius unknown (no area)",
    nameKind: (name: unknown, kind: unknown) => `${name} (${kind ?? ""})`,
    parent: (name: unknown) => `parent: ${dash(name)}`,
    polygonVertices: (n: number) => `polygon: ${n} vertices`,
    environment: (e: string) => `environment: ${e}`,
    lonLatAlt: (lon: number, lat: number, alt: unknown) => `lon ${lon} / lat ${lat} / alt ${dash(alt)}`,
    period: (start: unknown, end: unknown) => `period: ${span(start, end)}`,
    hintClick: "Click a point to show distance and bearing to the other locations. Double-click to open its record.",
    hintCounts: (points: number, shapes: number) => `${points} locations with coordinates, ${shapes} with a polygon. Polygons are drawn as faint areas.`,
    coordinates: "Coordinates",
    environmentDt: "Environment",
    columns: { location: "Location", bearing: "Bearing", distance: "Distance", elevationDiff: "Elevation diff" },
    sameCoordinates: "same coordinates",
    aboutDegrees: (deg: number) => `≈ ${deg.toFixed(1)}°`,
    aboutKm: (km: number) => `≈ ${km.toLocaleString()} km`,
    altDiffUnknown: "elevation diff unknown",
    sameAltitude: "same altitude",
    altDiff: (up: boolean, m: number) => `${up ? "up" : "down"} ${m.toLocaleString()} m`,
  },

  timeline: {
    title: "Timeline",
    centeredOn: (at: string) => `Timeline around ${at}`,
    center: "Center",
    span: "Span",
    spanOf: (days: number) =>
      days >= 365 ? `${Math.round(days / 365)} year${days >= 730 ? "s" : ""}` : days >= 28 ? `${Math.round(days / 30.4)} month${days >= 56 ? "s" : ""}` : `${days} days`,
    earlier: "◀ Earlier",
    later: "Later ▶",
    story: "Story",
    location: "Location",
    moved: (label: string, at: string) => `Moved "${label}" to ${at}`,
    moveFailed: (error: string) => `Could not move: ${error}`,
    gap: "No episodes (squeezed)",
    skipped: (days: number) =>
      days >= 365 ? `${Math.round(days / 365.2)}y` : days >= 61 ? `${Math.round(days / 30.4)}mo` : `${Math.round(days)}d`,
    openInNewTab: "Open in new tab",
    newEpisode: "New episode",
    newEpisodeIn: (story: string) => `Story: ${story}`,
    newEpisodeStart: "Start",
  },

  episodeSheet: {
    characters: (n: number, at: string | null) => `Characters (${n})${at ? ` at ${at}` : ""}`,
    relation: (partner: string, relation: string) => `→ ${partner}: ${relation}`,
    noRelations: "(no relations)",
    toggleRelations: (open: boolean) => (open ? "Hide relations ▴" : "Show relations ▾"),
    mentioned: (names: string) => `Mentioned only: ${names}`,
  },

  stamp: {
    pick: "Pick date & time",
    pickIcon: "📅",
    clear: "Clear",
    set: "Set",
    hour: "H",
    minute: "M",
    second: "S",
    month: (m: number) => `${m}`,
  },

  relations: {
    title: "Character relations",
    of: (name: string) => `Relations of ${name}`,
    fullGraph: "Full graph",
    noKind: "(no kind)",
    year: "Year",
    allTime: "All time",
    relayout: "Re-layout",
    noCharacters: "No characters.",
    noCharacter: (id: number) => `No character with id=${id}.`,
    hintClick: "Click a character to show their relations, or an arrow to show the relation text. Double-click to open the record. Drag characters to move them.",
    hintCounts: (chars: number, rels: number, year: number | null) =>
      `${chars} characters, ${rels} relations${year == null ? "" : ` (active in year ${year})`}. Arrows point from character_1_id to character_2_id.`,
    columns: { subject: "Subject", relation: "Relation", target: "Target", period: "Period" },
    sex: "Sex",
    period: "Period",
    relation: "Relation",
    noRelations: "No relations.",
    noText: "No text.",
    nameKind: (name: unknown, kind: unknown) => `${name} (${kind ?? ""})`,
    sexOf: (sex: string) => `sex: ${sex}`,
    periodOf: (span: string) => `period: ${span}`,
    arrow: (from: string, to: string, relation: string | null) => `${from} → ${to}: ${relation ?? ""}`,
    unknownId: (id: number) => `id=${id}`,
  },
} as const;
