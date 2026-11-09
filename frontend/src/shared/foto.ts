/** Lange Kante nach dem Verkleinern: genug für Details, Upload über Mobilfunk in Sekunden. */
const MAX_KANTE = 2560;
const QUALITAET = 0.85;

export interface VorbereitetesFoto {
  blob: Blob;
  gps?: { lat: number; lon: number };
  aufgenommenAt?: string;
}

/**
 * Liest GPS und Aufnahmezeit aus den EXIF-Daten, bevor das Verkleinern sie entfernt.
 * Viele Android-Handys geben dem Browser Fotos ohne GPS – dann fehlt es eben.
 */
async function leseMetadaten(datei: File): Promise<Omit<VorbereitetesFoto, "blob">> {
  // Erst beim ersten Foto laden – hält das Melder-Formular klein.
  const { default: exifr } = await import("exifr/dist/lite.esm.mjs");
  // Ohne Filter: `pick` wirft in der lite-Variante von exifr 7.1.3 einen TypeError.
  const exif = await exifr.parse(datei).catch(() => undefined);
  const meta: Omit<VorbereitetesFoto, "blob"> = {};
  if (Number.isFinite(exif?.latitude) && Number.isFinite(exif?.longitude)) {
    meta.gps = { lat: exif.latitude, lon: exif.longitude };
  }
  const zeit = exif?.DateTimeOriginal;
  if (zeit instanceof Date && !Number.isNaN(zeit.getTime())) meta.aufgenommenAt = zeit.toISOString();
  return meta;
}

async function ladeBild(datei: File): Promise<CanvasImageSource & { width: number; height: number }> {
  try {
    return await createImageBitmap(datei, { imageOrientation: "from-image" });
  } catch {
    // Fallback für ältere Browser; <img> berücksichtigt die EXIF-Drehung ebenfalls.
    const url = URL.createObjectURL(datei);
    try {
      const img = new Image();
      img.src = url;
      await img.decode();
      return img;
    } finally {
      URL.revokeObjectURL(url);
    }
  }
}

async function verkleinere(datei: File): Promise<Blob> {
  const bild = await ladeBild(datei);
  const faktor = Math.min(1, MAX_KANTE / Math.max(bild.width, bild.height));
  const canvas = document.createElement("canvas");
  canvas.width = Math.round(bild.width * faktor);
  canvas.height = Math.round(bild.height * faktor);
  canvas.getContext("2d")!.drawImage(bild, 0, 0, canvas.width, canvas.height);
  if ("close" in bild) bild.close();
  return new Promise((ok, fehler) =>
    canvas.toBlob((b) => (b ? ok(b) : fehler(new Error("Foto konnte nicht verkleinert werden"))), "image/jpeg", QUALITAET),
  );
}

export async function bereiteFotoVor(datei: File): Promise<VorbereitetesFoto> {
  // Fehlende oder kaputte Metadaten sind kein Grund, das Foto abzulehnen.
  const [meta, blob] = await Promise.all([leseMetadaten(datei).catch(() => ({})), verkleinere(datei)]);
  return { blob, ...meta };
}
