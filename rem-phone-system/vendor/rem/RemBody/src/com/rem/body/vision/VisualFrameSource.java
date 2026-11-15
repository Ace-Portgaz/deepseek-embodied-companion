package com.rem.body.vision;

import android.graphics.Bitmap;

/** Future local/network camera adapters must supply upright, unmirrored frames with monotonic time. */
public interface VisualFrameSource extends AutoCloseable {
    interface Sink {
        boolean readyForFrame();
        /** Ownership transfers to the sink, which must recycle the bitmap. */
        void frame(Bitmap upright, long timestampMs);
        void failed(String code);
    }
    void start(Sink sink);
    void close();
}
