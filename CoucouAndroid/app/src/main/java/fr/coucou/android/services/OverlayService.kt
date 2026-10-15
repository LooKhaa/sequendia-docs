package fr.coucou.android.services

import android.app.Service
import android.content.Context
import android.content.Intent
import android.content.SharedPreferences
import android.graphics.PixelFormat
import android.os.Binder
import android.os.IBinder
import android.view.Gravity
import android.view.LayoutInflater
import android.view.MotionEvent
import android.view.View
import android.view.WindowManager
import android.widget.FrameLayout
import androidx.compose.ui.platform.ComposeView
import fr.coucou.android.Constants
import fr.coucou.android.MainActivity
import fr.coucou.android.ui.OverlayComposable

class OverlayService : Service() {
    private val binder = LocalBinder()
    private lateinit var windowManager: WindowManager
    private var overlayView: View? = null
    private lateinit var prefs: SharedPreferences
    
    inner class LocalBinder : Binder() {
        fun getService(): OverlayService = this@OverlayService
    }

    override fun onBind(intent: Intent?): IBinder {
        return binder
    }

    override fun onCreate() {
        super.onCreate()
        prefs = getSharedPreferences("coucou", Context.MODE_PRIVATE)
        windowManager = getSystemService(WindowManager::class.java)
        createOverlay()
    }

    private fun createOverlay() {
        if (overlayView != null) return
        
        val params = WindowManager.LayoutParams(
            WindowManager.LayoutParams.WRAP_CONTENT,
            WindowManager.LayoutParams.WRAP_CONTENT,
            if (android.os.Build.VERSION.SDK_INT >= android.os.Build.VERSION_CODES.O) {
                WindowManager.LayoutParams.TYPE_APPLICATION_OVERLAY
            } else {
                WindowManager.LayoutParams.TYPE_PHONE
            },
            WindowManager.LayoutParams.FLAG_NOT_FOCUSABLE or
                    WindowManager.LayoutParams.FLAG_NOT_TOUCH_MODAL,
            PixelFormat.TRANSLUCENT
        ).apply {
            gravity = Gravity.TOP or Gravity.START
            x = 0
            y = 100
        }

        overlayView = ComposeView(this).apply {
            setContent {
                OverlayComposable(
                    onClick = { toggleOverlay() },
                    hasNotifications = false
                )
            }
            
            setOnTouchListener { _, event ->
                when (event.action) {
                    MotionEvent.ACTION_DOWN -> true
                    MotionEvent.ACTION_MOVE -> {
                        params.x = event.rawX.toInt() - width / 2
                        params.y = event.rawY.toInt() - height / 2
                        windowManager.updateViewLayout(this, params)
                        true
                    }
                    else -> false
                }
            }
        }
        
        windowManager.addView(overlayView, params)
    }

    private fun toggleOverlay() {
        val intent = Intent(this, MainActivity::class.java).apply {
            flags = Intent.FLAG_ACTIVITY_NEW_TASK
            putExtra("from_overlay", true)
        }
        startActivity(intent)
    }

    fun showOverlay() {
        if (overlayView == null) {
            createOverlay()
        }
        overlayView?.visibility = View.VISIBLE
    }

    fun hideOverlay() {
        overlayView?.visibility = View.GONE
    }

    fun isOverlayEnabled(): Boolean {
        return prefs.getBoolean(Constants.PREF_OVERLAY_ENABLED, false)
    }

    override fun onDestroy() {
        super.onDestroy()
        overlayView?.let { windowManager.removeView(it) }
        overlayView = null
    }
}
