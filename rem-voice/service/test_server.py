import unittest
from unittest.mock import Mock
from server import speak

class SpeechBounds(unittest.TestCase):
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
