package uy.wingfoil.tracker

import android.content.ContentValues
import android.content.Context
import android.net.Uri
import android.os.Environment
import android.provider.MediaStore
import com.chaquo.python.Python
import com.chaquo.python.android.AndroidPlatform
import org.json.JSONObject
import java.io.File
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale

/** Corre el "Análisis WingFoil Completo" (wingfoil_analisis.py + PDF) con Python dentro de la app. */
object Analysis {

    data class Result(
        val ok: Boolean, val error: String = "", val resumen: String = "",
        val pdf: File? = null, val kml: File? = null, val xlsx: File? = null, val log: String = ""
    )

    fun ensurePython(ctx: Context) {
        if (!Python.isStarted()) Python.start(AndroidPlatform(ctx.applicationContext))
    }

    fun run(ctx: Context, dir: File, wind: Double, fecha: String, sections: Int, excludes: String, sat: Boolean,
            nombre: String = "", lugar: String = "", vientoKn: String = "", comentario: String = "", disciplina: String = "wingfoil"): Result {
        ensurePython(ctx)
        Tiles.cacheDir = File(ctx.filesDir, "tiles").apply { mkdirs() }; Tiles.reset()
        val out = File(dir, "analisis")
        out.deleteRecursively()
        val s = Python.getInstance().getModule("runner")
            .callAttr("run", dir.absolutePath, out.absolutePath, wind, fecha, sections, excludes, sat, nombre, lugar, vientoKn, comentario, disciplina).toString()
        val j = JSONObject(s)
        if (!j.optBoolean("ok")) return Result(false, error = j.optString("error"), log = j.optString("log"))
        return Result(
            true, resumen = j.optString("resumen"), log = j.optString("log"),
            pdf = File(j.getString("pdf")), kml = File(j.getString("kml")), xlsx = File(j.getString("xlsx"))
        )
    }

    /** Copia un archivo a Descargas/WingFoil/<sub> y devuelve su Uri (para ver o compartir). */
    fun saveToDownloads(ctx: Context, f: File, mime: String, sub: String = "Analisis", name: String = f.name): Uri? {
        val res = ctx.contentResolver
        val values = ContentValues().apply {
            put(MediaStore.Downloads.DISPLAY_NAME, name)
            put(MediaStore.Downloads.MIME_TYPE, mime)
            put(MediaStore.Downloads.RELATIVE_PATH, Environment.DIRECTORY_DOWNLOADS + "/WingFoil/" + sub)
            put(MediaStore.Downloads.IS_PENDING, 1)
        }
        val uri = res.insert(MediaStore.Downloads.EXTERNAL_CONTENT_URI, values) ?: return null
        res.openOutputStream(uri)?.use { os -> f.inputStream().use { it.copyTo(os) } }
        values.clear(); values.put(MediaStore.Downloads.IS_PENDING, 0)
        res.update(uri, values, null, null)
        return uri
    }

    /** Fecha DD-MM-AAAA de la sesión (primer punto del track). */
    fun fechaSesion(dir: File): String {
        val sm = Exporter.summary(dir)
        val ms = if (sm.points > 0) sm.firstMs else dir.lastModified()
        return SimpleDateFormat("dd-MM-yyyy", Locale.US).format(Date(ms))
    }
}
