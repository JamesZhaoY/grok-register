"""Launch a headed Camoufox window on DISPLAY and verify basic Playwright access."""

from tempfile import TemporaryDirectory

from camoufox.sync_api import Camoufox


def main() -> None:
    # 注册流程使用 persistent context；冒烟测试保持相同启动路径，并用临时 profile。
    with TemporaryDirectory(prefix="camoufox-smoke-") as profile_dir:
        with Camoufox(
            headless=False,
            persistent_context=True,
            user_data_dir=profile_dir,
            geoip=False,
            humanize=False,
            i_know_what_im_doing=True,
        ) as context:
            page = context.pages[0] if context.pages else context.new_page()
            page.goto("data:text/html,<title>camoufox-ok</title><h1>ok</h1>")
            result = page.evaluate(
                "() => ({title: document.title, webdriver: navigator.webdriver, width: screen.width})"
            )
            if result.get("title") != "camoufox-ok":
                raise RuntimeError(f"unexpected browser result: {result}")
            print(f"Camoufox headed smoke OK: {result}", flush=True)


if __name__ == "__main__":
    main()
