package uy.wingfoil.tracker

import android.content.ContentValues
import android.content.Context
import android.net.Uri
import android.os.Environment
import android.provider.MediaStore
import java.io.File
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale
import java.util.TimeZone
import java.util.zip.ZipEntry
import java.util.zip.ZipOutputStream

object Exporter {

    data class Summary(val points: Int, val firstMs: Long, val lastMs: Long)

    fun summary(dir: File): Summary {
        var n = 0; var first = 0L; var last = 0L
        try {
            File(dir, "Location.csv").useLines { lines ->
                lines.drop(1).forEach { line ->
                    val t = line.substringBefore(',').toLongOrNull() ?: return@forEach
                    val ms = t / 1_000_000L
                    if (n == 0) first = ms
                    last = ms; n++
                }
            }
        } catch (_: Exception) { }
        return Summary(n, first, last)
    }

    /** Arma el ZIP (Location.csv + Metadata.csv + track.gpx) en Descargas/WingFoil y devuelve su Uri. */
    fun zipToDownloads(ctx: Context, dir: File): Uri? {
        SessionInfo.deleteDownloads(ctx, dir, "zip")          // reemplaza el ZIP anterior de esta sesión
        val res = ctx.contentResolver
        val values = ContentValues().apply {
            put(MediaStore.Downloads.DISPLAY_NAME, dir.name + ".zip")
            put(MediaStore.Downloads.MIME_TYPE, "application/zip")
            put(MediaStore.Downloads.RELATIVE_PATH, Environment.DIRECTORY_DOWNLOADS + "/WingFoil")
            put(MediaStore.Downloads.IS_PENDING, 1)
        }
        val uri = res.insert(MediaStore.Downloads.EXTERNAL_CONTENT_URI, values) ?: return null
        res.openOutputStream(uri)?.use { os ->
            ZipOutputStream(os).use { z ->
                for (fn in listOf("Location.csv", "Metadata.csv", "TotalAcceleration.csv")) {
                    val f = File(dir, fn)
                    if (f.exists()) {
                        z.putNextEntry(ZipEntry(fn))
                        f.inputStream().use { it.copyTo(z) }
                        z.closeEntry()
                    }
                }
                z.putNextEntry(ZipEntry("track.gpx"))
                z.write(gpx(dir).toByteArray())
                z.closeEntry()
            }
        }
        values.clear()
        values.put(MediaStore.Downloads.IS_PENDING, 0)
        res.update(uri, values, null, null)
        SessionInfo.addDownload(dir, uri, "zip")
        return uri
    }

    /**
     * GPX "estándar" (lo aceptan Relive, Strava, Garmin, Google Earth…): un solo tramo, horas en segundos
     * enteros sin milisegundos, bloque de metadatos con la hora de inicio, sin altitud (en el agua es ruido)
     * y sin puntos con precisión peor que 20 m.
     */
    fun gpx(dir: File): String {
        val iso = SimpleDateFormat("yyyy-MM-dd'T'HH:mm:ss'Z'", Locale.US).apply { timeZone = TimeZone.getTimeZone("UTC") }
        val nombre = SessionInfo.get(dir, "nombre").ifEmpty { dir.name }
            .replace("&", "y").replace("<", "").replace(">", "")
        val pts = StringBuilder()
        var last = -1L; var first = -1L
        File(dir, "Location.csv").useLines { lines ->
            lines.drop(1).forEach { line ->
                val c = line.split(',')
                if (c.size < 11) return@forEach
                val acc = c[5].toDoubleOrNull()
                if (acc != null && acc > 20) return@forEach
                val sec = (c[0].toLongOrNull() ?: return@forEach) / 1_000_000_000L
                val la = c[10].toDoubleOrNull() ?: return@forEach; val lo = c[9].toDoubleOrNull() ?: return@forEach
                if (sec <= last) return@forEach
                if (first < 0) first = sec
                last = sec
                pts.append("<trkpt lat=\"").append(String.format(Locale.US, "%.7f", la)).append("\" lon=\"")
                    .append(String.format(Locale.US, "%.7f", lo)).append("\"><time>").append(iso.format(Date(sec * 1000)))
                    .append("</time></trkpt>\n")
            }
        }
        val sb = StringBuilder()
        sb.append("<?xml version=\"1.0\" encoding=\"UTF-8\"?>\n")
        sb.append("<gpx version=\"1.1\" creator=\"Wingfoil and PW Tracker\" xmlns=\"http://www.topografix.com/GPX/1/1\" ")
        sb.append("xmlns:xsi=\"http://www.w3.org/2001/XMLSchema-instance\" ")
        sb.append("xsi:schemaLocation=\"http://www.topografix.com/GPX/1/1 http://www.topografix.com/GPX/1/1/gpx.xsd\">\n")
        sb.append("<metadata><name>").append(nombre).append("</name>")
        if (first > 0) sb.append("<time>").append(iso.format(Date(first * 1000))).append("</time>")
        sb.append("</metadata>\n<trk><name>").append(nombre).append("</name><trkseg>\n")
        sb.append(pts)
        sb.append("</trkseg></trk></gpx>\n")
        return sb.toString()
    }
}
