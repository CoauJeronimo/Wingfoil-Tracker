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
        return uri
    }

    private fun gpx(dir: File): String {
        val iso = SimpleDateFormat("yyyy-MM-dd'T'HH:mm:ss.SSS'Z'", Locale.US).apply { timeZone = TimeZone.getTimeZone("UTC") }
        val sb = StringBuilder()
        sb.append("<?xml version=\"1.0\" encoding=\"UTF-8\"?>\n")
        sb.append("<gpx version=\"1.1\" creator=\"Wingfoil Tracker\" xmlns=\"http://www.topografix.com/GPX/1/1\">\n")
        sb.append("<trk><name>").append(dir.name).append("</name><trkseg>\n")
        var prev = 0L
        File(dir, "Location.csv").useLines { lines ->
            lines.drop(1).forEach { line ->
                val c = line.split(',')
                if (c.size < 11) return@forEach
                val ms = (c[0].toLongOrNull() ?: return@forEach) / 1_000_000L
                if (prev > 0 && ms - prev > 30_000L) sb.append("</trkseg><trkseg>\n")   // corte largo = segmento nuevo
                sb.append("<trkpt lat=\"").append(c[10]).append("\" lon=\"").append(c[9]).append("\">")
                if (c[8].isNotEmpty()) sb.append("<ele>").append(c[8]).append("</ele>")
                sb.append("<time>").append(iso.format(Date(ms))).append("</time></trkpt>\n")
                prev = ms
            }
        }
        sb.append("</trkseg></trk></gpx>\n")
        return sb.toString()
    }
}
