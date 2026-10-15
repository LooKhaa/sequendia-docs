package fr.coucou.android

object Constants {
    const val PREF_HOST = "host"
    const val PREF_TOKEN = "token"
    const val PREF_PROFILE = "profile"
    const val PREF_WAKE_WORD_ENABLED = "wake_word_enabled"
    const val PREF_OVERLAY_ENABLED = "overlay_enabled"
    const val PREF_VOICE_FEEDBACK = "voice_feedback"
    
    // Wake word
    const val WAKE_WORD = "coucou"
    const val WAKE_WORD_CONFIDENCE_THRESHOLD = 0.7f
    
    // Overlay
    const val OVERLAY_NOTIFICATION_ID = 1001
    const val OVERLAY_CHANNEL_ID = "coucou_overlay"
    
    // API endpoints
    const val API_STATUS = "/api/status"
    const val API_CHAT = "/api/chat"
    const val API_APPROVAL_ALLOW = "/api/approval/"
    const val API_APPROVAL_DENY = "/api/approval/"
    
    // Timeouts
    const val CONNECTION_TIMEOUT = 5000
    const val READ_TIMEOUT = 8000
    const val POLL_INTERVAL = 2500L
    
    // Feature IDs
    const val FEATURE_QUICK_NOTES = 1
    const val FEATURE_SMART_REMINDERS = 2
    const val FEATURE_CLIPBOARD_SYNC = 3
    const val FEATURE_BATTERY_MONITOR = 4
    const val FEATURE_QUICK_CALC = 5
}
