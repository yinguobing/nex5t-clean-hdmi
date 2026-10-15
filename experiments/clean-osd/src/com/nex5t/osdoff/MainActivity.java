package com.nex5t.osdoff;

import android.app.Activity;
import android.graphics.Color;
import android.os.Bundle;
import android.os.Handler;
import android.util.Log;
import android.view.KeyEvent;
import android.widget.TextView;

import java.lang.reflect.Constructor;
import java.lang.reflect.Method;

/**
 * NEX-5T CleanOSD —— 关掉 HDMI 上的图形层（OSD），然后退出
 *
 * 原理：
 *   APP 在前台时，相机的取景器不渲染（HDMI 显示 APP 的界面，分辨率只有 640x480）。
 *   但相机的 Android 层提供了一个显示控制接口：
 *       com.sony.scalar.hardware.avio.DisplayManager
 *         public void controlGraphicsOutputAll(boolean onoff)
 *   它是「图形层（OSD/UI 覆盖层）输出开关」，**视频层是独立的**。
 *
 *   所以：调用 controlGraphicsOutputAll(false) 关掉图形层 → 然后立刻 finish() 让 APP 窗口消失
 *        → 相机自己的全分辨率实时画面渲染回来，而图形层保持关闭
 *        → HDMI 上就是「全分辨率 + 零 OSD」的干净画面
 *
 *   v1 试过这个调用但 APP 留在前台，结果是全黑（APP 没有视频层）。
 *   这次的关键是「调用完就退出」。
 *
 * 按键：
 *   自动 —— 4 秒后自动退出（保持图形层关闭）
 *   MENU —— 恢复图形层开启再退出（保险，随时能回到正常）
 */
public class MainActivity extends Activity {

    private static final String TAG = "CleanOSD";
    private static final String DM = "com.sony.scalar.hardware.avio.DisplayManager";

    private TextView tv;
    private String text = "";
    private Object dm;
    private Method mAll;

    @Override
    protected void onCreate(Bundle b) {
        super.onCreate(b);
        tv = new TextView(this);
        tv.setTextColor(Color.WHITE);
        tv.setTextSize(16);
        tv.setPadding(24, 24, 24, 24);
        setContentView(tv);

        say("NEX-5T CleanOSD");
        say("----------------------------");

        try {
            Class<?> c = Class.forName(DM);
            Constructor<?> ctor = c.getConstructor();
            dm = ctor.newInstance();
            mAll = c.getMethod("controlGraphicsOutputAll", boolean.class);
            say("DisplayManager OK");
        } catch (Throwable t) {
            say("!! 拿不到 DisplayManager: " + t);
            say("   （此机型不支持，无法继续）");
            return;
        }

        // 打印当前活动的显示设备
        try {
            Method g = Class.forName(DM).getMethod("getActiveDevices");
            Object r = g.invoke(dm);
            StringBuilder s = new StringBuilder("活动显示设备: ");
            if (r instanceof String[]) for (String x : (String[]) r) s.append(x).append(' ');
            say(s.toString());
        } catch (Throwable t) {
            say("getActiveDevices: " + t);
        }

        // ★ 关掉图形层
        setGraphics(false);

        say("");
        say("4 秒后自动退出，保持 OSD 关闭");
        say("按 MENU = 恢复 OSD 再退出");

        new Handler().postDelayed(new Runnable() {
            @Override public void run() {
                say(">>> 退出（OSD 保持关闭）—— 请看 HDMI：应是全分辨率、无 OSD 的画面");
                finish();
            }
        }, 4000);
    }

    private void setGraphics(boolean on) {
        try {
            mAll.invoke(dm, on);
            say(on ? ">>> controlGraphicsOutputAll(true) 已执行（图形层开）"
                   : ">>> controlGraphicsOutputAll(false) 已执行（图形层关）");
        } catch (Throwable t) {
            say("!! controlGraphicsOutputAll(" + on + ") 失败: " + t);
            Throwable cc = t.getCause();
            if (cc != null) say("   原因: " + cc);
        }
    }

    private void say(String s) {
        Log.i(TAG, s);
        text += s + "\n";
        if (tv != null) tv.setText(text);
    }

    @Override
    public boolean onKeyDown(int keyCode, KeyEvent e) {
        if (keyCode == KeyEvent.KEYCODE_MENU) {
            setGraphics(true);          // 保险：恢复
            finish();
            return true;
        }
        return super.onKeyDown(keyCode, e);
    }
}
