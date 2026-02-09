import subprocess


def execute_command(command: str, timeout: int = 300) -> tuple[bool, str]:
    """Run a shell command and return (success, output)."""
    try:
        result = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        output = result.stdout
        if result.stderr:
            output += result.stderr
        return result.returncode == 0, output.strip()
    except subprocess.TimeoutExpired:
        return False, "Command timed out"
    except Exception as e:
        return False, f"Execution error: {e}"
