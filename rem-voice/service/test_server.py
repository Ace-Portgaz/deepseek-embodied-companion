import unittest
from unittest.mock import Mock
from server import speak

class SpeechBounds(unittest.TestCase):
    def test_premature_semantics_retry_with_original_deadline(self):
        engine=Mock();engine.language='zh'
        engine.synthesize.side_effect=[RuntimeError('Premature semantic stop'),(bytes(3200),{})]
        audio,_=speak(engine,'你好。')
        self.assertEqual(audio,bytes(3200))
        self.assertEqual(engine.synthesize.call_count,2)
        self.assertLessEqual(engine.synthesize.call_args_list[1].kwargs['timeout'],engine.synthesize.call_args_list[0].kwargs['timeout'])

    def test_retry_limit_and_other_failures(self):
        for error,count in [('Premature semantic stop',3),('Incomplete semantic sequence',1)]:
            engine=Mock();engine.synthesize.side_effect=RuntimeError(error)
            with self.assertRaises(RuntimeError):speak(engine,'你好。')
            self.assertEqual(engine.synthesize.call_count,count)

    def test_chinese_clause_splitting_preserves_text(self):
        engine=Mock();engine.language='zh';engine.synthesize.return_value=(bytes(3200),{})
        text='你好，我叫大肥鱼；很高兴见到你。'
        speak(engine,text)
        self.assertEqual([c.args[0] for c in engine.synthesize.call_args_list],['你好，','我叫大肥鱼；','很高兴见到你。'])

    def test_long_text_split_and_bounded(self):
        engine=Mock();engine.synthesize.return_value=(bytes(3200),{})
        audio,_=speak(engine,'あ'*110+'。はい。')
        self.assertLessEqual(max(len(c.args[0]) for c in engine.synthesize.call_args_list),45)
        self.assertEqual(''.join(c.args[0] for c in engine.synthesize.call_args_list),'あ'*110+'。はい。')
        self.assertGreater(len(audio),0)

    def test_invalid_text_never_invokes_model(self):
        for value in ('', ' ', 'a'*161,{},None):
            engine=Mock()
            with self.assertRaises(ValueError):speak(engine,value)
            engine.synthesize.assert_not_called()

    def test_invalid_pcm_and_total_duration_rejected(self):
        for pcm,error in [(b'',ValueError),(b'a',ValueError),(bytes(960002),TimeoutError)]:
            engine=Mock();engine.synthesize.return_value=(pcm,{})
            with self.assertRaises(error):speak(engine,'はい。')

if __name__=='__main__':unittest.main()
