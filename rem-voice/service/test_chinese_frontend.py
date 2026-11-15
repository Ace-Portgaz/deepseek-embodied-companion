"""Regression: common interjections must not switch the deployed voice."""
import unittest
from vendor_genie.Chinese.ChineseG2P import chinese_to_phones

class ChineseFrontendTests(unittest.TestCase):
    def test_interjections_keep_character_phone_alignment(self):
        for text in ('嗯，你好呀。','嗯嗯，我叫大肥鱼。','呣，先休息一下。','哼，才没有一直等你呢。',
                     '欸，我看见你挥手了。','哦，原来是这样呀。','我在这儿，慢慢说。',
                     '你好，我叫大肥鱼，是你的朋友。','今天吃了三碗白米饭。'):
            with self.subTest(text=text):
                normalized,phones,ids,word2ph=chinese_to_phones('。'+text)
                self.assertEqual(len(normalized),len(word2ph))
                self.assertEqual(sum(word2ph),len(ids))
                self.assertTrue(ids)

if __name__=='__main__':unittest.main()
