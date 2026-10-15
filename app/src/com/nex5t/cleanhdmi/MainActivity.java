package com.nex5t.cleanhdmi;

import android.app.Activity;
import android.graphics.Color;
import android.graphics.PixelFormat;
import android.hardware.Camera;
import android.os.Bundle;
import android.util.Log;
import android.view.KeyEvent;
import android.view.SurfaceHolder;
import android.view.SurfaceView;
import android.view.View;
import android.view.ViewGroup;
import android.widget.FrameLayout;
import android.widget.TextView;

import java.lang.reflect.Method;

/**
 * NEX-5T 干净 HDMI
 *
 * 原理：PMCA 应用运行时占屏，相机的取景器渲染停止 —— 相机的 OSD 根本不参与渲染。
 *       APP 只要把实时画面显示出来、上面什么都不画，HDMI 上就是干净的实时画面。
 *
 * 调用序列（照抄胶片坊，已验证）：
 *   onCreate        : SurfaceView → getHolder → setType(PUSH_BUFFERS) → setFormat(RGBA_8888)
 *   onResume        : CameraEx.open(0, null) → getNormalCamera() → holder.addCallback(this)
 *   surfaceCreated  : setPreviewDisplay(holder) → startPreview()
 *   MENU            : release + finish
 *
 * 画面默认是纯净的，不显示任何文字。
 * 只有在出错时才会把错误显示到画面上（诊断同时写入 logcat，tag = CleanHdmi）。
 */
public class MainActivity extends Activity implements SurfaceHolder.Callback {

    private static final String TAG = "CleanHdmi";
    private static final String CAMERA_EX = "com.sony.scalar.hardware.CameraEx";
    private static final String OPEN_OPTIONS = "com.sony.scalar.hardware.CameraEx$OpenOptions";

    // ---- 放行名单：只有这些按键交给相机自己处理 ----
    // 扫描码来自固件 com.sony.scalar.sysutil.ScalarInput 的 static_values 常量表。
    //
    // ⚠️ 重要教训：那套常量值只在「确定键(0xe8)」和「播放键(0xcf)」上被交叉验证过
    //    （胶片坊里正是拿这两个值比较 getScanCode()），**不能推广到所有按键**。
    //    曾经据此把「菜单 = 0x202」写死，结果菜单键判断不命中、事件被放行给相机系统，
    //    表现为"MENU 退出失效、相机的菜单被打开"。
    //
    //    所以现在改成**白名单**逻辑：只明确放行拍摄必需的键，其余一律退出。
    //    这样即使某个键的扫描码猜错了，最坏结果也只是"多退出了一次"，而不会死循环。
    private static final int SCAN_S1 = 0x204;   // ISV_KEY_S1_1  快门半按（对焦）
    private static final int SCAN_S2 = 0x206;   // ISV_KEY_S2    快门全按（拍摄）

    private SurfaceView surface;
    private SurfaceHolder holder;
    private TextView errorView;          // 平时隐藏，只在出错时显示
    private Camera camera;
    private Object cameraEx;
    private String errorText = "";
    private boolean surfaceReady = false;
    private boolean previewing = false;
    private boolean callbackAdded = false;

    @Override
    protected void onCreate(Bundle b) {
        super.onCreate(b);

        FrameLayout root = new FrameLayout(this);
        surface = new SurfaceView(this);
        root.addView(surface, new FrameLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.MATCH_PARENT));
        errorView = new TextView(this);
        errorView.setTextColor(Color.WHITE);
        errorView.setTextSize(15);
        errorView.setPadding(20, 20, 20, 20);
        errorView.setVisibility(View.GONE);      // 默认不显示
        root.addView(errorView);
        setContentView(root);

        holder = surface.getHolder();
        // Android 4.0 相机预览必须用 PUSH_BUFFERS，缺这行 startPreview 必失败
        holder.setType(SurfaceHolder.SURFACE_TYPE_PUSH_BUFFERS);
        // 32 位色（默认 RGB_565 只有 16 位，容易出色带）
        try {
            holder.setFormat(PixelFormat.RGBA_8888);
        } catch (Throwable t) {
            Log.i(TAG, "setFormat 失败，用默认: " + t);
        }
    }

    @Override
    protected void onResume() {
        super.onResume();
        openCamera();
        if (!callbackAdded) {
            holder.addCallback(this);
            callbackAdded = true;
        }
        if (surfaceReady) startPreview();
    }

    private void openCamera() {
        if (camera != null) return;
        try {
            Class<?> c = Class.forName(CAMERA_EX);
            Class<?> oo = Class.forName(OPEN_OPTIONS);
            Method open = c.getMethod("open", int.class, oo);
            cameraEx = open.invoke(null, 0, null);
            Method getNormal = c.getMethod("getNormalCamera");
            camera = (Camera) getNormal.invoke(cameraEx);
            Log.i(TAG, "相机已打开: " + (camera != null));
        } catch (Throwable t) {
            fail("打开相机失败: " + t);
        }
    }

    private void startPreview() {
        if (camera == null || previewing || !surfaceReady) return;
        try {
            camera.setPreviewDisplay(holder);
            camera.startPreview();
            previewing = true;
            Log.i(TAG, "startPreview 成功");
        } catch (Throwable t) {
            // 回退：用默认色深再试一次
            try {
                holder.setFormat(PixelFormat.OPAQUE);
                camera.setPreviewDisplay(holder);
                camera.startPreview();
                previewing = true;
                Log.i(TAG, "退回默认色深后 startPreview 成功");
            } catch (Throwable t2) {
                fail("startPreview 失败: " + t + " / 退回后: " + t2);
            }
        }
    }

    @Override public void surfaceCreated(SurfaceHolder h) {
        surfaceReady = true;
        startPreview();
    }

    @Override public void surfaceChanged(SurfaceHolder h, int fmt, int w, int hh) {
        Log.i(TAG, "surfaceChanged: " + w + "x" + hh + " format=" + fmt);
    }

    @Override public void surfaceDestroyed(SurfaceHolder h) {
        surfaceReady = false;
        stopPreview();
    }

    private void stopPreview() {
        if (camera != null && previewing) {
            try { camera.stopPreview(); } catch (Throwable ignored) { }
            previewing = false;
        }
    }

    private void release() {
        stopPreview();
        if (camera != null) {
            try { camera.release(); } catch (Throwable ignored) { }
            camera = null;
        }
        if (cameraEx != null) {
            try { cameraEx.getClass().getMethod("release").invoke(cameraEx); } catch (Throwable ignored) { }
            cameraEx = null;
        }
    }

    /**
     * 一离开前台就**彻底释放相机**（不只是停预览）。
     *
     * 原来的实现只在 onDestroy 里释放，等于整个运行期间相机一直被 APP 占着。
     * 问题：关机流程想停相机时拿不到，就可能超时 → 直接硬断电，
     * 表现为「镜头没缩回去就断电」（实机复现过）。
     *
     * 改成进 onPause 就 release()，让系统任何时候想用相机都能立刻拿到。
     * 回到前台时 onResume 会重新打开相机，用户无感。
     */
    @Override
    protected void onPause() {
        super.onPause();
        release();                       // ★ 彻底释放：停预览 + camera.release() + CameraEx.release()
        if (callbackAdded) {
            holder.removeCallback(this);
            callbackAdded = false;
        }
    }

    @Override
    protected void onStop() {
        super.onStop();
        release();                       // 再兜一次，防止某些路径只走 onStop
    }

    @Override
    protected void onDestroy() {
        super.onDestroy();
        release();
    }

    /** 只在出错时才把信息显示到画面上（正常运行时画面是纯净的） */
    private void fail(String s) {
        Log.e(TAG, s);
        errorText += s + "\n";
        if (errorView != null) {
            errorView.setVisibility(View.VISIBLE);
            errorView.setText(errorText);
        }
    }

    /**
     * 按键处理 —— **白名单放行，其余一律退出**。
     *
     * 【为什么需要它】APP 运行期间独占了相机。按下「播放图像」「菜单」「MOVIE」这类
     * 会切换显示界面的键时，相机系统会尝试接管显示，与 APP 争抢相机
     * → 黑屏 → 系统重启 → 约 20 秒后才恢复（实机复现过）。
     * 而相机的物理键是相机系统直接处理的，光"吞事件"挡不住，必须抢先把相机释放掉。
     *
     * 【为什么不按键表精确区分】试过。扫描码常量只在确定键/播放键上验证过，
     * 推广到菜单键就翻车了（MENU 退出失效）。**白名单是更稳的设计**：
     * 猜错的最坏结果是"多退出一次"，而不是死循环。
     *
     * 【实现要点】
     *   1) 用 dispatchKeyEvent —— 比 onKeyDown 更早拿到事件，也更全
     *   2) 用 getScanCode() 识别相机物理键（keyCode 认不出来），但**不作为唯一依据**
     */
    @Override
    public boolean dispatchKeyEvent(KeyEvent e) {
        if (e.getAction() != KeyEvent.ACTION_DOWN) {
            return super.dispatchKeyEvent(e);
        }
        int key  = e.getKeyCode();
        int scan = e.getScanCode();
        Log.i(TAG, "按键 keyCode=" + key + " scanCode=0x" + Integer.toHexString(scan));

        // 电源键：先释放相机，但**放行事件**（拦了就没法关机）
        if (key == KeyEvent.KEYCODE_POWER) {
            Log.i(TAG, "  → 电源键，释放相机后放行");
            release();
            finish();
            return super.dispatchKeyEvent(e);
        }

        // 白名单：快门（半按对焦 / 全按拍摄）交给相机自己处理
        if (scan == SCAN_S1 || scan == SCAN_S2) {
            Log.i(TAG, "  → 快门键，放行给相机");
            return super.dispatchKeyEvent(e);
        }

        // 其余按键一律退出并释放相机，避免与相机系统争抢显示
        Log.i(TAG, "  → 退出并释放相机");
        release();
        finish();
        return true;
    }

    @Override
    public void onBackPressed() {
        release();
        finish();
    }
}
