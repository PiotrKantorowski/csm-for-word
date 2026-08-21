from pathlib import Path


def test_github_actions_uses_compiled_sidecar_exe_not_dotnet_run():
    workflow = Path('.github/workflows/build-csm-installer.yml').read_text(encoding='utf-8')
    assert 'CSM.RevisionSidecar.exe' in workflow
    assert 'dotnet run --project sidecar/CSM.RevisionSidecar/CSM.RevisionSidecar.csproj --' not in workflow
    assert 'Compiled sidecar not found' in workflow
