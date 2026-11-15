package com.rem.body.character;

/** A bounded semantic event, never arbitrary web content or a hidden microphone turn. */
public final class TouchPolicy {
    private long last=-10000;
    public static String label(String region){
        if(region==null)return null;
        switch(region){case "head":return "头顶和头发";case "face":return "脸颊";case "hand":return "手和手臂";
            case "body":return "上身和衣服";case "legs":return "腿和脚";case "tail":return "尾巴";default:return null;}
    }
    public boolean accept(String region,long now,boolean busy,boolean foreground){
        if(label(region)==null||busy||!foreground||now-last<8000)return false;
        last=now;return true;
    }
    public static String prompt(String region){
        String name=label(region);if(name==null)throw new IllegalArgumentException("Body region");
        return "【屏幕互动事件，不是语音转写】用户刚刚轻触了你屏幕形象的「"+name+"」。"
            +"请结合当前人设和说话习惯，以朋友口吻对这次触碰直接说一句自然的中文回应，约二十到四十字。"
            +"要体现被点到的部位，不要每次重复同一句。只输出要说的话，不要括号动作或技术说明。"
            +"这是手机屏幕上的轻触，不要编造现实身体感受、痛感、未发生的连续动作或用户说过的话。";
    }
}
