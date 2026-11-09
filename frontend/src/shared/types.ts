export type Rolle = "melder" | "elw" | "beobachter";
export type Status = "neu" | "gesichtet" | "erledigt";
export type Feld = "an" | "inhalt";

export interface Me {
  name: string;
  rolle: Rolle;
  funktion: string;
  einsatz: string;
}

export interface AktiveAnmeldung {
  name: string;
  rolle: Rolle;
  funktion: string;
  angemeldet_at: string;
}

export interface Funktion {
  id: number;
  name: string;
}

export interface FeldEingabe {
  art: "text" | "sprache";
  rohtext?: string;
  modell?: string;
}

export interface NachrichtCreate {
  an: string;
  inhalt: string;
  erfasst_at?: string;
  eingabe: Partial<Record<Feld, FeldEingabe>>;
  /** IDs vorläufig abgelegter Aufnahmen und Fotos */
  anhaenge: string[];
  /** Je Formular einmal erzeugt: erneutes Senden nach verlorener Antwort legt keine zweite Nachricht an. */
  sende_id: string;
}

export interface Anhang {
  id: number;
  art: "audio" | "foto";
  feld: Feld | null;
  dateiname: string;
  mime: string;
  groesse: number;
  meta: Record<string, unknown>;
}

export interface Nachricht {
  id: number;
  lfd_nr: number;
  von_funktion: string;
  von_name: string;
  an: string;
  an_funktion_id: number | null;
  inhalt: string;
  status: Status;
  erfasst_at: string | null;
  eingang_at: string;
  eingabe: Partial<Record<Feld, FeldEingabe>>;
  anhaenge: Anhang[];
  /** Nur in der Antwort auf das Absenden */
  fehlende_anhaenge?: number;
}

export interface AuditEvent {
  aktion: string;
  funktion: string;
  name: string;
  zeitpunkt: string;
  aenderungen: Record<string, { alt: unknown; neu: unknown }>;
}

export interface FotoUpload {
  foto_id: string;
  breite: number;
  hoehe: number;
}

export interface Vorschlag {
  funktion_id: number;
  name: string;
  score: number;
}

export interface TranscribeResult {
  text: string;
  rohtext: string;
  modell: string;
  audio_sekunden: number;
  verarbeitung_sekunden: number;
  warte_sekunden: number;
  vorschlaege: Vorschlag[];
  aufnahme_id: string | null;
}
