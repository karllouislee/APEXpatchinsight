from pathlib import Path


def test_windows_launcher_has_safe_project_relative_commands():
    launcher = Path("run_app.bat").read_text(encoding="utf-8")
    assert 'cd /d "%~dp0"' in launcher
    assert ".venv\\Scripts\\python.exe" in launcher
    assert "-m streamlit run app.py" in launcher
    assert "requirements.txt" in launcher
