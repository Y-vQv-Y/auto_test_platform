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
                if await el.is_visible(timeout=500):
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
                logger.info("[策略] 方案1(Canny) 成功")
                return True
            logger.warning("[策略] 方案1(Canny): 拖拽后验证码未消失")
        except Exception as e:
            logger.warning(f"[策略] 方案1(Canny) 异常: {e}")

        # 尝试方案 2：全轨道拖拽（适用于简单滑块，缺口在尽头）
        try:
            success = await cls._solve_by_full_drag(page, slider_el, timeout)
            if success:
                logger.info("[策略] 方案2(全轨拖拽) 成功")
                return True
            logger.warning("[策略] 方案2(全轨拖拽): 拖拽后验证码未消失")
        except Exception as e:
            logger.warning(f"[策略] 方案2(全轨拖拽) 异常: {e}")

        # 方案 3：动态距离多次尝试
        try:
            success = await cls._solve_by_multi_attempt(page, slider_el, timeout)
            if success:
                logger.info("[策略] 方案3(动态距离) 成功")
                return True
        except Exception as e:
            logger.warning(f"[策略] 方案3(动态距离) 异常: {e}")

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
        screenshot_bytes = await slider_el.screenshot()
        if not screenshot_bytes:
            return False

        # 分析截图找到缺口位置
        import io
        try:
            from PIL import Image
            import numpy as np
        except ImportError:
            logger.warning("PIL/numpy 未安装，图像分析方案不可用，回退到拖拽方案")
            return False

        img = Image.open(io.BytesIO(screenshot_bytes)).convert("L")  # 灰度
        arr = np.array(img)
        height, width = arr.shape

        drag_distance = cls._find_gap_by_canny(arr, width, height)
        # 缺口应在中间区域（距左边缘 15%-85%），否则是噪声
        if drag_distance is None or drag_distance < width * 0.10 or drag_distance > width * 0.90:
            logger.warning(f"Canny 边缘检测结果不可靠 (位置={drag_distance}px, 宽度={width}px)，回退到全轨拖拽")
            return False

        logger.info(f"图像分析(Canny): 图像={width}x{height}, 缺口位置≈{drag_distance}px")
        return await cls._perform_drag(page, slider_el, drag_distance)

    @classmethod
    def _find_gap_by_canny(cls, arr, width, height):
        """Canny 边缘检测 + 轮廓查找定位缺口位置。返回 x 坐标或 None。"""
        import numpy as np
        try:
            from skimage.feature import canny
            from skimage.filters import threshold_otsu

            # Otsu 自动阈值 → Canny 边缘检测
            thresh = threshold_otsu(arr)
            edges = canny(arr, sigma=1.5, low_threshold=thresh * 0.5, high_threshold=thresh)
        except ImportError:
            # fallback: 手动 Canny (简化版，不依赖 skimage)
            edges = cls._simple_edge_detect(arr)

        edge_img = edges.astype(np.uint8) * 255

        # 查找轮廓
        from PIL import Image as PILImage
        edge_pil = PILImage.fromarray(edge_img, mode='L')

        # 用连通域分析找缺口区域
        # 缺口特征：位于中上区域，呈矩形
        gap_found = False
        best_x = None

        # 简化的缺口定位：在边缘图中找左右边缘突变点
        # 缺口左边界：从左往右扫描，第一个边缘像素密集的列
        # 缺口右边界：从缺口左边界继续扫描，边缘像素稀疏的位置
        col_edges = edges.sum(axis=0)

        # 找边缘密度最高的区域（缺口边界最明显）
        window = max(5, width // 20)
        smoothed = np.convolve(col_edges, np.ones(window)/window, mode='same')

        # 在中间 80% 区域找两个峰值（缺口左边缘和右边缘）
        s, e = int(width * 0.05), int(width * 0.95)
        if e <= s:
            s, e = 0, width

        # 找梯度最大的点（边缘密度变化最快 = 缺口边界）
        grad = np.abs(np.diff(smoothed[s:e]))
        if len(grad) == 0:
            return None

        # 找 top 2 峰值作为缺口的左右边界
        peak_indices = np.argsort(grad)[-4:]  # top 4
        peak_indices = sorted([p + s for p in peak_indices])

        # 取最靠左的显著峰值作为缺口左边缘
        for p in peak_indices:
            if grad[p - s] > grad.max() * 0.3:  # 显著度过滤
                best_x = p
                break

        if best_x is None and len(peak_indices) > 0:
            best_x = peak_indices[0]

        return best_x

    @classmethod
    def _simple_edge_detect(cls, arr):
        """简化版边缘检测（skimage 不可用时的 fallback）。Sobel 算子。"""
        import numpy as np
        # Sobel X 方向
        kernel_x = np.array([[-1, 0, 1], [-2, 0, 2], [-1, 0, 1]])
        h, w = arr.shape
        edges = np.zeros((h, w), dtype=bool)
        for y in range(1, h - 1):
            for x in range(1, w - 1):
                patch = arr[y-1:y+2, x-1:x+2].astype(float)
                gx = np.sum(kernel_x * patch)
                edges[y, x] = abs(gx) > 30  # 阈值
        return edges

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
                if await el.is_visible(timeout=200):
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
        方案 3：动态距离遍历，带随机抖动避免完全相同的拖拽。
        """
        box = await slider_el.bounding_box()
        if not box:
            return False

        track_width = box["width"] - 40
        # 动态距离：覆盖轨道宽度的 90% → 15%，加随机抖动 ±5px
        ratios = [0.90, 0.75, 0.60, 0.45, 0.30, 0.15]

        for i, ratio in enumerate(ratios):
            jitter = random.randint(-5, 5)
            distance = max(10, int(track_width * ratio) + jitter)
            logger.info(f"[动态距离] #{i+1}/{len(ratios)}: 距离={distance}px (ratio={ratio:.0%}, jitter={jitter:+d})")

            # 每次尝试前先刷新（有些验证码失败后需要重置）
            try:
                refresh_btn = page.locator("[class*='refresh'], .reload, .reset, [class*='retry']").first
                if await refresh_btn.is_visible(timeout=200):
                    await refresh_btn.click()
                    await page.wait_for_timeout(500)
            except Exception:
                pass

            if await cls._perform_drag(page, slider_el, distance):
                return True

            await page.wait_for_timeout(300)

        return False

    @classmethod
    async def _perform_drag(cls, page, slider_el, distance: int) -> bool:
        """
        执行拟人化拖拽操作。
        1. 找到滑块按钮
        2. 模拟人类拖拽（先快后慢，有小幅抖动）
        3. 检查验证码是否消失
        """
        drag_start = time.monotonic()
        logger.info(f"[拖拽] 开始, 目标距离={distance}px")

        # 找到滑块按钮
        knob = None
        for selector in cls.KNOB_SELECTORS + [".slide-verify-slider > *", ".slider-button", "div[class*='btn']"]:
            try:
                el = slider_el.locator(selector).first
                if await el.is_visible(timeout=200):
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

        elapsed = (time.monotonic() - drag_start) * 1000
        logger.info(f"[拖拽] 完成, 距离≈{distance}px, 步数={len(steps)}, 耗时={elapsed:.0f}ms")

        # 等待验证结果
        await page.wait_for_timeout(1500)

        # 检查验证码是否消失（成功了）
        try:
            still_visible = await slider_el.is_visible(timeout=200)
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
    async def wait_for_captcha_gone(cls, page, timeout: int = 120) -> bool:
        """
        等待验证码消失。持续重试直到成功或总超时。
        每次失败后刷新验证码重新尝试。
        """
        start = time.monotonic()
        retry_count = 0
        solved = False

        logger.info(f"[验证码] 开始等待，总超时={timeout}s")

        while time.monotonic() - start < timeout:
            # 先检查是否已经登录成功
            is_logged = await page.evaluate("""() => {
                const body = document.body.textContent || '';
                const hasNav = !!document.querySelector('.sidebar, .el-menu, .navbar, .el-header, .header');
                const isLogin = window.location.href.toLowerCase().includes('login');
                return hasNav && !isLogin;
            }""")

            if is_logged:
                logger.info("[验证码] 检测到已登录，跳过验证码处理")
                return True

            # 检测验证码
            captcha_found = False
            for selector in cls.SLIDER_DETECTORS:
                try:
                    el = page.locator(selector).first
                    if await el.is_visible(timeout=500):
                        captcha_found = True
                        retry_count += 1
                        elapsed = time.monotonic() - start
                        logger.info(f"[验证码] 检测到 [{selector}]，第 {retry_count} 轮求解 (已耗时 {elapsed:.0f}s)")

                        solved = await cls.detect_and_solve(page, timeout=8)
                        break
                except Exception:
                    continue

            if solved:
                break

            # 本轮失败 — 刷新验证码后重试
            if captcha_found:
                logger.info(f"[验证码] 第 {retry_count} 轮失败，刷新验证码后重试...")
                try:
                    refresh_btn = page.locator("[class*='refresh'], .reload, .reset, [class*='retry']").first
                    if await refresh_btn.is_visible(timeout=500):
                        await refresh_btn.click()
                except Exception:
                    pass

            await page.wait_for_timeout(2000)

        if solved:
            elapsed = time.monotonic() - start
            logger.info(f"[验证码] 成功解决! 共 {retry_count} 轮, 耗时 {elapsed:.0f}s")
            await page.wait_for_timeout(3000)
            return True

        logger.warning(f"[验证码] 超时放弃: 共 {retry_count} 轮, 耗时 {timeout}s")
        return False
