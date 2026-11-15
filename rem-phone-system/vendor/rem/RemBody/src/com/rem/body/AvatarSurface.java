package com.rem.body;

import android.content.Context;
import android.graphics.Canvas;
import android.graphics.Color;
import android.graphics.Paint;
import android.view.View;

/** Explicit empty model slot. No simulated lip sync or claim of a loaded Live2D model. */
public final class AvatarSurface extends View {
    private final Paint paint = new Paint(Paint.ANTI_ALIAS_FLAG);
    private final float density;

    public AvatarSurface(Context context) {
        super(context);
        density = getResources().getDisplayMetrics().density;
        setContentDescription("雷姆形象位置，Live2D 模型尚未接入");
    }

    @Override protected void onDraw(Canvas canvas) {
        super.onDraw(canvas);
        float cx = getWidth() / 2f, cy = getHeight() / 2f;
        paint.setColor(Color.rgb(25, 43, 60));
        canvas.drawCircle(cx, cy, Math.min(getWidth(), getHeight()) * .31f, paint);
        paint.setColor(Color.rgb(162, 216, 242));
        paint.setTextAlign(Paint.Align.CENTER);
        paint.setTextSize(34 * density);
        canvas.drawText("レム", cx, cy, paint);
        paint.setTextSize(13 * density);
        paint.setColor(Color.rgb(168, 182, 196));
        canvas.drawText("等待接入角色模型", cx, cy + 35 * density, paint);
    }
}

