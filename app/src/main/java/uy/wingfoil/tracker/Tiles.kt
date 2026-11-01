package uy.wingfoil.tracker

import java.io.File
import java.net.HttpURLConnection
import java.net.URL
import java.security.MessageDigest

/**
 * Descarga de imágenes satelitales para el mapa del PDF (la llama Python desde wf_pdf.py).
 * Cada imagen queda guardada en caché: si se vuelve a analizar en la misma zona, funciona sin internet.
 */
object Tiles {
    @JvmStatic var cacheDir: File? = null
    @Volatile private var offline = false   // si una descarga falla por red, no se insiste con las demás

    @JvmStatic
    fun get(url: String): ByteArray? {
        val dir = cacheDir
        val key = MessageDigest.getInstance("SHA-1").digest(url.toByteArray()).joinToString("") { "%02x".format(it) }
        val f = dir?.let { File(it, "$key.jpg") }
        if (f != null && f.exists() && f.length() > 0) return f.readBytes()
        if (offline) return null
        return try {
            val c = URL(url).openConnection() as HttpURLConnection
            c.connectTimeout = 6000; c.readTimeout = 10000
            c.setRequestProperty("User-Agent", "WingfoilTracker/1.2 (Android)")
            if (c.responseCode != 200) { c.disconnect(); return null }
            val b = c.inputStream.use { it.readBytes() }
            c.disconnect()
            if (f != null && b.size > 100) try { f.writeBytes(b) } catch (_: Exception) { }
            b
        } catch (e: java.io.IOException) {
            offline = true
            null
        }
    }

    @JvmStatic fun reset() { offline = false }
}
