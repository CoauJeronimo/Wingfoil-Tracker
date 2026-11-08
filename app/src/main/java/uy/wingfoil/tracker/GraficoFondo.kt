package uy.wingfoil.tracker

import android.graphics.Canvas
import android.graphics.Color
import android.graphics.ColorFilter
import android.graphics.Paint
import android.graphics.Path
import android.graphics.PixelFormat
import android.graphics.RectF
import android.graphics.drawable.Drawable

/** Fondo del botón "Analizar": un mini gráfico negro con una línea verde de velocidad. */
class GraficoFondo(private val dens: Float) : Drawable() {
    private val pFondo = Paint(Paint.ANTI_ALIAS_FLAG).apply { color = Color.rgb(8, 10, 12) }
    private val pBorde = Paint(Paint.ANTI_ALIAS_FLAG).apply { style = Paint.Style.STROKE; color = Color.rgb(0, 150, 70); strokeWidth = 1.5f * dens }
    private val pGrilla = Paint().apply { color = Color.rgb(32, 38, 44); strokeWidth = 1f * dens }
    private val pLinea = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        style = Paint.Style.STROKE; color = Color.rgb(0, 230, 90); strokeWidth = 2.4f * dens
        strokeJoin = Paint.Join.ROUND; strokeCap = Paint.Cap.ROUND
    }
    private val pRelleno = Paint(Paint.ANTI_ALIAS_FLAG).apply { color = Color.argb(55, 0, 230, 90) }
    // forma de una sesión: arranque, planeo con altibajos, un par de caídas
    private val ys = floatArrayOf(0.85f, 0.7f, 0.45f, 0.35f, 0.4f, 0.3f, 0.38f, 0.75f, 0.4f, 0.28f, 0.33f, 0.22f, 0.36f, 0.3f, 0.8f, 0.42f, 0.3f, 0.26f, 0.35f, 0.3f)

    override fun draw(c: Canvas) {
        val b = bounds; val r = 6 * dens
        val rf = RectF(b.left + 2 * dens, b.top + 4 * dens, b.right - 2 * dens, b.bottom - 4 * dens)
        c.drawRoundRect(rf, r, r, pFondo)
        for (k in 1..3) { val y = rf.top + rf.height() * k / 4; c.drawLine(rf.left + r, y, rf.right - r, y, pGrilla) }
        for (k in 1..7) { val x = rf.left + rf.width() * k / 8; c.drawLine(x, rf.top + r, x, rf.bottom - r, pGrilla) }
        val p = Path(); val f = Path()
        for ((i, yv) in ys.withIndex()) {
            val x = rf.left + 6 * dens + (rf.width() - 12 * dens) * i / (ys.size - 1)
            val y = rf.top + 5 * dens + (rf.height() - 10 * dens) * yv
            if (i == 0) { p.moveTo(x, y); f.moveTo(x, rf.bottom - 4 * dens); f.lineTo(x, y) } else { p.lineTo(x, y); f.lineTo(x, y) }
        }
        f.lineTo(rf.right - 6 * dens, rf.bottom - 4 * dens); f.close()
        c.drawPath(f, pRelleno); c.drawPath(p, pLinea)
        c.drawRoundRect(rf, r, r, pBorde)
    }
    override fun setAlpha(alpha: Int) {}
    override fun setColorFilter(cf: ColorFilter?) {}
    @Deprecated("Drawable") override fun getOpacity() = PixelFormat.TRANSLUCENT
}
