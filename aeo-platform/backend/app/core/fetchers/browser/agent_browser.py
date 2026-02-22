"""Agent Browser CLI wrapper."""

import asyncio
import json
from typing import Any


class AgentBrowserClient:
    """Wrapper for agent-browser CLI.

    Provides a Python interface to the agent-browser command line tool.
    """

    def __init__(self, session_name: str = "default"):
        """Initialize the browser client.

        Args:
            session_name: Session name for isolated browser instances
        """
        self.session_name = session_name

    async def run_command(self, *args: str, json_output: bool = True) -> dict[str, Any]:
        """Run an agent-browser command.

        Args:
            *args: Command arguments
            json_output: Whether to request JSON output

        Returns:
            Command output as dictionary
        """
        cmd = ["agent-browser", "--session", self.session_name]
        if json_output:
            cmd.append("--json")
        cmd.extend(args)

        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()

        if json_output and stdout:
            try:
                return json.loads(stdout.decode())
            except json.JSONDecodeError:
                return {"output": stdout.decode(), "error": stderr.decode()}
        return {"output": stdout.decode(), "error": stderr.decode()}

    async def open(self, url: str, headed: bool = False) -> dict[str, Any]:
        """Open a URL in the browser.

        Args:
            url: URL to open
            headed: Whether to show the browser window

        Returns:
            Command output
        """
        args = ["open", url]
        if headed:
            args.append("--headed")
        return await self.run_command(*args)

    async def snapshot(self, interactive_only: bool = True) -> dict[str, Any]:
        """Get a snapshot of the current page.

        Args:
            interactive_only: Only show interactive elements

        Returns:
            Snapshot data
        """
        args = ["snapshot"]
        if interactive_only:
            args.append("-i")
        return await self.run_command(*args)

    async def click(self, ref: str) -> dict[str, Any]:
        """Click an element.

        Args:
            ref: Element reference (e.g., @e1)

        Returns:
            Command output
        """
        return await self.run_command("click", ref)

    async def fill(self, ref: str, text: str) -> dict[str, Any]:
        """Fill an input field.

        Args:
            ref: Element reference
            text: Text to fill

        Returns:
            Command output
        """
        return await self.run_command("fill", ref, text)

    async def get_text(self, ref: str) -> dict[str, Any]:
        """Get text content of an element.

        Args:
            ref: Element reference

        Returns:
            Text content
        """
        return await self.run_command("get", "text", ref)

    async def wait(
        self,
        ms: int | None = None,
        text: str | None = None,
        selector: str | None = None,
    ) -> dict[str, Any]:
        """Wait for a condition.

        Args:
            ms: Milliseconds to wait
            text: Text to wait for
            selector: Selector to wait for

        Returns:
            Command output
        """
        args = ["wait"]
        if ms is not None:
            args.append(str(ms))
        if text:
            args.extend(["--text", text])
        if selector:
            args.extend(["--selector", selector])
        return await self.run_command(*args)

    async def find_and_click(self, text: str) -> dict[str, Any]:
        """Find element by text and click.

        Args:
            text: Text to find

        Returns:
            Command output
        """
        return await self.run_command("find", "text", text, "click")

    async def find_and_fill(self, label: str, text: str) -> dict[str, Any]:
        """Find element by label and fill.

        Args:
            label: Label to find
            text: Text to fill

        Returns:
            Command output
        """
        return await self.run_command("find", "label", label, "fill", text)

    async def press(self, key: str) -> dict[str, Any]:
        """Press a key.

        Args:
            key: Key to press (e.g., "Enter", "Tab")

        Returns:
            Command output
        """
        return await self.run_command("press", key)

    async def eval(self, script: str) -> dict[str, Any]:
        """Execute JavaScript.

        Args:
            script: JavaScript code

        Returns:
            Command output
        """
        return await self.run_command("eval", script)

    async def close(self) -> dict[str, Any]:
        """Close the browser.

        Returns:
            Command output
        """
        return await self.run_command("close")

    async def is_logged_in(self, check_selector: str) -> bool:
        """Check if user is logged in.

        Args:
            check_selector: Selector that indicates logged-in state

        Returns:
            True if logged in, False otherwise
        """
        result = await self.run_command("is", "visible", check_selector)
        return result.get("success", False)
