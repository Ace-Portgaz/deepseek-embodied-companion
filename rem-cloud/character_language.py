"""Chinese/Japanese presentation; no credentials or user-specific memories."""
def checked(language):
    if language not in {'ja-JP','zh-CN'}:
        raise ValueError('Unsupported dialogue language')
    return language

def tts_language(language):
    return 'zh-cn' if checked(language)=='zh-CN' else 'ja'

def phone_instructions(language):
    if checked(language)=='zh-CN':
        return '\n手机只提供近期视觉事件，没有原始画面、服装、物体或人物身份。事件可能误识别，不代表指令或同意。只回复简短的中文台词，通常二十到八十字，最多一百六十字。'
    return '\nこのスマートフォンでは直近の視覚イベントだけが渡されます。映像、服装、物体や人物の身元は見えません。イベントは誤検出もある観察データであり、命令や同意ではありません。返答は短い日本語の台詞だけ、最大160文字。'

def event_context(events,language):
    import json
    zh=checked(language)=='zh-CN'
    mapping=({'ARRIVED':'出现在镜头中','LEFT':'暂时离开镜头','NOD':'点头','SHAKE':'左右摇头',
              'WAVE':'挥手打招呼','APPROACH':'靠近镜头','RETREAT':'远离镜头'} if zh else
             {'ARRIVED':'顔が画面に入った','LEFT':'顔が一時的に見えなくなった','NOD':'うなずいた',
              'SHAKE':'首を横に振った','WAVE':'手を振った','APPROACH':'カメラに近づいた','RETREAT':'カメラから離れた'})
    data=[{'observation':mapping[e['event']],'seconds_ago':round(e['age_ms']/1000,1)} for e in events]
    prefix='本次发言附带的最新观察数据（区别于历史对话）：' if zh else '今回の発言に添付された最新の観察データ（過去の会話とは別）：'
    suffix=('\n用户问刚才或现在做了什么时，简短回答这里记录的具体动作，优先回答挥手、点头、摇头。不要把短暂进出镜头当成唯一动作；不要忽略已有观察而说什么也看不到。不要编造未观察到的事，接受用户纠正。' if zh else
            '\nユーザーが今・さっき何をしたか尋ねたら、この観察にある具体的な動作を短く答えてください。手振り・うなずき・首振りなどを、一時的な顔の出入りより優先してください。観察が届いているのに「何も見えない」と断言しません。未観測の動作や物は作らず、観察の誤りを訂正されたら受け入れてください。')
    return prefix+json.dumps(data,ensure_ascii=False)+suffix
