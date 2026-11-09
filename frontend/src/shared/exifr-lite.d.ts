// Die schlanke Variante von exifr (JPEG/HEIC, EXIF + GPS) hat dieselbe API wie das Hauptpaket.
declare module "exifr/dist/lite.esm.mjs" {
  export * from "exifr";
  export { default } from "exifr";
}
