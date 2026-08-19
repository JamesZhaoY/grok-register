"""验证码提取的回归测试。

xAI 邮件模板换过一次格式：旧版验证码含字母（I6R-B2W），新版是纯数字
（SpaceXAI confirmation code: 688-106）。提取逻辑必须两者都认，同时
不能把 CSS 类名、数字区间误判成验证码。
"""

import unittest

from backend.mailbox.utilities import extract_verification_code, strip_html


class ExtractVerificationCodeTests(unittest.TestCase):
    def test_new_all_digit_code_in_subject(self):
        # 2026-08-19 事故的原始主题：纯数字验证码曾被"必须含字母"的守卫丢弃
        subject = "SpaceXAI confirmation code: 688-106"
        self.assertEqual(extract_verification_code(f"{subject}\n正文", subject), "688-106")

    def test_legacy_letter_code_in_subject(self):
        subject = "xAI confirmation code: I6R-B2W"
        self.assertEqual(extract_verification_code(f"{subject}\n正文", subject), "I6R-B2W")

    def test_all_digit_code_in_body_only(self):
        text = "Welcome!\nYour confirmation code: 688-106\nThanks"
        self.assertEqual(extract_verification_code(text, ""), "688-106")

    def test_bare_numeric_range_is_not_a_code(self):
        # 没有 code/验证码 上下文时，纯数字串仍然不是验证码
        self.assertIsNone(extract_verification_code("价格区间 100-200 之间", ""))

    def test_bare_letter_token_still_matches(self):
        self.assertEqual(extract_verification_code("Use A1B-2C3 to continue", ""), "A1B-2C3")

    def test_alpha_code_preferred_over_numeric_in_same_source(self):
        text = "promo code: 100-200\nconfirmation code: I6R-B2W"
        self.assertEqual(extract_verification_code(text, ""), "I6R-B2W")

    def test_css_class_not_matched_after_strip_html(self):
        html = (
            "<style>.sm-w-per-100 { width: 100% }</style>"
            "<p>No code in this mail body.</p>"
        )
        self.assertIsNone(extract_verification_code(strip_html(html), ""))

    def test_plain_numeric_fallback_formats(self):
        self.assertEqual(
            extract_verification_code("Your verification code: 123456", ""), "123456"
        )
        self.assertEqual(
            extract_verification_code("confirm code: 9876", ""), "9876"
        )

    def test_empty_inputs(self):
        self.assertIsNone(extract_verification_code("", ""))
        self.assertIsNone(extract_verification_code(None, None))


if __name__ == "__main__":
    unittest.main()
