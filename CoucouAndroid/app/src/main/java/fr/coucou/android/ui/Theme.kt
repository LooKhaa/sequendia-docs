package fr.coucou.android.ui

import androidx.compose.foundation.isSystemInDarkTheme
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.darkColorScheme
import androidx.compose.material3.dynamicDarkColorScheme
import androidx.compose.material3.dynamicLightColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext

private val DarkColorScheme = darkColorScheme(
    primary = Color(0xFF7AA2FF),
    background = Color(0xFF08090D),
    surface = Color(0xFF151923),
    onPrimary = Color.White,
    onBackground = Color(0xFFEEF1F6),
    onSurface = Color(0xFFEEF1F6),
    secondary = Color(0xFF4FD6A0),
    onSecondary = Color.Black,
    error = Color(0xFFFF6B7D),
    onError = Color.White,
    tertiary = Color(0xFFFFB454)
)

@Composable
fun CoucouTheme(
    darkTheme: Boolean = isSystemInDarkTheme(),
    content: @Composable () -> Unit
) {
    val colorScheme = DarkColorScheme
    
    MaterialTheme(
        colorScheme = colorScheme,
        typography = Typography,
        content = content
    )
}
