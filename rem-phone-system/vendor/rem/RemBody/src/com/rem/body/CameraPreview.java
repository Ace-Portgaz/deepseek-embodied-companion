package com.rem.body;

import android.content.Context;
import android.graphics.Matrix;
import android.graphics.SurfaceTexture;
import android.hardware.camera2.CameraCaptureSession;
import android.hardware.camera2.CameraCharacteristics;
import android.hardware.camera2.CameraDevice;
import android.hardware.camera2.CameraManager;
import android.hardware.camera2.CaptureRequest;
import android.hardware.camera2.params.StreamConfigurationMap;
import android.os.Handler;
import android.util.Size;
import android.view.Surface;
import android.view.TextureView;
import java.util.Collections;

/** Foreground, user-opened preview only. No snapshots, storage or image upload. */
public final class CameraPreview implements TextureView.SurfaceTextureListener {
    public interface Listener { void error(); }
    private final CameraManager manager;
    private final TextureView view;
    private final Handler main;
    private final Listener listener;
    private final int requestedFacing;
    private Size previewSize;
    private int sensorOrientation;
    private CameraDevice camera;
    private CameraCaptureSession session;
    private Surface surface;
    private boolean closed;
    private boolean opening;

    public CameraPreview(Context context, TextureView view, Handler main, int requestedFacing,
                         Listener listener) {
        this.manager = (CameraManager) context.getSystemService(Context.CAMERA_SERVICE);
        this.view = view;
        this.main = main;
        this.listener = listener;
        this.requestedFacing = requestedFacing;
        view.setSurfaceTextureListener(this);
        if (view.isAvailable()) open(view.getSurfaceTexture());
    }

    private void open(SurfaceTexture texture) {
        if (closed || opening || texture == null) return;
        opening = true;
        try {
            String chosen = null;
            for (String id : manager.getCameraIdList()) {
                Integer facing = manager.getCameraCharacteristics(id).get(CameraCharacteristics.LENS_FACING);
                if (facing != null && facing == requestedFacing) {
                    chosen = id; break;
                }
            }
            if (chosen == null) throw new IllegalStateException();
            CameraCharacteristics info = manager.getCameraCharacteristics(chosen);
            StreamConfigurationMap map = info.get(CameraCharacteristics.SCALER_STREAM_CONFIGURATION_MAP);
            if (map == null) throw new IllegalStateException();
            Size[] sizes = map.getOutputSizes(SurfaceTexture.class);
            if (sizes == null || sizes.length == 0) throw new IllegalStateException();
            Size size = sizes[0];
            for (Size option : sizes) {
                if (Math.abs(option.getWidth() * option.getHeight() - 640 * 480)
                        < Math.abs(size.getWidth() * size.getHeight() - 640 * 480)) size = option;
            }
            texture.setDefaultBufferSize(size.getWidth(), size.getHeight());
            previewSize = size;
            Integer sensorRotation = info.get(CameraCharacteristics.SENSOR_ORIENTATION);
            if (sensorRotation == null) throw new IllegalStateException();
            sensorOrientation = sensorRotation;
            updateTransform();
            surface = new Surface(texture);
            manager.openCamera(chosen, new CameraDevice.StateCallback() {
                @Override public void onOpened(CameraDevice value) {
                    if (closed) { value.close(); return; }
                    camera = value;
                    createSession();
                }
                @Override public void onDisconnected(CameraDevice value) { value.close(); fail(); }
                @Override public void onError(CameraDevice value, int error) { value.close(); fail(); }
            }, main);
        } catch (Exception e) { fail(); }
    }

    private void updateTransform() {
        float vw = view.getWidth(), vh = view.getHeight();
        if (previewSize == null || vw <= 0 || vh <= 0) return;
        // Android 11 CameraUtils already rotates the camera SurfaceTexture and
        // mirrors front cameras. In this portrait-only HOME, only correct the
        // aspect ratio; rotating or mirroring again would duplicate that work.
        boolean swapped = sensorOrientation % 180 != 0;
        float bw = swapped ? previewSize.getHeight() : previewSize.getWidth();
        float bh = swapped ? previewSize.getWidth() : previewSize.getHeight();
        float scale = Math.max(vw / bw, vh / bh);
        Matrix transform = new Matrix();
        transform.setScale(bw * scale / vw, bh * scale / vh, vw / 2, vh / 2);
        view.setTransform(transform);
    }

    private void createSession() {
        try {
            camera.createCaptureSession(Collections.singletonList(surface), new CameraCaptureSession.StateCallback() {
                @Override public void onConfigured(CameraCaptureSession value) {
                    if (closed) { value.close(); return; }
                    session = value;
                    try {
                        CaptureRequest.Builder request = camera.createCaptureRequest(CameraDevice.TEMPLATE_PREVIEW);
                        request.addTarget(surface);
                        session.setRepeatingRequest(request.build(), null, main);
                    } catch (Exception e) { fail(); }
                }
                @Override public void onConfigureFailed(CameraCaptureSession value) { value.close(); fail(); }
            }, main);
        } catch (Exception e) { fail(); }
    }

    private void fail() {
        if (!closed) {
            close();
            // open() may run inside TextureView's first draw callback. Defer
            // removal of the preview until that draw has finished.
            main.post(listener::error);
        }
    }
    public void close() {
        closed = true;
        view.setSurfaceTextureListener(null);
        if (session != null) { session.close(); session = null; }
        if (camera != null) { camera.close(); camera = null; }
        if (surface != null) { surface.release(); surface = null; }
    }
    @Override public void onSurfaceTextureAvailable(SurfaceTexture t, int w, int h) { open(t); }
    @Override public void onSurfaceTextureSizeChanged(SurfaceTexture t, int w, int h) { updateTransform(); }
    @Override public boolean onSurfaceTextureDestroyed(SurfaceTexture t) { close(); return true; }
    @Override public void onSurfaceTextureUpdated(SurfaceTexture t) { }
}

