# 自动化测试平台登录态管理方案设计

## 1. 引言

当前自动化测试平台在处理需要登录的网站时，主要依赖用户手动导入 Cookie 来维持登录态。然而，这种方式存在以下问题：

*   **无法确定登录态是否成功导入或有效**：用户导入 Cookie 后，系统缺乏机制主动验证这些 Cookie 是否能成功建立有效会话。
*   **登录态过期后无法自动处理**：导入的 Cookie 存在有效期，一旦过期，测试用例将因登录失败而中断，需要用户手动更新。

本设计方案旨在解决上述问题，建立一套健壮的登录态管理机制，包括 Cookie 的保存、加载、有效性校验以及自动重新登录逻辑，以提升测试的稳定性和自动化程度。

## 2. 现有登录态处理分析

根据对代码库的分析，现有系统已具备以下基础：

*   **数据模型**：`backend/database.py` 中定义了 `LoginRecord` 模型，用于存储 `cookies_data` (JSON 序列化的 Cookie)、`local_storage` (JSON 序列化的 localStorage) 和 `session_valid` 状态，以及 `last_login_at` 时间戳。
*   **手动导入**：`backend/api/settings_api.py` 提供了 `/captcha/cookies/{project_id}` 接口，允许用户手动粘贴并保存 Cookie。此操作会将 `session_valid` 标记为 `True`。
*   **Playwright 集成**：`backend/test_engine/runner.py` 在生成测试文件时，会根据 `login_info` 中的 `cookies_data` 动态生成 `restore_login` fixture，通过 `page.context.add_cookies()` 将 Cookie 注入到 Playwright 上下文中。
*   **登录检测**：`backend/captcha/handler.py` 中的 `handle_slider_captcha` 函数在用户手动完成滑块验证后，会通过检查 URL 变化和特定 DOM 元素（如 `.user-info`, `.avatar`）来判断是否登录成功，并保存会话信息。

**现有机制的不足**：

*   `session_valid` 字段仅在保存时设置为 `True`，后续缺乏主动的周期性或按需校验。
*   测试执行时，仅恢复 Cookie，未在恢复后进行有效性验证。
*   没有自动重新登录的机制。

## 3. 登录态管理方案设计

### 3.1 核心目标

1.  **会话有效性主动校验**：在测试用例执行前，能够判断当前保存的登录态是否仍然有效。
2.  **过期会话自动刷新/重新登录**：当检测到登录态失效时，能够触发自动刷新或引导用户重新登录。
3.  **提升用户体验**：减少因登录态问题导致的测试中断和手动干预。

### 3.2 方案详情

#### 3.2.1 登录态有效性校验

引入一个独立的函数或方法，用于检查 `LoginRecord` 中保存的 `cookies_data` 是否仍然有效。该校验应具备以下特点：

*   **轻量级检查**：避免执行完整的登录流程，而是通过访问一个轻量级的、需要登录才能访问的页面（如用户中心、个人设置页），并检查页面上是否存在登录成功的标志性元素（如用户名、头像、退出按钮等）。
*   **Playwright 环境**：校验过程应在一个临时的 Playwright 浏览器上下文中进行，以模拟真实用户环境。
*   **结果反馈**：返回布尔值表示登录态是否有效，并可附带失效原因。

**实现思路**：

1.  在 `CaptchaHandler` 中新增 `check_session_validity(project_id: int) -> bool` 方法。
2.  该方法会从数据库加载 `LoginRecord`，并使用其中的 `cookies_data` 和 `local_storage` 创建一个 Playwright `BrowserContext`。
3.  导航到项目的 `deploy_url` 或一个预设的、需要登录才能访问的页面。
4.  通过 `page.evaluate()` 或 `page.locator().is_visible()` 检查页面上是否存在登录成功的标志性元素（例如，检查 `body` 中是否包含“欢迎回来”、“个人中心”等文本，或是否存在 `.user-info`、`.avatar` 等 CSS 选择器）。
5.  如果检查通过，则认为会话有效；否则认为失效。
6.  更新 `LoginRecord` 中的 `session_valid` 字段和 `last_login_at`。

#### 3.2.2 自动重新登录机制

当 `check_session_validity` 返回 `False` 时，系统应尝试自动重新登录。由于当前系统主要依赖手动滑块验证，自动重新登录需要用户介入。因此，这里的“自动”更多是指系统能感知失效并引导用户。

**实现思路**：

1.  **触发时机**：在 `TestRunner` 执行测试用例前，调用 `CaptchaHandler.check_session_validity()`。
2.  **处理流程**：
    *   如果校验通过，则继续执行测试。
    *   如果校验失败：
        *   将 `LoginRecord` 的 `session_valid` 设为 `False`。
        *   通知用户登录态已失效，并提供重新登录的指引（例如，通过前端界面提示用户进行手动滑块验证或重新导入 Cookie）。
        *   可以考虑在 `CaptchaHandler` 中添加一个 `refresh_session` 方法，该方法会再次启动一个 Playwright 浏览器，导航到登录页，并等待用户手动完成登录，然后更新 `LoginRecord`。
        *   对于无法自动处理的登录（如滑块验证），系统应暂停测试执行，等待用户完成登录操作。

#### 3.2.3 优化 `LoginRecord` 存储

*   **加密敏感信息**：虽然 Cookie 通常不包含明文密码，但为了安全起见，可以考虑对 `cookies_data` 和 `local_storage` 进行加密存储。这需要引入 `backend/security/encryption.py` 模块进行加解密。
*   **有效期管理**：`last_login_at` 字段可以用于判断登录态的“新鲜度”。虽然不能替代实际校验，但可以作为一种辅助判断，例如，如果 `last_login_at` 超过一定时间（如7天），即使 `session_valid` 为 `True`，也建议进行一次强制校验。

### 3.3 接口与模块调整

#### 3.3.1 `backend/captcha/handler.py` 调整

*   **新增方法**：
    ```python
    async def check_session_validity(self, project_id: int, deploy_url: str) -> bool:
        """检查指定项目的登录会话是否仍然有效"""
        # ... 实现逻辑 ...

    async def refresh_session(self, project_id: int, url: str, headless: bool = False, timeout: int = 120) -> Optional[dict]:
        """重新启动浏览器，等待用户手动完成登录，并更新会话信息"""
        # ... 实现逻辑，复用 handle_slider_captcha 的部分逻辑 ...
    ```

#### 3.3.2 `backend/api/settings_api.py` 调整

*   **新增接口**：
    ```python
    @router.post("/captcha/check_session/{project_id}")
    async def check_captcha_session(project_id: int, db: Session = Depends(get_db)):
        """手动触发登录会话有效性检查"""
        # ... 调用 CaptchaHandler.check_session_validity ...

    @router.post("/captcha/refresh_login/{project_id}")
    async def refresh_captcha_login(project_id: int, db: Session = Depends(get_db)):
        """手动触发重新登录流程（弹出浏览器）"""
        # ... 调用 CaptchaHandler.refresh_session ...
    ```

#### 3.3.3 `backend/test_engine/runner.py` 调整

*   在 `run_test_cases` 方法中，获取 `login_info` 后，增加一步调用 `CaptchaHandler.check_session_validity()`。
*   如果校验失败，则根据策略（例如，抛出异常、标记测试运行为失败、或触发 `refresh_session` 并等待用户操作）。

### 3.4 前端交互（`frontend/src/pages`）

*   **登录态状态展示**：在项目详情页或设置页，展示当前项目的登录态状态（有效/失效，上次登录时间）。
*   **手动校验按钮**：提供一个按钮，允许用户手动触发登录态有效性检查。
*   **重新登录引导**：当登录态失效时，提供明确的指引，引导用户进行重新登录操作（例如，点击按钮弹出浏览器进行手动验证）。

## 4. 总结

本方案通过引入登录态有效性校验和自动重新登录的机制，旨在解决当前平台在处理需要登录的网站时遇到的痛点。这将显著提高测试的可靠性和自动化程度，减少人工干预。下一步将根据此设计方案进行具体的代码实现。
