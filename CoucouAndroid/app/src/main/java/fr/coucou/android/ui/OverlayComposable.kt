package fr.coucou.android.ui

import androidx.compose.animation.AnimatedVisibility
import androidx.compose.animation.core.animateDpAsState
import androidx.compose.animation.fadeIn
import androidx.compose.animation.fadeOut
import androidx.compose.animation.slideInVertically
import androidx.compose.animation.slideOutVertically
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp

@Composable
fun OverlayComposable(
    onClick: () -> Unit,
    hasNotifications: Boolean = false
) {
    var expanded by remember { mutableStateOf(false) }
    val height by animateDpAsState(targetValue = if (expanded) 120.dp else 34.dp)
    
    Column(
        modifier = Modifier
            .width(if (expanded) 320.dp else 112.dp)
            .height(height)
            .background(Color(0xFF020204), RoundedCornerShape(24.dp))
            .clickable { expanded = !expanded }
            .padding(horizontal = 14.dp, vertical = 8.dp),
        verticalArrangement = Arrangement.Center,
        horizontalAlignment = Alignment.CenterHorizontally
    ) {
        Row(
            verticalAlignment = Alignment.CenterVertically,
            horizontalArrangement = Arrangement.Center
        ) {
            Box(
                modifier = Modifier
                    .size(7.dp)
                    .background(
                        if (hasNotifications) Color(0xFFFF6B7D) else Color(0xFF4FD6A0),
                        RoundedCornerShape(50)
                    )
            )
            Spacer(Modifier.width(8.dp))
            Text(
                if (expanded) "COUCOU" else "coucou",
                color = Color.White,
                fontSize = 12.sp,
                fontWeight = FontWeight.SemiBold
            )
            if (!expanded && hasNotifications) {
                Spacer(Modifier.width(7.dp))
                Text("1", color = Color(0xFF7AA2FF), fontSize = 11.sp)
            }
        }
        
        AnimatedVisibility(
            visible = expanded,
            enter = fadeIn() + slideInVertically(initialOffsetY = { -it / 2 }),
            exit = fadeOut() + slideOutVertically(targetOffsetY = { -it / 2 })
        ) {
            Spacer(Modifier.height(8.dp))
            Text(
                "Appuyez pour ouvrir",
                color = Color(0xFF8A93A6),
                fontSize = 11.sp
            )
        }
    }
}
