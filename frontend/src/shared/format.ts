const zeit = new Intl.DateTimeFormat("de-DE", { hour: "2-digit", minute: "2-digit", second: "2-digit" });
const datumZeit = new Intl.DateTimeFormat("de-DE", { dateStyle: "short", timeStyle: "medium" });

export const fmtZeit = (iso: string | null) => (iso ? zeit.format(new Date(iso)) : "–");
export const fmtDatumZeit = (iso: string | null) => (iso ? datumZeit.format(new Date(iso)) : "–");
export const fmtSek = (s: number) => `${s.toFixed(1).replace(".", ",")} s`;
