"""滑块验证码自动破解器 — 基于 Playwright 的图像分析 + 模拟拖拽"""

import random
import time
from typing import Optional
from loguru import logger


class SliderSolver:
    """自动处理滑块/拖动验证码"""

    # 常见的滑块验证码选择器（Element UI / Vue 生态）
    SLIDER_DETECTORS = [
        # 通用滑块容器
        ".slide-verify",
        ".slider-verify",
        ".slider-captcha",
        ".captcha-slider",
        ".drag-verify",
        ".verify-slider",
        ".slideVerify",
        ".captcha_slider",
        # Element UI / Vue 生态
        "[class*='slide-verify']",
        "[class*='slider-verify']",
        "[class*='captcha-box']",
        "[class*='verify-box']",
        # 特定组件
        ".verifybox",
        "#sliderVerify",
        "#captcha",
        # 图片拖动类型
        "canvas[class*='captcha']",
        ".block",
    ]

    # 滑块拖拽按钮选择器
    KNOB_SELECTORS = [
        ".slide-verify-slider",
        ".slider-button",
        ".slider-btn",
        ".drag-btn",
        ".verify-btn",
        ".slide-verify-btn",
        "[class*='slider-btn']",
        "[class*='slide-btn']",
        ".slide-verify-slider-btn",
        ".block",
    ]

    # 滑块轨道选择器
    TRACK_SELECTORS = [
        ".slide-verify-slider-track",
        ".slider-track",
        ".slide-verify-track",
        ".drag-track",
        "[class*='slider-track']",
    ]

    @classmethod
    async def detect_and_solve(cls, page, timeout: int = 10) -> bool:
        """
        检测页面上是否存在滑块验证码，并尝试自动解决。
        返回 True 表示成功解决或没有检测到验证码。
        """
        await page.wait_for_timeout(1500)  # 给验证码弹出留时间

        # 检测滑块验证码是否存在
        slider_el = None
        for selector in cls.SLIDER_DETECTORS:
            try:
                el = page.locator(selector).first
                if await el.is_visible(timeout=2000):
                    slider_el = el
                    logger.info(f"检测到滑块验证码: {selector}")
                    break
            except Exception:
                continue

        if not slider_el:
            logger.info("未检测到滑块验证码，可能无需处理或不是滑块类型")
            return True  # 没有验证码，视为成功

        # 尝试方案 1：图像分析定位缺口
        try:
            success = await cls._solve_by_image_analysis(page, slider_el, timeout)
            if success:
                return True
        except Exception as e:
            logger.warning(f"图像分析方案失败: {e}")

        # 尝试方案 2：全轨道拖拽（适用于简单滑块，缺口在尽头）
        try:
            success = await cls._solve_by_full_drag(page, slider_el, timeout)
            if success:
                return True
        except Exception as e:
            logger.warning(f"全轨道拖拽方案失败: {e}")

        # 方案 3：多次尝试不同距离
        try:
            success = await cls._solve_by_multi_attempt(page, slider_el, timeout)
            if success:
                return True
        except Exception as e:
            logger.warning(f"多次尝试方案失败: {e}")

        return False

    @classmethod
    async def _solve_by_image_analysis(cls, page, slider_el, timeout: int) -> bool:
        """
        方案 1：通过分析滑块背景图找到缺口位置，精确拖拽。
        """
        # 获取滑块的背景图 src
        bg_images = []
        for img_selector in ["img", ".slide-verify-bg img", "img[class*='bg']", "[style*='background']"]:
            try:
                imgs = await slider_el.locator(img_selector).all()
                for img in imgs:
                    src = await img.get_attribute("src")
                    if src:
                        bg_images.append(src)
            except Exception:
                pass

        if not bg_images:
            # 尝试获取 canvas 背景
            canvases = await slider_el.locator("canvas").all()
            if canvases and await canvases[0].count() > 0:
                logger.info("检测到 canvas 类型验证码，无法图像分析，尝试全轨拖拽")
                return False

            logger.info("未找到滑块背景图，尝试全轨拖拽")
            return False

        # 获取 slider 的边界框
        box = await slider_el.bounding_box()
        if not box:
            return False

        # 取整个滑块区域的截图
        screenshot_b64 = await slider_el.screenshot()
        if not screenshot_b64:
            return False

        # 分析截图找到缺口位置
        import base64
        import io
        try:
            from PIL import Image
            import numpy as np
        except ImportError:
            logger.warning("PIL/numpy 未安装，图像分析方案不可用，回退到拖拽方案")
            return False

        img_bytes = base64.b64decode(screenshot_b64)
        img = Image.open(io.BytesIO(img_bytes)).convert("L")  # 灰度
        arr = np.array(img)

        # 边缘检测：找竖直方向上的突变（缺口边界）
        # 对每列计算像素变化，缺口处像素会有明显差异
        height, width = arr.shape
        col_diffs = np.zeros(width)
        for x in range(1, width):
            col_diffs[x] = np.abs(arr[:, x].astype(float) - arr[:, x - 1].astype(float)).mean()

        # 找差异最大的位置（缺口位置）
        # 排除边缘区域
        search_start = int(width * 0.05)
        search_end = int(width * 0.95)
        if search_end <= search_start:
            search_start, search_end = 0, width

        max_idx = search_start + np.argmax(col_diffs[search_start:search_end])

        # 转换为实际拖拽距离
        drag_distance = max_idx

        logger.info(f"图像分析: 图像宽度={width}, 估计缺口位置≈{drag_distance}px, 差异值={col_diffs[max_idx]:.1f}")

        # 执行拖拽
        return await cls._perform_drag(page, slider_el, drag_distance)

    @classmethod
    async def _solve_by_full_drag(cls, page, slider_el, timeout: int) -> bool:
        """
        方案 2：将滑块拖到轨道最右端（适用于填满型滑块验证码）。
        """
        box = await slider_el.bounding_box()
        if not box:
            return False

        # 找到滑块轨道
        track = None
        for selector in cls.TRACK_SELECTORS:
            try:
                el = slider_el.locator(selector).first
                if await el.is_visible(timeout=1000):
                    track = await el.bounding_box()
                    break
            except Exception:
                continue

        # 如果没找到独立轨道，使用滑块容器宽度
        if not track:
            track = box

        # 减去滑块自身宽度
        drag_distance = track["width"] - 50  # 滑块按钮通常约 40-50px

        logger.info(f"全轨拖拽: 轨道宽度={track['width']}, 拖拽距离≈{drag_distance}px")
        return await cls._perform_drag(page, slider_el, max(50, drag_distance))

    @classmethod
    async def _solve_by_multi_attempt(cls, page, slider_el, timeout: int) -> bool:
        """
        方案 3：尝试多个不同距离，找到正确位置。
        """
        box = await slider_el.bounding_box()
        if not box:
            return False

        track_width = box["width"] - 40
        # 尝试多个距离：30%, 50%, 70%, 85% 的轨道宽度
        attempts = [
            int(track_width * 0.85),
            int(track_width * 0.70),
            int(track_width * 0.55),
            int(track_width * 0.40),
        ]

        for i, distance in enumerate(attempts):
            logger.info(f"多次尝试 #{i+1}: 距离={distance}px")
            # 每次尝试前先刷新（有些验证码失败后需要重置）
            try:
                refresh_btn = page.locator("[class*='refresh'], .reload, .reset, [class*='retry']").first
                if await refresh_btn.is_visible(timeout=1000):
                    await refresh_btn.click()
                    await page.wait_for_timeout(500)
            except Exception:
                pass

            if await cls._perform_drag(page, slider_el, distance):
                return True

            await page.wait_for_timeout(500)

        return False

    @classmethod
    async def _perform_drag(cls, page, slider_el, distance: int) -> bool:
        """
        执行拟人化拖拽操作。
        1. 找到滑块按钮
        2. 模拟人类拖拽（先快后慢，有小幅抖动）
        3. 检查验证码是否消失
        """
        # 找到滑块按钮
        knob = None
        for selector in cls.KNOB_SELECTORS + [".slide-verify-slider > *", ".slider-button", "div[class*='btn']"]:
            try:
                el = slider_el.locator(selector).first
                if await el.is_visible(timeout=1000):
                    knob = el
                    break
            except Exception:
                continue

        if not knob:
            # 如果找不到独立按钮，尝试 slider_el 本身
            knob = slider_el

        box = await knob.bounding_box()
        if not box:
            # 尝试 slider_el 的 box
            box = await slider_el.bounding_box()
            if not box:
                logger.warning("无法获取滑块边界框")
                return False

        # 计算起始点和终点
        start_x = box["x"] + box["width"] / 2
        start_y = box["y"] + box["height"] / 2

        # 拟人化拖拽轨迹
        steps = []
        remaining = distance
        # 前快后慢，带微抖动
        segments = [
            (0.55, 0.0),   # 55% 距离，匀速
            (0.25, 0.3),   # 25% 距离，开始减速
            (0.12, 0.6),   # 12% 距离，明显减速
            (0.08, 0.9),   # 最后 8%，很慢
        ]

        for ratio, slow_factor in segments:
            seg_dist = remaining * ratio
            seg_steps = max(1, int(seg_dist / (2 if slow_factor > 0.5 else 3)))  # 每步 2-3px
            for i in range(seg_steps):
                step_dist = seg_dist / seg_steps
                # 添加微小抖动（模拟人手）
                jitter_y = random.uniform(-1.5, 1.5)
                jitter_x = random.uniform(-0.5, 0.5)
                if slow_factor > 0:
                    jitter_x += random.uniform(-1, 0)  # 接近目标时回拉一下
                steps.append((step_dist + jitter_x, jitter_y))

        # 执行拖拽
        current_x = start_x
        current_y = start_y

        await page.mouse.move(start_x, start_y)
        await page.mouse.down()

        for dx, dy in steps:
            current_x += dx
            current_y += dy
            await page.mouse.move(current_x, current_y, steps=1)
            await page.wait_for_timeout(random.randint(8, 20))

        # 微小停顿模拟松手前的调整
        await page.wait_for_timeout(random.randint(50, 150))

        await page.mouse.up()

        logger.info(f"拖拽完成: 距离≈{distance}px, 步数={len(steps)}")

        # 等待验证结果
        await page.wait_for_timeout(1500)

        # 检查验证码是否消失（成功了）
        try:
            still_visible = await slider_el.is_visible(timeout=1000)
            if not still_visible:
                logger.info("验证码已消失，滑动成功！")
                return True
        except Exception:
            # 元素可能已被移除
            logger.info("验证码元素已不可见，可能已成功")
            return True

        # 检查是否有成功提示
        try:
            success_texts = await page.evaluate("""() => {
                const body = document.body.textContent || '';
                return body.includes('验证通过') || body.includes('验证成功') ||
                       body.includes('Verification successful') || body.includes('success');
            }""")
            if success_texts:
                logger.info("检测到验证成功文本")
                return True
        except Exception:
            pass

        # 检查是否有失败提示
        try:
            fail_texts = await page.evaluate("""() => {
                const body = document.body.textContent || '';
                return body.includes('验证失败') || body.includes('请重试') ||
                       body.includes('再试一次') || body.includes('try again');
            }""")
            if fail_texts:
                logger.warning("检测到验证失败提示")
                return False
        except Exception:
            pass

        logger.info("验证码仍存在，拖拽可能不准确")
        return False

    @classmethod
    async def wait_for_captcha_gone(cls, page, timeout: int = 30) -> bool:
        """
        等待验证码消失（用于在点击登录后，等待验证码出现然后自动解决）。
        轮询检测验证码元素，检测到自动处理。
        """
        start = time.monotonic()
        solved = False

        while time.monotonic() - start < timeout:
            # 先检查是否已经登录成功
            is_logged = await page.evaluate("""() => {
                const body = document.body.textContent || '';
                const hasNav = !!document.querySelector('.sidebar, .el-menu, .navbar, .el-header, .header');
                const isLogin = window.location.href.toLowerCase().includes('login');
                return hasNav && !isLogin;
            }""")

            if is_logged:
                logger.info("检测到已登录，跳过验证码处理")
                return True

            # 检测验证码
            captcha_found = False
            for selector in cls.SLIDER_DETECTORS:
                try:
                    el = page.locator(selector).first
                    if await el.is_visible(timeout=500):
                        captcha_found = True
                        logger.info(f"检测到验证码 [{selector}]，开始自动解决...")
                        solved = await cls.detect_and_solve(page, timeout=5)
                        break
                except Exception:
                    continue

            if solved:
                break

            await page.wait_for_timeout(1000)

        if solved:
            # 验证码解决后等待页面跳转或登录成功
            await page.wait_for_timeout(3000)
            return True

        return False
